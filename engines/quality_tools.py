# engines/quality_tools.py — 质检传感器，只返回数值，不返回合格/不合格判断
import cv2
import numpy as np
from typing import Dict, Any, Optional, Tuple

def analyze_frame(frame: np.ndarray, prev_gray: Optional[np.ndarray] = None) -> Tuple[Dict[str, float], Optional[np.ndarray]]:
    """
    对单帧做质量分析，只返回原始数值。
    返回: ({"br": float, "bl": float, "jitter": float, "std_dev": float}, current_gray 用于下一帧)
    """
    out: Dict[str, float] = {}
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        out["br"] = round(float(np.mean(gray)), 2)
        out["bl"] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)
        std_dev = float(np.std(gray))
        out["std_dev"] = round(std_dev, 2)
        out["jitter"] = 0.0
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            out["jitter"] = round(float(np.mean(diff)), 2)
        return out, gray
    except Exception:
        return {"br": 0.0, "bl": 0.0, "jitter": 0.0, "std_dev": 0.0}, None


def decide_env(raw: Dict[str, float], cfg: Dict[str, Any]) -> str:
    """
    决策层：根据工具输出与配置判断本帧环境标签。
    供 core 或 report 使用，工具层不依赖此函数。
    """
    br = raw.get("br", 0)
    bl = raw.get("bl", 0)
    jitter = raw.get("jitter", 0)
    std_dev = raw.get("std_dev", 0)
    env = "Normal"
    if br < cfg.get("min_brightness", 40):
        env = "Too Dark"
    elif br > cfg.get("max_brightness", 220):
        env = "Harsh Light"
    elif bl < cfg.get("min_blur_score", 15):
        env = "Blurry"
    elif std_dev < cfg.get("min_contrast", 15):
        env = "Low Contrast"
    elif std_dev > cfg.get("max_contrast", 95):
        env = "High Contrast"
    if env == "Normal" and jitter > cfg.get("max_jitter", 35):
        pardon = cfg.get("min_blur_score", 15) * 2.5
        if bl > pardon:
            env = "Normal (Jitter Pardoned)"
        else:
            env = "High Jitter"
    # 预留：v2.x 人机冲突检测可在此注入 env = "Conflict"
    # if cfg.get("conflict_detection") and <external_signal>: env = "Conflict"
    return env
