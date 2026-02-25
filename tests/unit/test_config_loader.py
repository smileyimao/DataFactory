# tests/unit/test_config_loader.py
"""config_loader.validate_config 单元测试。"""
import pytest

pytestmark = pytest.mark.unit


def test_validate_config_ok(test_cfg):
    """合法配置应返回空错误列表。"""
    from config.config_loader import validate_config

    errs = validate_config(test_cfg)
    assert errs == []


def test_validate_config_min_brightness_ge_max():
    """min_brightness >= max_brightness 应报错。"""
    from config.config_loader import validate_config

    cfg = {"paths": {"raw_video": "/x", "data_warehouse": "/y", "db_file": "/z", "rejected_material": "/a", "redundant_archives": "/b", "batch_subdirs": {"reports": "r", "source": "s", "refinery": "f", "inspection": "i"}}}
    cfg["quality_thresholds"] = {"min_brightness": 100, "max_brightness": 80}
    errs = validate_config(cfg)
    assert any("min_brightness" in e for e in errs)


def test_validate_config_gate_out_of_range():
    """pass_rate_gate 超出 [0,100] 应报错。"""
    from config.config_loader import validate_config

    cfg = {"paths": {"raw_video": "/x", "data_warehouse": "/y", "db_file": "/z", "rejected_material": "/a", "redundant_archives": "/b", "batch_subdirs": {"reports": "r", "source": "s", "refinery": "f", "inspection": "i"}}}
    cfg["production_setting"] = {"pass_rate_gate": 150}
    errs = validate_config(cfg)
    assert any("pass_rate_gate" in e for e in errs)


def test_validate_config_dual_gate_inconsistent():
    """dual_gate_high <= dual_gate_low 应报错。"""
    from config.config_loader import validate_config

    cfg = {"paths": {"raw_video": "/x", "data_warehouse": "/y", "db_file": "/z", "rejected_material": "/a", "redundant_archives": "/b", "batch_subdirs": {"reports": "r", "source": "s", "refinery": "f", "inspection": "i"}}}
    cfg["production_setting"] = {"dual_gate_high": 50, "dual_gate_low": 80}
    errs = validate_config(cfg)
    assert any("dual_gate" in e for e in errs)
