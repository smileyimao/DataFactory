# tests/e2e/test_main_full_pipeline.py
"""
端到端全链路测试：直接调用 tools.run_full_pipeline_test()，
用 storage/test/original/ 里的视频跑整条 pipeline（Ingest → QC → Archive → 报告）。
临时环境，不污染真实 storage/DB，测完自动清理。

使用方式：pytest tests/ --e2e
"""
import os
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.full_pipeline, pytest.mark.slow]

VIDEO_EXT = (".mov", ".mp4", ".avi", ".mkv")


def _test_source_has_videos(project_root: str) -> bool:
    """检查 paths.test_source 下是否有视频。"""
    from config import config_loader

    config_loader.set_base_dir(project_root)
    cfg = config_loader.load_config()
    src = cfg.get("paths", {}).get("test_source") or os.path.join(project_root, "storage", "test", "original")
    if not os.path.isdir(src):
        return False
    for name in os.listdir(src):
        if os.path.isfile(os.path.join(src, name)) and any(name.lower().endswith(ext) for ext in VIDEO_EXT):
            return True
    return False


def test_main_test_mode_full_pipeline(project_root, capfd):
    """全链路 E2E：临时环境跑整条 pipeline，等价 python tools.py --test。"""
    if not _test_source_has_videos(project_root):
        pytest.skip("paths.test_source 下无视频，跳过全链路测试。请在 storage/test/original/ 放入测试视频。")

    with capfd.disabled():
        from tools import run_full_pipeline_test
        run_full_pipeline_test()
