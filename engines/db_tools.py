# engines/db_tools.py — 数据库工具：查重、记录，只读写不决策
import sqlite3
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def init_db(db_path: str) -> None:
    """创建 production_history 与 batch_metrics 表。"""
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
    conn.commit()
    conn.close()


def get_reproduce_info(db_path: str, md5: str) -> Optional[Dict[str, Any]]:
    """若该指纹曾量产成功，返回 {batch_id, created_at}，否则 None。"""
    if not md5:
        return None
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


def record_production(
    db_path: str,
    batch_id: str,
    fingerprint: str,
    pass_rate: float,
    status: str,
    created_at: Optional[str] = None,
    sync_id: Optional[str] = None,
) -> None:
    """写入一条生产记录。created_at 不传则用当前多伦多时间。sync_id 预留，用于未来对齐外部传感器时间戳。"""
    if created_at is None:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            created_at = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
        except ImportError:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO production_history (batch_id, fingerprint, pass_rate, status, created_at, sync_id) VALUES (?, ?, ?, ?, ?, ?)",
        (batch_id, fingerprint, pass_rate, status, created_at, sync_id),
    )
    conn.commit()
    conn.close()


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
) -> None:
    """写入一批次的处理指标（各阶段耗时、吞吐量），供 v3 监控与报表使用。"""
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
