# engines/file_tools.py — 文件稳定性、路径列表，只干活不决策
import os
import time
from typing import List, Tuple

VIDEO_EXT_DEFAULT: Tuple[str, ...] = (".mp4", ".mov", ".avi", ".mkv")


def wait_file_stable(
    file_path: str,
    check_interval: float = 1.0,
    min_stable_sec: int = 2,
) -> None:
    """等待文件大小在 min_stable_sec 秒内不变（写入稳定）。"""
    last_size = -1
    stable_count = 0
    while True:
        try:
            size = os.path.getsize(file_path)
            if size == last_size and size > 0:
                stable_count += 1
                if stable_count >= min_stable_sec:
                    return
            else:
                stable_count = 0
            last_size = size
        except (FileNotFoundError, OSError):
            return
        time.sleep(check_interval)


def list_video_paths(
    directory: str,
    extensions: Tuple[str, ...] = VIDEO_EXT_DEFAULT,
) -> List[str]:
    """返回目录下所有扩展名为 extensions 的文件的绝对路径（排序）。"""
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        return []
    paths: List[str] = []
    for name in sorted(os.listdir(directory)):
        if any(name.lower().endswith(ext) for ext in extensions):
            p = os.path.join(directory, name)
            if os.path.isfile(p):
                paths.append(os.path.abspath(p))
    return paths
