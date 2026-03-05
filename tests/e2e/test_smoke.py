# tests/e2e/test_smoke.py
"""端到端冒烟测试：QC 全流程，需 paths.test_source 下测试视频（normal.mov 等）。Path decoupling。"""
import os
import shutil
import sys
import tempfile
import pytest

pytestmark = pytest.mark.e2e

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
VIDEO_EXT = (".mov", ".mp4", ".avi", ".mkv")
ORIGINAL_VIDEOS = ["normal.mov", "jitter.mov", "black.mov"]
ORIGINAL_IMAGE = "image.jpg"
FINGERPRINT_CHECK_FILES = ["normal.mov", "jitter.mov", "black.mov"]
EXPECTED = {
    "normal.mov": "PASS",
    "jitter.mov": "REVIEW",
    "black.mov": "REJECTED",
    "fake_from_img.mov": "REJECTED_CORRUPTED",
    "incomplete_stream.mov": "REJECTED_CORRUPTED",
    "zero_byte_video.mov": "REJECTED_CORRUPTED",
    "normal_duplicate.mov": "DUPLICATE",
}


def _get_test_source(project_root: str) -> str:
    """从配置读取 paths.test_source，实现 path decoupling。"""
    from config import config_loader

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    return cfg.get("paths", {}).get("test_source") or os.path.join(project_root, "storage", "test", "original")


def _get_test_root(project_root: str) -> str:
    """test_source 的父目录，用于生成派生物料。"""
    return os.path.dirname(_get_test_source(project_root))


def _find_original(path_dir: str, name: str) -> str:
    if not os.path.isdir(path_dir):
        return ""
    lower = name.lower()
    for entry in os.listdir(path_dir):
        if entry.lower() == lower:
            return os.path.join(path_dir, entry)
    return ""


def _ensure_test_data(project_root: str) -> bool:
    """从 test_source 生成派生物料到 test_root（清空非 original 内容）。"""
    test_root = _get_test_root(project_root)
    original_dir = _get_test_source(project_root)

    if not os.path.isdir(test_root):
        os.makedirs(test_root, exist_ok=True)
    for name in os.listdir(test_root):
        if name == "original":
            continue
        path = os.path.join(test_root, name)
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)

    if not os.path.isdir(original_dir):
        return False
    missing = [f for f in ORIGINAL_VIDEOS + [ORIGINAL_IMAGE] if not _find_original(original_dir, f)]
    if missing:
        pytest.skip(f"原始素材缺失: {missing}，跳过 smoke 测试")

    for name in ORIGINAL_VIDEOS:
        src = _find_original(original_dir, name)
        if src:
            shutil.copy2(src, os.path.join(test_root, name.lower()))
    src_img = _find_original(original_dir, ORIGINAL_IMAGE)
    if src_img:
        shutil.copy2(src_img, os.path.join(test_root, "fake_from_img.mov"))
    src_normal = _find_original(original_dir, "normal.mov")
    if src_normal:
        with open(src_normal, "rb") as f:
            chunk = f.read(1024 * 1024)
        with open(os.path.join(test_root, "incomplete_stream.mov"), "wb") as f:
            f.write(chunk)
    with open(os.path.join(test_root, "zero_byte_video.mov"), "wb") as f:
        f.write(b"")
    if src_normal:
        shutil.copy2(src_normal, os.path.join(test_root, "normal_duplicate.mov"))
    return True


def _check_fingerprints(project_root: str) -> None:
    sys.path.insert(0, project_root)
    from utils import fingerprinter

    test_root = _get_test_root(project_root)
    paths = []
    for name in FINGERPRINT_CHECK_FILES:
        p = os.path.join(test_root, name)
        if os.path.isfile(p):
            paths.append((name, p))
    if len(paths) < 2:
        return
    fingerprints = [(n, fingerprinter.compute(p) or "") for n, p in paths]
    seen = {}
    for name, fp in fingerprints:
        if fp and fp in seen:
            pytest.fail(f"指纹雷同: {seen[fp]} 与 {name}")
        if fp:
            seen[fp] = name


def _actual_category(item) -> str:
    if item.get("is_duplicate"):
        return "DUPLICATE"
    if item.get("passed"):
        return "PASS"
    return "REJECTED"


def test_smoke_qc_full_flow(project_root):
    """Smoke：QC 全流程，断言 PASS/REVIEW/REJECTED/DUPLICATE。路径从 config 读取。"""
    if not _ensure_test_data(project_root):
        pytest.skip("无法准备测试物料")
    _check_fingerprints(project_root)

    from config import config_loader
    from core import qc_engine
    from db import db_tools

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    paths_cfg = cfg.get("paths", {})
    test_root = _get_test_root(project_root)

    with tempfile.TemporaryDirectory(prefix="smoke_test_") as tmp:
        temp_raw = os.path.join(tmp, "raw")
        temp_warehouse = os.path.join(tmp, "warehouse")
        temp_db = os.path.join(tmp, "factory_test.db")
        os.makedirs(temp_raw, exist_ok=True)
        os.makedirs(temp_warehouse, exist_ok=True)

        for name in os.listdir(test_root):
            if name == "original":
                continue
            p = os.path.join(test_root, name)
            if not os.path.isfile(p) or not any(name.lower().endswith(ext) for ext in VIDEO_EXT):
                continue
            dest_name = name.lower() if name.lower().endswith(".mov") else (os.path.splitext(name)[0] + ".mov")
            shutil.copy2(p, os.path.join(temp_raw, dest_name.lower()))

        all_paths = [os.path.join(temp_raw, n) for n in sorted(os.listdir(temp_raw))]
        normal_path = next((p for p in all_paths if os.path.basename(p).lower() == "normal.mov"), None)
        other_paths = [p for p in all_paths if p != normal_path]

        cfg = dict(cfg)
        cfg["paths"] = dict(paths_cfg)
        cfg["paths"]["raw_video"] = temp_raw
        cfg["paths"]["data_warehouse"] = temp_warehouse
        cfg["paths"]["db_file"] = temp_db
        cfg["paths"]["reports"] = os.path.join(tmp, "reports")
        os.makedirs(cfg["paths"]["reports"], exist_ok=True)
        cfg["email_setting"] = {}
        cfg.setdefault("production_setting", {})["pass_rate_gate"] = 50.0
        cfg.setdefault("vision", {})["enabled"] = False

        db_tools.init_db(temp_db)
        results = {}

        if normal_path and os.path.isfile(normal_path):
            qc_archive, qualified, blocked, _, path_info = qc_engine.run_qc(cfg, [normal_path])
            for item in qc_archive:
                results[item["filename"]] = _actual_category(item)
            batch_id = path_info.get("batch_id", "")
            for x in qc_archive:
                if x.get("fingerprint"):
                    db_tools.record_production(temp_db, batch_id, x["fingerprint"], x["score"], "SUCCESS")
                    break

        if other_paths:
            remaining = [p for p in other_paths if os.path.isfile(p)]
            if remaining:
                qc_archive, _, _, _, _ = qc_engine.run_qc(cfg, remaining)
                for item in qc_archive:
                    results[item["filename"]] = _actual_category(item)

    for filename, expected in EXPECTED.items():
        actual = results.get(filename)
        if actual is None:
            pytest.fail(f"{filename}: expected {expected}, got MISSING")
        ok = False
        if expected == "REVIEW":
            ok = actual in ("PASS", "REJECTED")
        elif expected == "REJECTED_CORRUPTED":
            ok = actual == "REJECTED"
        else:
            ok = actual == expected
        if not ok:
            pytest.fail(f"{filename}: expected {expected}, got {actual}")
