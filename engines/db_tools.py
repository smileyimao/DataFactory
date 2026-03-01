# engines/db_tools.py — 数据库工具：查重、记录、血缘，只读写不决策
# P0 工业级：所有 DB 操作捕获异常，记录日志，失败时返回 None/空
import json
import os
import sqlite3
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def init_db(db_path: str) -> bool:
    """创建 production_history 与 batch_metrics 表。成功返回 True，失败记录日志并返回 False。"""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS production_history (
                batch_id TEXT PRIMARY KEY,
                fingerprint TEXT,
                pass_rate REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_id VARCHAR(64) NULL
            )
        """)
        try:
            cur.execute("ALTER TABLE production_history ADD COLUMN sync_id VARCHAR(64) NULL")
        except sqlite3.OperationalError:
            pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS batch_metrics (
                batch_id TEXT PRIMARY KEY,
                file_count INTEGER,
                size_gb REAL,
                elapsed_sec REAL,
                duration_ingest_sec REAL,
                duration_qc_sec REAL,
                duration_review_sec REAL,
                duration_archive_sec REAL,
                throughput_gb_per_hour REAL,
                files_per_hour REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # v3 血缘表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS batch_lineage (
                batch_id TEXT PRIMARY KEY,
                batch_base TEXT,
                source_dir TEXT,
                refinery_dir TEXT,
                inspection_dir TEXT,
                transform_params TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS label_import (
                import_id TEXT PRIMARY KEY,
                batch_ids TEXT,
                training_dir TEXT,
                consistency_rate REAL,
                merged_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # v3.1 模型训练血缘
        cur.execute("""
            CREATE TABLE IF NOT EXISTS model_train (
                run_id        TEXT PRIMARY KEY,
                model_name    TEXT,
                registry_uri  TEXT,
                base_model    TEXT,
                training_dir  TEXT,
                import_ids    TEXT,
                dataset_size  INTEGER,
                epochs        INTEGER,
                map50         REAL,
                map50_95      REAL,
                precision     REAL,
                recall        REAL,
                mlflow_run_id TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.exception("数据库初始化失败: %s — %s", db_path, e)
        return False


def get_reproduce_info(db_path: str, md5: str) -> Optional[Dict[str, Any]]:
    """若该指纹曾量产成功，返回 {batch_id, created_at}，否则 None。DB 异常时返回 None。"""
    if not md5:
        return None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT batch_id, created_at FROM production_history WHERE fingerprint = ? AND status = 'SUCCESS'",
            (md5,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        batch_id, created_at = row
        logger.info("数据库查重命中: fingerprint 对应批次=%s 处理时间=%s", batch_id, created_at)
        try:
            created_at_str = created_at[:19].replace("T", " ") if isinstance(created_at, str) and " " in created_at else (str(created_at)[:19] if created_at else "未知时间")
        except Exception:
            created_at_str = str(created_at) if created_at else "未知时间"
        return {"batch_id": batch_id, "created_at": created_at_str}
    except sqlite3.Error as e:
        logger.exception("数据库查重失败: db_path=%s md5=%s — %s", db_path, md5[:16] if md5 else "", e)
        return None


def record_production(
    db_path: str,
    batch_id: str,
    fingerprint: str,
    pass_rate: float,
    status: str,
    created_at: Optional[str] = None,
    sync_id: Optional[str] = None,
) -> bool:
    """写入一条生产记录。成功返回 True，失败记录日志并返回 False。"""
    if created_at is None:
        from core import time_utils
        created_at = time_utils.now_toronto().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO production_history (batch_id, fingerprint, pass_rate, status, created_at, sync_id) VALUES (?, ?, ?, ?, ?, ?)",
            (batch_id, fingerprint, pass_rate, status, created_at, sync_id),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.exception("数据库写入失败: batch_id=%s fingerprint=%s — %s", batch_id, fingerprint[:16] if fingerprint else "", e)
        return False


def record_batch_metrics(
    db_path: str,
    batch_id: str,
    file_count: int,
    size_gb: float,
    elapsed_sec: float,
    duration_ingest_sec: float,
    duration_qc_sec: float,
    duration_review_sec: float,
    duration_archive_sec: float,
    throughput_gb_per_hour: float,
    files_per_hour: float,
) -> bool:
    """写入一批次的处理指标。成功返回 True，失败记录日志并返回 False。"""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO batch_metrics (
                batch_id, file_count, size_gb, elapsed_sec,
                duration_ingest_sec, duration_qc_sec, duration_review_sec, duration_archive_sec,
                throughput_gb_per_hour, files_per_hour
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                batch_id,
                file_count,
                size_gb,
                elapsed_sec,
                duration_ingest_sec,
                duration_qc_sec,
                duration_review_sec,
                duration_archive_sec,
                throughput_gb_per_hour,
                files_per_hour,
            ),
        )
        conn.commit()
        conn.close()
        logger.info(
            "batch_metrics 已写入: batch_id=%s elapsed=%.1fs throughput=%.2f GB/h",
            batch_id,
            elapsed_sec,
            throughput_gb_per_hour,
        )
        return True
    except sqlite3.Error as e:
        logger.exception("batch_metrics 写入失败: batch_id=%s — %s", batch_id, e)
        return False


def record_batch_lineage(
    db_path: str,
    batch_id: str,
    batch_base: str,
    source_dir: str,
    refinery_dir: str,
    inspection_dir: str,
    transform_params: Optional[Dict[str, Any]] = None,
) -> bool:
    """写入批次血缘。成功返回 True，失败记录日志并返回 False。"""
    if not db_path or not os.path.isfile(os.path.abspath(db_path)):
        return False
    params_json = json.dumps(transform_params or {}, ensure_ascii=False)
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO batch_lineage
               (batch_id, batch_base, source_dir, refinery_dir, inspection_dir, transform_params)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (batch_id, batch_base, source_dir, refinery_dir, inspection_dir, params_json),
        )
        conn.commit()
        conn.close()
        logger.info("batch_lineage 已写入: batch_id=%s", batch_id)
        return True
    except sqlite3.Error as e:
        logger.exception("batch_lineage 写入失败: batch_id=%s — %s", batch_id, e)
        return False


def record_label_import(
    db_path: str,
    import_id: str,
    batch_ids: List[str],
    training_dir: str,
    consistency_rate: float,
    merged_count: int,
) -> bool:
    """写入标注回传血缘。成功返回 True，失败记录日志并返回 False。"""
    if not db_path or not os.path.isfile(os.path.abspath(db_path)):
        return False
    batch_ids_json = json.dumps(batch_ids, ensure_ascii=False)
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO label_import
               (import_id, batch_ids, training_dir, consistency_rate, merged_count)
               VALUES (?, ?, ?, ?, ?)""",
            (import_id, batch_ids_json, training_dir, consistency_rate, merged_count),
        )
        conn.commit()
        conn.close()
        logger.info("label_import 已写入: import_id=%s batch_ids=%s", import_id, batch_ids)
        return True
    except sqlite3.Error as e:
        logger.exception("label_import 写入失败: import_id=%s — %s", import_id, e)
        return False


def get_batch_lineage(db_path: str, batch_id: str) -> Optional[Dict[str, Any]]:
    """查询批次血缘。返回 dict 或 None。"""
    if not db_path or not os.path.isfile(os.path.abspath(db_path)):
        return None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT batch_id, batch_base, source_dir, refinery_dir, inspection_dir, transform_params, created_at FROM batch_lineage WHERE batch_id = ?", (batch_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        out = {
            "batch_id": row[0],
            "batch_base": row[1],
            "source_dir": row[2],
            "refinery_dir": row[3],
            "inspection_dir": row[4],
            "created_at": row[6],
        }
        if row[5]:
            try:
                out["transform_params"] = json.loads(row[5])
            except json.JSONDecodeError:
                out["transform_params"] = {}
        else:
            out["transform_params"] = {}
        return out
    except sqlite3.Error as e:
        logger.exception("batch_lineage 查询失败: batch_id=%s — %s", batch_id, e)
        return None
