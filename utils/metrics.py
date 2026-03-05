# utils/metrics.py — P2 简单 counters，便于告警与可观测
"""
线程安全的简单计数器，供 pipeline 各阶段递增。
可后续扩展为 Prometheus 或导出到 MLflow。
"""
import threading
from typing import Dict

_lock = threading.Lock()
_counters: Dict[str, int] = {}


def inc(name: str, delta: int = 1) -> None:
    """递增计数器。"""
    with _lock:
        _counters[name] = _counters.get(name, 0) + delta


def get_all() -> Dict[str, int]:
    """获取所有计数器（快照）。"""
    with _lock:
        return dict(_counters)
