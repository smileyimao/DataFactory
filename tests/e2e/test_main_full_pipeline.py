# tests/e2e/test_main_full_pipeline.py
"""端到端：调用 main.py --test 跑全链路，验证临时环境、无异常退出。"""
import os
import subprocess
import sys
import pytest

pytestmark = pytest.mark.e2e

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
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


def test_main_test_mode_full_pipeline(project_root):
    """main.py --test：临时环境跑全链路，应正常退出（exit 0）。"""
    if not _test_source_has_videos(project_root):
        pytest.skip("paths.test_source 下无视频，跳过全链路测试。请在 storage/test/original/ 放入测试视频。")

    result = subprocess.run(
        [sys.executable, "main.py", "--test"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    assert result.returncode == 0, (
        f"main.py --test 异常退出 {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
