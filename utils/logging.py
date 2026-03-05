# utils/logging.py — 应用日志配置（P1 时区+轮转配置驱动；P2 结构化 JSON 日志）
import json
import logging
import logging.handlers
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

LOGS_DIR = "logs"


def _get_tz(cfg: Optional[Dict[str, Any]] = None) -> str:
    """从配置或默认获取时区。"""
    if cfg:
        return cfg.get("timezone", "America/Toronto")
    return "America/Toronto"


class JsonFormatter(logging.Formatter):
    """
    结构化 JSON 日志格式（P2-12）。
    每条日志输出一行 JSON，包含 ts / level / logger / msg，异常时追加 exc 字段。
    启用方式（任选其一）：
      - 环境变量：DATAFACTORY_LOG_FORMAT=json
      - 配置项：  logging.format: json
    """

    def __init__(self, tz: str = "America/Toronto"):
        super().__init__()
        self._tz = tz

    def format(self, record: logging.LogRecord) -> str:
        doc: Dict[str, Any] = {
            "ts": self._fmt_time(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False)

    def _fmt_time(self, record: logging.LogRecord) -> str:
        try:
            from zoneinfo import ZoneInfo
            ct = datetime.fromtimestamp(record.created, tz=ZoneInfo(self._tz))
        except Exception:
            ct = datetime.fromtimestamp(record.created)
        return ct.strftime("%Y-%m-%dT%H:%M:%S")


class _TZFormatter(logging.Formatter):
    """日志时间使用配置时区。"""

    def __init__(self, tz: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tz = tz

    def formatTime(self, record, datefmt=None):
        try:
            from zoneinfo import ZoneInfo
            ct = datetime.fromtimestamp(record.created, tz=ZoneInfo(self._tz))
        except Exception:
            ct = datetime.fromtimestamp(record.created)
        if datefmt:
            return ct.strftime(datefmt)
        return ct.strftime("%Y-%m-%d %H:%M:%S")


def setup_logging(base_dir: str, cfg: Optional[Dict[str, Any]] = None) -> None:
    """
    在 base_dir 下创建 logs/，配置文件日志。P1：RotatingFileHandler 轮转，时区从 cfg 读取。
    """
    base_dir = os.path.abspath(base_dir)
    log_dir = os.path.join(base_dir, LOGS_DIR)
    os.makedirs(log_dir, exist_ok=True)
    tz = _get_tz(cfg)
    try:
        from zoneinfo import ZoneInfo
        date_str = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")
    except Exception:
        date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"factory_{date_str}.log")

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    log_file_abs = os.path.abspath(log_file)
    for h in root.handlers:
        if getattr(h, "baseFilename", None) == log_file_abs:
            return
    lg_cfg = (cfg or {}).get("logging", {})
    max_bytes = lg_cfg.get("max_bytes", 10 * 1024 * 1024)
    backup_count = lg_cfg.get("backup_count", 5)
    fh = logging.handlers.RotatingFileHandler(
        log_file, encoding="utf-8", maxBytes=max_bytes, backupCount=backup_count
    )
    fh.setLevel(logging.INFO)
    log_fmt = lg_cfg.get("format", os.environ.get("DATAFACTORY_LOG_FORMAT", "text")).lower()
    if log_fmt == "json":
        fh.setFormatter(JsonFormatter(tz))
    else:
        fh.setFormatter(_TZFormatter(tz, "[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s"))
    root.addHandler(fh)
