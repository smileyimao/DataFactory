# utils/time_utils.py — 时区工具（P1 配置驱动，poka yoke）
"""从配置读取时区，避免硬编码。无 cfg 时回退默认。"""
from datetime import datetime
from typing import Any, Dict

_DEFAULT_TZ = "America/Toronto"


def get_tz(cfg: Dict[str, Any] = None) -> str:
    """返回配置的时区字符串，如 America/Toronto。"""
    if cfg:
        return cfg.get("timezone", _DEFAULT_TZ)
    return _DEFAULT_TZ


def now_toronto(cfg: Dict[str, Any] = None) -> datetime:
    """返回当前时间（配置时区）。cfg 可选，无则用默认 America/Toronto。"""
    try:
        from zoneinfo import ZoneInfo
        tz = get_tz(cfg) if cfg else _DEFAULT_TZ
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.now()


def format_ts(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化 datetime 为字符串。"""
    return dt.strftime(fmt)
