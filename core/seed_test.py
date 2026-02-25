# core/seed_test.py — 测试前将 test_source 复制到 raw，支持反复自动化测试
"""Pipeline 会把 raw 里的视频 move 走，raw 会被清空。此模块从 test_source 复制到 raw。"""
import os
import shutil

VIDEO_EXT = (".mov", ".mp4", ".avi", ".mkv")


def seed_raw(source_dir: str, raw_dir: str, clear_raw_first: bool = True) -> int:
    """
    将 source_dir 下视频复制到 raw_dir。返回复制的文件数。
    clear_raw_first=True 时先清空 raw 下已有视频（避免重复累积）。
    """
    if not os.path.isdir(source_dir):
        return 0
    os.makedirs(raw_dir, exist_ok=True)

    if clear_raw_first:
        for name in os.listdir(raw_dir):
            if any(name.lower().endswith(ext) for ext in VIDEO_EXT):
                p = os.path.join(raw_dir, name)
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    count = 0
    for name in os.listdir(source_dir):
        if not any(name.lower().endswith(ext) for ext in VIDEO_EXT):
            continue
        src = os.path.join(source_dir, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(raw_dir, name)
        if os.path.exists(dst):
            base, ext = os.path.splitext(name)
            dst = os.path.join(raw_dir, f"{base}_copy{ext}")
        try:
            shutil.copy2(src, dst)
            count += 1
        except OSError:
            pass
    return count
