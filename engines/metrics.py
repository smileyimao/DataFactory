# engines/metrics.py — P2 简单 counters，便于告警与可观测
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


def get(name: str) -> int:
    """获取计数值。"""
    with _lock:
        return _counters.get(name, 0)


def get_all() -> Dict[str, int]:
    """获取所有计数器（快照）。"""
    with _lock:
        return dict(_counters)


def reset(name: str = None) -> None:
    """重置计数器。name 为 None 时重置全部。"""
    with _lock:
        if name is None:
            _counters.clear()
        else:
            _counters.pop(name, None)
