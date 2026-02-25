# tests/unit/test_quality_tools.py
"""quality_tools.decide_env 单元测试。"""
import sys

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        sys.platform == "darwin",
        reason="cv2/numpy Floating-point exception on macOS (numpy._mac_os_check)",
    ),
]


@pytest.fixture
def base_cfg():
    """质检阈值默认值。"""
    return {
        "min_brightness": 55,
        "max_brightness": 225,
        "min_blur_score": 20,
        "min_contrast": 15,
        "max_contrast": 100,
        "max_jitter": 35,
    }


def test_decide_env_normal(base_cfg):
    """正常帧应返回 Normal。"""
    from engines.quality_tools import decide_env

    raw = {"br": 120, "bl": 50, "jitter": 5, "std_dev": 40}
    assert decide_env(raw, base_cfg) == "Normal"


def test_decide_env_too_dark(base_cfg):
    """过暗应返回 Too Dark。"""
    from engines.quality_tools import decide_env

    raw = {"br": 30, "bl": 50, "jitter": 0, "std_dev": 40}
    assert decide_env(raw, base_cfg) == "Too Dark"


def test_decide_env_blurry(base_cfg):
    """模糊应返回 Blurry。"""
    from engines.quality_tools import decide_env

    raw = {"br": 120, "bl": 5, "jitter": 0, "std_dev": 40}
    assert decide_env(raw, base_cfg) == "Blurry"


def test_decide_env_low_contrast(base_cfg):
    """低对比度应返回 Low Contrast。"""
    from engines.quality_tools import decide_env

    raw = {"br": 120, "bl": 50, "jitter": 0, "std_dev": 5}
    assert decide_env(raw, base_cfg) == "Low Contrast"


def test_decide_env_high_jitter(base_cfg):
    """高抖动应返回 High Jitter。"""
    from engines.quality_tools import decide_env

    raw = {"br": 120, "bl": 10, "jitter": 50, "std_dev": 40}
    assert decide_env(raw, base_cfg) == "High Jitter"
