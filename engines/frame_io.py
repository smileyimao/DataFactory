# engines/frame_io.py — I-帧抽取：只解 I-帧减少解码量
"""用 ffprobe 获取 I-帧位置，只读取这些帧。若无 ffprobe 则回退到按秒抽帧。"""
import logging
import subprocess
from typing import List, Optional, Tuple

import cv2

logger = logging.getLogger(__name__)


def get_i_frame_timestamps(video_path: str) -> Optional[List[float]]:
    """
    用 ffprobe 获取 I-帧时间戳（秒）。失败返回 None。
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "frame=key_frame,pkt_pts_time",
            "-of", "csv=p=0",
            video_path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=30)
        timestamps = []
        for line in out.strip().splitlines():
            parts = line.split(",")
            if len(parts) >= 2 and parts[0].strip() == "1":
                try:
                    ts = float(parts[1].strip())
                    timestamps.append(ts)
                except ValueError:
                    continue
        return timestamps if timestamps else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.debug("ffprobe I-frame 获取失败 %s: %s", video_path, e)
        return None


def sample_i_frames(
    video_path: str,
    sample_seconds: float,
    max_frames: Optional[int] = None,
    max_duration_seconds: Optional[float] = None,
) -> List[Tuple[any, int]]:
    """
    只抽取 I-帧，按 sample_seconds 间隔筛选。
    返回 [(frame_bgr, frame_idx), ...]。
    若 ffprobe 不可用或失败，回退到按秒抽帧。
    """
    if not video_path or not __import__("os").path.isfile(video_path):
        return []
    cap = cv2.VideoCapture(video_path)
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25

    timestamps = get_i_frame_timestamps(video_path)
    if not timestamps:
        cap.release()
        return _fallback_sample(video_path, sample_seconds, max_frames)

    if max_duration_seconds is not None:
        timestamps = [t for t in timestamps if t <= max_duration_seconds]
    selected_ts = []
    last_ts = -float("inf")
    for ts in timestamps:
        if ts - last_ts >= sample_seconds:
            selected_ts.append(ts)
            last_ts = ts
    if max_frames and len(selected_ts) > max_frames:
        selected_ts = selected_ts[:max_frames]

    out = []
    for ts in selected_ts:
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        frame_idx = int(ts * fps)
        out.append((frame.copy(), frame_idx))
    cap.release()
    return out


def _fallback_sample(
    video_path: str,
    sample_seconds: float,
    max_frames: Optional[int] = None,
) -> List[Tuple[any, int]]:
    """回退：按秒抽帧（与 vision_detector._sample_frames 一致）。"""
    cap = cv2.VideoCapture(video_path)
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25
    step_frames = max(1, int(fps * sample_seconds))
    out = []
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % step_frames == 0:
            out.append((frame.copy(), frame_idx))
            if max_frames and len(out) >= max_frames:
                break
        frame_idx += 1
    cap.release()
    return out
