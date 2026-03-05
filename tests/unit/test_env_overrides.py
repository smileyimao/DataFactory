# tests/unit/test_env_overrides.py
"""环境变量覆盖：DATAFACTORY_* 覆盖 paths，验证 Environment Agnostic。"""
import os
import pytest

pytestmark = pytest.mark.unit


def test_env_override_raw_video(monkeypatch, project_root):
    """DATAFACTORY_RAW_VIDEO 覆盖 paths.raw_video。"""
    from config import config_loader

    custom_path = "/custom/production/raw"
    monkeypatch.setenv("DATAFACTORY_RAW_VIDEO", custom_path)
    monkeypatch.delenv("DATAFACTORY_DATA_WAREHOUSE", raising=False)
    monkeypatch.delenv("DATAFACTORY_DB_FILE", raising=False)
    monkeypatch.delenv("DATAFACTORY_REJECTED_MATERIAL", raising=False)
    monkeypatch.delenv("DATAFACTORY_REDUNDANT_ARCHIVES", raising=False)

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    assert cfg["paths"]["raw_video"] == custom_path


def test_env_override_data_warehouse(monkeypatch, project_root):
    """DATAFACTORY_DATA_WAREHOUSE 覆盖 paths.data_warehouse。"""
    from config import config_loader

    custom_path = "/mnt/edge/archive"
    monkeypatch.setenv("DATAFACTORY_DATA_WAREHOUSE", custom_path)
    monkeypatch.delenv("DATAFACTORY_RAW_VIDEO", raising=False)

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    assert cfg["paths"]["data_warehouse"] == custom_path


def test_env_override_db_url(monkeypatch, project_root):
    """DATABASE_URL 覆盖 paths.db_url（v3.2+ PG 模式）。"""
    from config import config_loader

    custom_url = "postgresql://user:pass@localhost:5432/testdb"
    monkeypatch.setenv("DATABASE_URL", custom_url)
    monkeypatch.delenv("DATAFACTORY_RAW_VIDEO", raising=False)

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    assert cfg["paths"]["db_url"] == custom_url


def test_env_key_naming():
    """DATAFACTORY_ + key 大写 + 下划线，如 raw_video -> DATAFACTORY_RAW_VIDEO。"""
    # 文档化：key 中 . 替换为 _，全大写
    assert "DATAFACTORY_RAW_VIDEO" == "DATAFACTORY_" + "raw_video".upper().replace(".", "_")
