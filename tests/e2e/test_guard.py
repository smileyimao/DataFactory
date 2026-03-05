# tests/e2e/test_guard.py
"""端到端：Guard 模式逻辑验证。临时 cfg 启动、stop_event 退出，确保工业生产依赖的监控逻辑可通。"""
import copy
import os
import threading
import time
import pytest

pytestmark = pytest.mark.e2e


def test_guard_starts_and_stops_with_temp_cfg(project_root, temp_dir):
    """Guard 使用临时 cfg 能正常启动、通过 stop_event 退出。"""
    from config import config_loader
    from core import guard

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    paths = cfg.get("paths", {})

    temp_raw = os.path.join(temp_dir, "raw")
    temp_archive = os.path.join(temp_dir, "archive")
    temp_rejected = os.path.join(temp_dir, "rejected")
    temp_reports = os.path.join(temp_dir, "reports")
    temp_db = os.path.join(temp_dir, "factory_test.db")
    for d in (temp_raw, temp_archive, temp_rejected, temp_reports):
        os.makedirs(d, exist_ok=True)

    test_cfg = copy.deepcopy(cfg)
    test_cfg["paths"] = dict(paths)
    test_cfg["paths"]["raw_video"] = temp_raw
    test_cfg["paths"]["data_warehouse"] = temp_archive
    test_cfg["paths"]["rejected_material"] = temp_rejected
    test_cfg["paths"]["reports"] = temp_reports
    test_cfg["paths"]["db_file"] = temp_db
    test_cfg["email_setting"] = {}
    test_cfg.setdefault("vision", {})["enabled"] = False
    test_cfg.setdefault("ingest", {})["poll_interval_seconds"] = 0  # 关闭轮询，减少干扰

    stop_event = threading.Event()
    err = []

    def run():
        try:
            guard.run_guard(cfg=test_cfg, stop_event=stop_event)
        except Exception as e:
            err.append(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    time.sleep(3)  # 让 startup_scan 完成（raw 为空时很快）
    stop_event.set()
    t.join(timeout=5)

    assert not err, f"Guard 运行异常: {err}"
    assert not t.is_alive(), "Guard 应在 stop_event 后退出"


def test_guard_processes_existing_videos(project_root, temp_dir):
    """Guard 开机扫描能处理 raw 下已有视频（startup_scan + pipeline 逻辑）。"""
    from config import config_loader
    from core import guard
    from tests.helpers import seed_test

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    paths = cfg.get("paths", {})
    test_source = paths.get("test_source") or os.path.join(project_root, "storage", "test", "original")
    test_source = os.path.abspath(test_source)

    if not os.path.isdir(test_source):
        pytest.skip("paths.test_source 不存在，跳过")
    n = seed_test.seed_raw(test_source, os.path.join(temp_dir, "raw"), clear_raw_first=True)
    if n == 0:
        pytest.skip("paths.test_source 下无视频，跳过 Guard 处理测试")

    temp_raw = os.path.join(temp_dir, "raw")
    temp_archive = os.path.join(temp_dir, "archive")
    temp_rejected = os.path.join(temp_dir, "rejected")
    temp_redundant = os.path.join(temp_dir, "redundant")
    temp_reports = os.path.join(temp_dir, "reports")
    temp_db = os.path.join(temp_dir, "factory_test.db")
    for d in (temp_archive, temp_rejected, temp_redundant, temp_reports):
        os.makedirs(d, exist_ok=True)

    test_cfg = copy.deepcopy(cfg)
    test_cfg["paths"] = dict(paths)
    test_cfg["paths"]["raw_video"] = temp_raw
    test_cfg["paths"]["data_warehouse"] = temp_archive
    test_cfg["paths"]["rejected_material"] = temp_rejected
    test_cfg["paths"]["redundant_archives"] = temp_redundant
    test_cfg["paths"]["reports"] = temp_reports
    test_cfg["paths"]["db_file"] = temp_db
    test_cfg["paths"]["quarantine"] = os.path.join(temp_dir, "quarantine")
    test_cfg["paths"]["pending_review"] = os.path.join(temp_dir, "pending_review")
    test_cfg["paths"]["labeling_export"] = os.path.join(temp_dir, "for_labeling")
    test_cfg["paths"]["labeled_return"] = os.path.join(temp_dir, "labeled_return")
    test_cfg["paths"]["training"] = os.path.join(temp_dir, "training")
    test_cfg["paths"]["golden"] = os.path.join(temp_dir, "golden")
    test_cfg["paths"]["logs"] = os.path.join(temp_dir, "logs")
    for k in ["quarantine", "pending_review", "labeling_export", "labeled_return", "training", "golden", "logs"]:
        os.makedirs(test_cfg["paths"][k], exist_ok=True)
    test_cfg["email_setting"] = {}
    test_cfg.setdefault("vision", {})["enabled"] = False
    test_cfg.setdefault("ingest", {})["poll_interval_seconds"] = 0

    stop_event = threading.Event()
    err = []

    def run():
        try:
            guard.run_guard(cfg=test_cfg, stop_event=stop_event)
        except Exception as e:
            err.append(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    # Pipeline 可能需数十秒，最多等 120 秒
    for _ in range(120):
        if not t.is_alive():
            break
        archive_subdirs = [x for x in os.listdir(temp_archive) if os.path.isdir(os.path.join(temp_archive, x))]
        rejected_subdirs = [x for x in os.listdir(temp_rejected)] if os.path.isdir(temp_rejected) else []
        if archive_subdirs or any("_Fails" in x for x in rejected_subdirs):
            break
        time.sleep(1)
    stop_event.set()
    t.join(timeout=10)

    assert not err, f"Guard 运行异常: {err}"
    # 至少应有产出：archive 有 Batch_xxx 或 rejected 有 Batch_xxx_Fails
    archive_dirs = [x for x in os.listdir(temp_archive)] if os.path.isdir(temp_archive) else []
    rejected_dirs = [x for x in os.listdir(temp_rejected)] if os.path.isdir(temp_rejected) else []
    has_archive = any(x.startswith("Batch_") and not x.endswith("_Fails") for x in archive_dirs)
    has_rejected = any("_Fails" in x for x in rejected_dirs)
    assert has_archive or has_rejected, "Guard 应处理视频并产生 archive 或 rejected 批次"
