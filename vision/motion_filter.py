# vision/motion_filter.py — 运动唤醒：帧差/光流，静止画面不跑 YOLO
"""用帧差或光流计算运动量，低于阈值视为静态，可跳过检测。"""
import logging
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def compute_motion_score(
    prev_gray: Optional[np.ndarray],
    curr_frame: np.ndarray,
    method: str = "diff",
) -> float:
    """
    计算当前帧相对前一帧的运动量。
    method: "diff" 帧差均值（快），"optical_flow" 光流（更准但慢）。
    返回 [0, 255] 区间的标量，越大运动越剧烈。
    """
    if curr_frame is None or curr_frame.size == 0:
        return 0.0
    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY) if len(curr_frame.shape) == 3 else curr_frame
    if prev_gray is None or prev_gray.shape != curr_gray.shape:
        return 255.0  # 无前一帧时视为有运动，不跳过
    if method == "optical_flow":
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
        )
        mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        return float(np.mean(mag))
    # default: diff
    diff = cv2.absdiff(prev_gray, curr_gray)
    return float(np.mean(diff))


def should_run_detection(
    prev_gray: Optional[np.ndarray],
    curr_frame: np.ndarray,
    motion_threshold: float,
    method: str = "diff",
) -> Tuple[bool, float]:
    """
    判断是否应运行 YOLO：运动量 >= threshold 时返回 True。
    返回 (should_run, motion_score)。
    """
    score = compute_motion_score(prev_gray, curr_frame, method=method)
    return (score >= motion_threshold, score)
