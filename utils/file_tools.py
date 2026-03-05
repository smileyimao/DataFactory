# utils/file_tools.py — 文件稳定性、路径列表，只干活不决策
import os
import time
from typing import List, Tuple

VIDEO_EXT_DEFAULT: Tuple[str, ...] = (".mp4", ".mov", ".avi", ".mkv")
IMAGE_EXT_DEFAULT: Tuple[str, ...] = (".jpg", ".jpeg", ".png")


def sanitize_filename(name: str) -> str:
    """文件名去空格（空格→下划线），避免 CVAT/YOLO 等下游解析时按空格截断。"""
    return name.replace(" ", "_")


def detect_content_mode(
    directory: str,
    image_extensions: Tuple[str, ...] = IMAGE_EXT_DEFAULT,
    video_extensions: Tuple[str, ...] = VIDEO_EXT_DEFAULT,
) -> str:
    """
    递归扫描 raw 目录，统计图片/视频数量，自动判定通路。
    返回 "image"、"video" 或 "both"。两者都有时返回 "both"；仅一种时按数量多者；空目录默认 video。
    """
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        return "video"
    n_img, n_vid = 0, 0
    for root, _, files in os.walk(directory):
        for name in files:
            low = name.lower()
            if any(low.endswith(ext) for ext in image_extensions):
                n_img += 1
            elif any(low.endswith(ext) for ext in video_extensions):
                n_vid += 1
    if n_img > 0 and n_vid > 0:
        return "both"
    if n_img > n_vid:
        return "image"
    return "video"


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


def list_video_paths_recursive(
    directory: str,
    extensions: Tuple[str, ...] = VIDEO_EXT_DEFAULT,
) -> List[str]:
    """递归扫描目录及子目录下所有视频文件，返回绝对路径（排序）。"""
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        return []
    paths: List[str] = []
    for root, _, files in os.walk(directory):
        for name in sorted(files):
            if any(name.lower().endswith(ext) for ext in extensions):
                p = os.path.join(root, name)
                if os.path.isfile(p):
                    paths.append(os.path.abspath(p))
    return paths


def list_image_paths_recursive(
    directory: str,
    extensions: Tuple[str, ...] = (".jpg", ".jpeg", ".png"),
) -> List[str]:
    """递归扫描目录及子目录下所有图片文件，返回绝对路径（排序）。"""
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        return []
    paths: List[str] = []
    for root, _, files in os.walk(directory):
        for name in sorted(files):
            if any(name.lower().endswith(ext) for ext in extensions):
                p = os.path.join(root, name)
                if os.path.isfile(p):
                    paths.append(os.path.abspath(p))
    return paths


def list_media_paths_recursive(
    directory: str,
    image_extensions: Tuple[str, ...] = IMAGE_EXT_DEFAULT,
    video_extensions: Tuple[str, ...] = VIDEO_EXT_DEFAULT,
) -> List[str]:
    """递归扫描目录下所有图片+视频，返回绝对路径（排序）。混合模式用。"""
    imgs = list_image_paths_recursive(directory, image_extensions)
    vids = list_video_paths_recursive(directory, video_extensions)
    return sorted(imgs + vids)
