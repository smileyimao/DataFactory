# tests/unit/test_property_based.py
"""Property-based：随机配置下 validate_config 与路径解析的不变性。"""
import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis 未安装，跳过属性测试")
given = hypothesis.given
st = hypothesis.strategies

pytestmark = pytest.mark.unit


@given(
    min_br=st.floats(min_value=0, max_value=200),
    max_br=st.floats(min_value=0, max_value=255),
)
def test_validate_config_brightness_range(min_br, max_br):
    """min_brightness >= max_brightness 时必有错误。"""
    from config.config_loader import validate_config

    cfg = {
        "paths": {
            "raw_video": "/x",
            "data_warehouse": "/y",
            "db_file": "/z",
            "rejected_material": "/a",
            "redundant_archives": "/b",
            "batch_subdirs": {"reports": "r", "source": "s", "refinery": "f", "inspection": "i"},
        },
        "quality_thresholds": {"min_brightness": min_br, "max_brightness": max_br},
    }
    errs = validate_config(cfg)
    if min_br >= max_br:
        assert any("brightness" in e for e in errs)
    else:
        assert not any("brightness" in e for e in errs)


@given(
    gate=st.floats(min_value=-10, max_value=110),
)
def test_validate_config_gate_in_range(gate):
    """pass_rate_gate 超出 [0,100] 时必有错误。"""
    from config.config_loader import validate_config

    cfg = {
        "paths": {
            "raw_video": "/x",
            "data_warehouse": "/y",
            "db_file": "/z",
            "rejected_material": "/a",
            "redundant_archives": "/b",
            "batch_subdirs": {"reports": "r", "source": "s", "refinery": "f", "inspection": "i"},
        },
        "production_setting": {"pass_rate_gate": gate},
    }
    errs = validate_config(cfg)
    if gate < 0 or gate > 100:
        assert any("pass_rate_gate" in e for e in errs)
    else:
        assert not any("pass_rate_gate" in e for e in errs)


@given(
    dh=st.floats(min_value=0, max_value=100),
    dl=st.floats(min_value=0, max_value=100),
)
def test_validate_config_dual_gate_consistency(dh, dl):
    """dual_gate_high <= dual_gate_low 时必有错误。"""
    from config.config_loader import validate_config

    cfg = {
        "paths": {
            "raw_video": "/x",
            "data_warehouse": "/y",
            "db_file": "/z",
            "rejected_material": "/a",
            "redundant_archives": "/b",
            "batch_subdirs": {"reports": "r", "source": "s", "refinery": "f", "inspection": "i"},
        },
        "production_setting": {"dual_gate_high": dh, "dual_gate_low": dl},
    }
    errs = validate_config(cfg)
    if dh <= dl:
        assert any("dual_gate" in e for e in errs)
    else:
        assert not any("dual_gate" in e for e in errs)
