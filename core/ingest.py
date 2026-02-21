# core/ingest.py — 入场：解析或扫描得到待处理视频路径列表
import os
import glob
from typing import List, Optional

from engines import file_tools
from config import config_loader


def get_video_paths(
    cfg: dict,
    video_paths: Optional[List[str]] = None,
) -> List[str]:
    """
    若 video_paths 已传入则校验并返回绝对路径列表；
    否则从 paths.raw_video 扫描符合 extensions 的视频文件（排序）。
    """
    paths = cfg.get("paths", {})
    raw_dir = paths.get("raw_video", "")
    if video_paths is not None:
        out = [os.path.abspath(p) for p in video_paths if os.path.isfile(p)]
        return out
    exts = tuple(cfg.get("ingest", {}).get("video_extensions", [".mp4", ".mov", ".avi", ".mkv"]))
    return file_tools.list_video_paths(raw_dir, exts)
