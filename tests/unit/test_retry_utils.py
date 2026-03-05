# tests/unit/test_retry_utils.py
"""retry_utils：OSError/PermissionError 下的重试与降级。"""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


def test_with_retry_raises_after_exhausted():
    """重试耗尽后抛出 OSError。"""
    from utils.retry_utils import with_retry

    call_count = 0

    def failing():
        nonlocal call_count
        call_count += 1
        raise OSError("Permission denied")

    with pytest.raises(OSError):
        with_retry(failing, max_attempts=3, backoff_seconds=0.01)

    assert call_count == 3


def test_with_retry_succeeds_on_second_try():
    """第二次重试成功则返回。"""
    from utils.retry_utils import with_retry

    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise PermissionError("Temp failure")
        return 42

    result = with_retry(flaky, max_attempts=3, backoff_seconds=0.01)
    assert result == 42
    assert call_count == 2


def test_safe_move_with_retry_returns_false_on_oserror():
    """safe_move_with_retry 在 OSError 后返回 False，不抛异常。"""
    from utils.retry_utils import safe_move_with_retry

    with patch("shutil.move", side_effect=OSError("Permission denied")):
        result = safe_move_with_retry("/src", "/dest", max_attempts=2, backoff_seconds=0.01)

    assert result is False


def test_safe_move_with_retry_returns_false_on_permission_error():
    """safe_move_with_retry 在 PermissionError 后返回 False。"""
    from utils.retry_utils import safe_move_with_retry

    with patch("shutil.move", side_effect=PermissionError("Access denied")):
        result = safe_move_with_retry("/src", "/dest", max_attempts=2, backoff_seconds=0.01)

    assert result is False


def test_safe_move_with_retry_returns_true_on_success():
    """safe_move_with_retry 成功时返回 True。"""
    from utils.retry_utils import safe_move_with_retry

    with patch("shutil.move"):
        result = safe_move_with_retry("/src", "/dest")

    assert result is True


def test_safe_copy_with_retry_returns_false_on_oserror():
    """safe_copy_with_retry 在 OSError（如磁盘满）后返回 False，打 warning 不抛异常。"""
    from utils.retry_utils import safe_copy_with_retry

    with patch("shutil.copy2", side_effect=OSError("No space left on device")):
        result = safe_copy_with_retry("/src/img.jpg", "/dest/img.jpg", max_attempts=2, backoff_seconds=0.01)

    assert result is False


def test_safe_copy_with_retry_returns_true_on_success():
    """safe_copy_with_retry 成功时返回 True。"""
    from utils.retry_utils import safe_copy_with_retry

    with patch("shutil.copy2"):
        result = safe_copy_with_retry("/src/img.jpg", "/dest/img.jpg")

    assert result is True
