# tests/conftest.py — 共享 fixture
"""
pytest 共享 fixture：项目根、临时目录、测试用 config、临时 DB。
"""
import os
import sys
import tempfile
import shutil
from typing import Dict, Any, Generator

import pytest

# 确保项目根在 path 中
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 测试环境标记
os.environ.setdefault("DATAFLOW_TEST", "1")


@pytest.fixture(scope="session")
def project_root() -> str:
    """项目根目录。"""
    return PROJECT_ROOT


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """临时目录，测完自动清理。"""
    with tempfile.TemporaryDirectory(prefix="datafactory_test_") as d:
        yield d


@pytest.fixture
def test_cfg(project_root: str, temp_dir: str) -> Dict[str, Any]:
    """
    测试用 config：paths 指向临时目录，email 关闭，vision 关闭（加速）。
    """
    from config import config_loader

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    cfg = dict(cfg)
    paths = dict(cfg.get("paths", {}))

    raw = os.path.join(temp_dir, "raw")
    warehouse = os.path.join(temp_dir, "warehouse")
    rejected = os.path.join(temp_dir, "rejected")
    redundant = os.path.join(temp_dir, "redundant")
    reports = os.path.join(temp_dir, "reports")
    db_file = os.path.join(temp_dir, "factory_test.db")

    for d in (raw, warehouse, rejected, redundant, reports):
        os.makedirs(d, exist_ok=True)

    paths["raw_video"] = raw
    paths["data_warehouse"] = warehouse
    paths["rejected_material"] = rejected
    paths["redundant_archives"] = redundant
    paths["reports"] = reports
    paths["db_file"] = db_file

    cfg["paths"] = paths
    cfg["email_setting"] = {}  # 不发邮件
    cfg.setdefault("vision", {})["enabled"] = False  # 不跑 YOLO，加速
    cfg.setdefault("mlflow", {})["enabled"] = False  # 不写 MLflow

    return cfg


@pytest.fixture
def test_db(temp_dir: str) -> str:
    """临时 DB 路径，已 init_db。"""
    from engines import db_tools

    db_path = os.path.join(temp_dir, "factory_test.db")
    db_tools.init_db(db_path)
    return db_path


@pytest.fixture(scope="session")
def test_video_root(project_root: str) -> str:
    """storage/test/original/ 路径，smoke 需此目录下的 normal.mov 等。"""
    return os.path.join(project_root, "storage", "test", "original")
