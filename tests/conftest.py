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


def pytest_addoption(parser):
    """简化命令：--unit 单元测试，--e2e 全链路（等价 tools.py --test）；均不捕获 stdout，便于看进度。"""
    parser.addoption("--unit", action="store_true", help="跑单元测试（等价 -m 'not slow'），输出进度")
    parser.addoption("--e2e", action="store_true", help="跑全链路 E2E（等价 tools.py --test，用 storage/test/original 跑整条 pipeline）")


def pytest_configure(config):
    """--unit / --e2e 时自动设 marker 表达式。"""
    if config.getoption("--e2e", default=False):
        config.option.markexpr = "full_pipeline"
    elif config.getoption("--unit", default=False):
        config.option.markexpr = "not slow"


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
    paths["db_file"] = db_file                          # 向后兼容保留
    paths["db_url"] = db_file                           # v3.2+：validate_config 检查此键

    cfg["paths"] = paths
    cfg["email_setting"] = {}  # 不发邮件
    cfg.setdefault("vision", {})["enabled"] = False  # 不跑 YOLO，加速
    cfg.setdefault("mlflow", {})["enabled"] = False  # 不写 MLflow

    return cfg


@pytest.fixture
def test_db(temp_dir: str) -> str:
    """临时 DB 路径，已 init_db。"""
    from db import db_tools

    db_path = os.path.join(temp_dir, "factory_test.db")
    db_tools.init_db(db_path)
    return db_path


@pytest.fixture(scope="session")
def test_video_root(project_root: str) -> str:
    """paths.test_source（测试源目录），smoke 需此目录下的 normal.mov 等。Path decoupling。"""
    from config import config_loader

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    return cfg.get("paths", {}).get("test_source") or os.path.join(project_root, "storage", "test", "original")


@pytest.fixture
def synthetic_image(tmp_path):
    """
    用 numpy 生成一张 100x100 灰色 JPEG，无需真实视频。
    返回文件路径。
    """
    import numpy as np
    try:
        import cv2
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        path = str(tmp_path / "synthetic.jpg")
        cv2.imwrite(path, img)
    except Exception:
        # cv2 不可用时用 PIL 回退
        from PIL import Image
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        path = str(tmp_path / "synthetic.jpg")
        img.save(path)
    return path


@pytest.fixture
def synthetic_batch_dir(tmp_path):
    """
    造一个标准 Batch 目录结构，含 inspection/ 和 refinery/ 子目录，
    每个子目录放若干合成图片 + 对应 .txt 伪标签。
    返回 batch_dir 路径。
    """
    import numpy as np

    batch_dir = tmp_path / "Batch_20240101_120000"
    inspection_dir = batch_dir / "inspection"
    refinery_dir = batch_dir / "refinery"
    inspection_dir.mkdir(parents=True)
    refinery_dir.mkdir(parents=True)

    def _write_img_and_label(directory, stem):
        try:
            import cv2
            img = np.full((100, 100, 3), 128, dtype=np.uint8)
            cv2.imwrite(str(directory / f"{stem}.jpg"), img)
        except Exception:
            from PIL import Image
            Image.new("RGB", (100, 100), (128, 128, 128)).save(str(directory / f"{stem}.jpg"))
        # 伪标签：一个框
        (directory / f"{stem}.txt").write_text("0 0.5 0.5 0.2 0.2\n")

    # inspection: 3 帧（模拟同一视频的连续帧）
    for i in range(3):
        _write_img_and_label(inspection_dir, f"video1_f{i:05d}")

    # refinery: 10 帧（用于测试抽样比例）
    for i in range(10):
        _write_img_and_label(refinery_dir, f"video2_f{i:05d}")

    return str(batch_dir)
