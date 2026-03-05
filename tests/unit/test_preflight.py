# tests/unit/test_preflight.py
"""Pre-flight：非法配置时系统拒绝启动。"""
import pytest

pytestmark = pytest.mark.unit


def _minimal_valid_cfg():
    """最小合法 paths，供组合非法项。"""
    return {
        "paths": {
            "raw_video": "/x",
            "data_warehouse": "/y",
            "db_file": "/z",
            "rejected_material": "/a",
            "redundant_archives": "/b",
            "batch_subdirs": {"reports": "r", "source": "s", "refinery": "f", "inspection": "i"},
        }
    }


def test_validate_config_dual_gate_inconsistent_returns_error():
    """dual_gate_high <= dual_gate_low 时 validate_config 返回非空错误。"""
    from config.config_loader import validate_config

    cfg = _minimal_valid_cfg()
    cfg["production_setting"] = {"dual_gate_high": 50, "dual_gate_low": 80}
    errs = validate_config(cfg)
    assert len(errs) > 0
    assert any("dual_gate" in e for e in errs)


def test_startup_self_check_refuses_invalid_config():
    """run_startup_self_check 在非法配置时返回 False（Pre-flight 拒绝启动）。"""
    from utils.startup import run_startup_self_check

    cfg = _minimal_valid_cfg()
    cfg["production_setting"] = {"dual_gate_high": 50, "dual_gate_low": 80}
    result = run_startup_self_check(cfg)
    assert result is False


def test_startup_self_check_passes_valid_config(test_cfg):
    """合法配置时 run_startup_self_check 返回 True。"""
    from utils.startup import run_startup_self_check

    assert run_startup_self_check(test_cfg) is True
