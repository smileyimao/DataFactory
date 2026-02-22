# config/startup.py — 开机自检与滚动清零，提升 edge 部署稳定性
"""
开机自检：校验配置与关键目录可写，失败则打日志并返回 False，由 main 决定是否退出。
黄金库自检：可选用 paths.golden 下视频真跑一遍 QC，确保 pipeline 能跑通（edge 建议开启）。
滚动清零：按 settings 中 rolling_cleanup 保留天数删除过期日志/报表（可选 archive）。
"""
import logging
import os
import shutil
import tempfile
import time
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

VIDEO_EXT = (".mov", ".mp4", ".avi", ".mkv")


def run_startup_self_check(cfg: Dict[str, Any]) -> bool:
    """
    开机自检：校验 paths 中关键目录存在且可写，db 父目录可写。
    返回 True 表示通过，False 表示不通过（调用方可 exit(1)）。
    """
    paths = cfg.get("paths", {})
    checks = [
        ("raw_video", "原材料目录"),
        ("data_warehouse", "成品库目录"),
        ("reports", "报表目录"),
        ("logs", "日志目录"),
    ]
    for key, label in checks:
        dir_path = paths.get(key)
        if not dir_path:
            logger.error("开机自检失败: 配置缺少 paths.%s", key)
            return False
        dir_path = os.path.abspath(dir_path)
        try:
            os.makedirs(dir_path, exist_ok=True)
            probe = os.path.join(dir_path, ".write_probe")
            with open(probe, "w") as f:
                f.write("")
            os.remove(probe)
        except OSError as e:
            logger.error("开机自检失败: %s 不可写 [%s] — %s", label, dir_path, e)
            return False
    db_path = paths.get("db_file")
    if db_path:
        db_dir = os.path.dirname(os.path.abspath(db_path))
        try:
            os.makedirs(db_dir, exist_ok=True)
            probe = os.path.join(db_dir, ".write_probe")
            with open(probe, "w") as f:
                f.write("")
            os.remove(probe)
        except OSError as e:
            logger.error("开机自检失败: 数据库目录不可写 [%s] — %s", db_dir, e)
            return False
    logger.info("开机自检通过: 配置与关键目录可写")
    return True


def run_golden_run(cfg: Dict[str, Any]) -> bool:
    """
    黄金库自检：用 paths.golden 下至少一个视频真跑一遍 QC，不崩且返回结果即通过。
    若黄金库目录不存在或为空，跳过并返回 True。失败返回 False（调用方可 exit(1)）。
    """
    paths = cfg.get("paths", {})
    golden_dir = paths.get("golden")
    if not golden_dir or not os.path.isdir(golden_dir):
        logger.info("黄金库自检跳过: 目录不存在或未配置 paths.golden")
        return True
    candidates = []
    for name in os.listdir(golden_dir):
        if not any(name.lower().endswith(ext) for ext in VIDEO_EXT):
            continue
        path = os.path.join(golden_dir, name)
        if os.path.isfile(path):
            candidates.append(path)
    if not candidates:
        logger.info("黄金库自检跳过: 目录为空，请放入 1～2 个参考视频（.mov/.mp4 等）")
        return True
    # 只跑第一个，控制开机耗时
    one = candidates[0]
    logger.info("黄金库自检: 使用 %s 真跑一遍 QC", os.path.basename(one))
    try:
        with tempfile.TemporaryDirectory(prefix="golden_run_") as tmp:
            temp_raw = os.path.join(tmp, "raw")
            temp_warehouse = os.path.join(tmp, "warehouse")
            temp_db = os.path.join(tmp, "db.sqlite")
            temp_reports = os.path.join(tmp, "reports")
            os.makedirs(temp_raw, exist_ok=True)
            os.makedirs(temp_warehouse, exist_ok=True)
            os.makedirs(temp_reports, exist_ok=True)
            dest = os.path.join(temp_raw, os.path.basename(one))
            shutil.copy2(one, dest)
            run_cfg = dict(cfg)
            run_cfg["paths"] = dict(cfg.get("paths", {}))
            run_cfg["paths"]["raw_video"] = temp_raw
            run_cfg["paths"]["data_warehouse"] = temp_warehouse
            run_cfg["paths"]["db_file"] = temp_db
            run_cfg["paths"]["reports"] = temp_reports
            run_cfg["email_setting"] = {}
            from engines import db_tools
            from core import qc_engine
            db_tools.init_db(temp_db)
            qc_archive, _, _, _, _ = qc_engine.run_qc(run_cfg, [dest])
            if not qc_archive:
                logger.error("黄金库自检失败: QC 未返回任何结果")
                return False
            logger.info("黄金库自检通过: 真跑完成，%d 个文件有质检结果", len(qc_archive))
            return True
    except Exception as e:
        logger.exception("黄金库自检失败: 运行 QC 异常 — %s", e)
        return False


def _list_files_older_than(dir_path: str, days: float) -> List[Tuple[str, float]]:
    """返回 (绝对路径, mtime) 中 mtime 早于 (now - days) 的文件列表。"""
    if not os.path.isdir(dir_path) or days <= 0:
        return []
    now = time.time()
    cutoff = now - days * 86400
    out = []
    for name in os.listdir(dir_path):
        path = os.path.join(dir_path, name)
        if not os.path.isfile(path):
            continue
        try:
            mtime = os.path.getmtime(path)
            if mtime < cutoff:
                out.append((path, mtime))
        except OSError:
            continue
    return out


def _list_dirs_older_than(dir_path: str, days: float, prefix: str = "") -> List[Tuple[str, float]]:
    """返回 (绝对路径, mtime) 中 mtime 早于 (now - days) 的子目录列表；prefix 用于过滤（如 Batch_）。"""
    if not os.path.isdir(dir_path) or days <= 0:
        return []
    now = time.time()
    cutoff = now - days * 86400
    out = []
    for name in os.listdir(dir_path):
        if prefix and not name.startswith(prefix):
            continue
        path = os.path.join(dir_path, name)
        if not os.path.isdir(path):
            continue
        try:
            mtime = os.path.getmtime(path)
            if mtime < cutoff:
                out.append((path, mtime))
        except OSError:
            continue
    return out


def run_rolling_cleanup(cfg: Dict[str, Any]) -> None:
    """
    滚动清零：按 rolling_cleanup 配置删除过期日志、报表（及可选 archive 批次目录）。
    全球/边缘部署时可在 settings.yaml 中覆盖 retention 天数以适配不同存储环境。
    """
    rc = cfg.get("rolling_cleanup") or {}
    paths = cfg.get("paths", {})
    logs_dir = paths.get("logs")
    reports_dir = paths.get("reports")
    archive_dir = paths.get("data_warehouse")

    logs_days = int(rc.get("logs_retention_days", 0))
    reports_days = int(rc.get("reports_retention_days", 0))
    archive_days = int(rc.get("archive_retention_days", 0))

    if logs_days > 0 and logs_dir and os.path.isdir(logs_dir):
        removed = 0
        for path, _ in _list_files_older_than(logs_dir, logs_days):
            try:
                os.remove(path)
                removed += 1
                logger.info("滚动清零: 删除过期日志 %s", os.path.basename(path))
            except OSError as e:
                logger.warning("滚动清零: 删除日志失败 %s — %s", path, e)
        if removed:
            logger.info("滚动清零: 日志目录已清理 %d 个过期文件", removed)

    if reports_days > 0 and reports_dir and os.path.isdir(reports_dir):
        removed = 0
        for path, _ in _list_files_older_than(reports_dir, reports_days):
            try:
                os.remove(path)
                removed += 1
                logger.info("滚动清零: 删除过期报表 %s", os.path.basename(path))
            except OSError as e:
                logger.warning("滚动清零: 删除报表失败 %s — %s", path, e)
        if removed:
            logger.info("滚动清零: 报表目录已清理 %d 个过期文件", removed)

    if archive_days > 0 and archive_dir and os.path.isdir(archive_dir):
        import shutil
        removed = 0
        for path, _ in _list_dirs_older_than(archive_dir, archive_days, "Batch_"):
            try:
                shutil.rmtree(path)
                removed += 1
                logger.info("滚动清零: 删除过期批次 %s", os.path.basename(path))
            except OSError as e:
                logger.warning("滚动清零: 删除批次目录失败 %s — %s", path, e)
        if removed:
            logger.info("滚动清零: 成品库已清理 %d 个过期批次", removed)
