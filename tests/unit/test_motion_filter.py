# tests/unit/test_motion_filter.py — motion_filter 单元测试
"""验证运动量计算和静止帧判断逻辑。"""
import pytest
import numpy as np

pytestmark = pytest.mark.unit

cv2 = pytest.importorskip("cv2", reason="cv2 不可用，跳过 motion_filter 测试")


def _gray(value: int, size=(50, 50)) -> np.ndarray:
    """生成指定灰度值的单色帧。"""
    return np.full(size, value, dtype=np.uint8)


def _bgr(value: int, size=(50, 50, 3)) -> np.ndarray:
    """生成指定灰度值的 BGR 帧。"""
    return np.full(size, value, dtype=np.uint8)


class TestComputeMotionScore:
    def test_no_prev_frame_returns_255(self):
        """无前一帧时，运动量应为 255（视为有运动，不跳过）。"""
        from vision.motion_filter import compute_motion_score

        score = compute_motion_score(None, _bgr(128))
        assert score == 255.0

    def test_identical_frames_zero_motion(self):
        """完全相同帧，运动量应接近 0。"""
        from vision.motion_filter import compute_motion_score

        frame = _bgr(100)
        prev = _gray(100)
        score = compute_motion_score(prev, frame)
        assert score < 1.0

    def test_different_frames_nonzero_motion(self):
        """明显不同的帧，运动量应大于 0。"""
        from vision.motion_filter import compute_motion_score

        prev = _gray(50)
        curr = _bgr(200)
        score = compute_motion_score(prev, curr)
        assert score > 0.0

    def test_shape_mismatch_returns_255(self):
        """prev 和 curr 尺寸不一致时，视为有运动。"""
        from vision.motion_filter import compute_motion_score

        prev = _gray(128, size=(30, 30))
        curr = _bgr(128, size=(50, 50, 3))
        score = compute_motion_score(prev, curr)
        assert score == 255.0

    def test_empty_frame_returns_zero(self):
        """空帧返回 0，不崩溃。"""
        from vision.motion_filter import compute_motion_score

        score = compute_motion_score(None, np.array([]))
        assert score == 0.0


class TestShouldRunDetection:
    def test_high_motion_triggers_detection(self):
        """运动量超过阈值时，应该运行检测。"""
        from vision.motion_filter import should_run_detection

        prev = _gray(0)
        curr = _bgr(255)
        should_run, score = should_run_detection(prev, curr, motion_threshold=5.0)
        assert should_run is True
        assert score > 5.0

    def test_static_scene_skips_detection(self):
        """静止场景运动量低，不应运行检测。"""
        from vision.motion_filter import should_run_detection

        frame = _bgr(128)
        prev = _gray(128)
        should_run, score = should_run_detection(prev, frame, motion_threshold=10.0)
        assert should_run is False

    def test_no_prev_always_runs(self):
        """无前一帧时 score=255，只要阈值低于 255 就应运行检测。"""
        from vision.motion_filter import should_run_detection

        # compute_motion_score(None, ...) 返回 255.0，阈值设 200 确保触发
        should_run, score = should_run_detection(None, _bgr(128), motion_threshold=200.0)
        assert should_run is True
        assert score == 255.0
