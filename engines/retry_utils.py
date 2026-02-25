# engines/retry_utils.py — 文件操作重试（P0 工业级）
"""
对 shutil.move/copy 等易受瞬时故障影响的操作提供重试。
配置：retry.max_attempts, retry.backoff_seconds
"""
import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    operation: str = "operation",
    context: str = "",
) -> T:
    """
    执行 fn，失败时按 backoff 重试。最后一次失败时抛出。
    """
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except (OSError, IOError, PermissionError) as e:
            last_err = e
            if attempt < max_attempts:
                wait = backoff_seconds * attempt
                logger.warning(
                    "%s 失败 (attempt %d/%d): %s，%s 秒后重试",
                    operation, attempt, max_attempts, e, wait,
                    extra={"context": context} if context else {},
                )
                time.sleep(wait)
            else:
                logger.error(
                    "%s 最终失败 (%d 次尝试): %s",
                    operation, max_attempts, e,
                    extra={"context": context} if context else {},
                )
                raise
    raise last_err  # type: ignore


def safe_move_with_retry(
    src: str,
    dest: str,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> bool:
    """
    带重试的 shutil.move。成功返回 True，失败记录日志并返回 False（不抛异常，便于批量操作继续）。
    """
    import shutil
    try:
        with_retry(
            lambda: shutil.move(src, dest),
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
            operation="shutil.move",
            context=f"{src} -> {dest}",
        )
        return True
    except (OSError, IOError, PermissionError) as e:
        logger.exception("文件移动失败（已重试）: %s -> %s: %s", src, dest, e)
        try:
            from engines import metrics
            metrics.inc("file_move_errors_total")
        except Exception:
            pass
        return False


def safe_copy_with_retry(
    src: str,
    dest: str,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> bool:
    """
    带重试的 shutil.copy2。成功返回 True，失败记录日志并返回 False（不抛异常，便于批量操作继续）。
    用于 copy_to_batch_labeled、merge_to_training 等，防止磁盘满/权限不足时静默失败。
    """
    import shutil
    try:
        with_retry(
            lambda: shutil.copy2(src, dest),
            max_attempts=max_attempts,
            backoff_seconds=backoff_seconds,
            operation="shutil.copy2",
            context=f"{src} -> {dest}",
        )
        return True
    except (OSError, IOError, PermissionError) as e:
        logger.warning(
            "文件拷贝失败（已重试 %d 次）: %s -> %s: %s",
            max_attempts, src, dest, e,
        )
        try:
            from engines import metrics
            metrics.inc("file_copy_errors_total")
        except Exception:
            pass
        return False
