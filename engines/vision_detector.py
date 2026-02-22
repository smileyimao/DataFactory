# engines/vision_detector.py — v2.0 视觉质检：YOLO 单例加载，抽帧推理，仅返回检测结果，不决策
# 所有推理参数（conf、iou、classes、device 等）均从 config/settings.yaml vision 段读取，不硬编码。
import base64
import io
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_model: Any = None
_model_path_loaded: Optional[str] = None


def _vision_cfg(cfg: dict) -> dict:
    return cfg.get("vision") or {}


def is_enabled(cfg: dict) -> bool:
    return bool(_vision_cfg(cfg).get("enabled", False))


def get_inference_params(cfg: dict) -> Dict[str, Any]:
    """
    从 config vision 段读取推理参数，供 model.predict(**kwargs) 使用。
    默认值由 config_loader 在加载时填入，此处不硬编码任何数字。
    返回的 dict 中 None 值已剔除，避免覆盖 ultralytics 内部默认行为。
    """
    v = _vision_cfg(cfg)
    raw = {
        "conf": v.get("conf"),
        "iou": v.get("iou"),
        "classes": v.get("classes"),
        "device": v.get("device"),
        "max_det": v.get("max_det"),
        "imgsz": v.get("imgsz"),
        "half": v.get("half"),
        "verbose": v.get("verbose"),
    }
    return {k: val for k, val in raw.items() if val is not None}


def get_model(cfg: dict):
    """
    YOLO 单例：从 config vision.model_path 加载，仅当 vision.enabled 且 model_path 非空时加载。
    返回模型实例或 None。
    """
    global _model, _model_path_loaded
    v = _vision_cfg(cfg)
    if not v.get("enabled") or not v.get("model_path"):
        return None
    path = (v.get("model_path") or "").strip()
    if not path:
        return None
    if path == _model_path_loaded and _model is not None:
        return _model
    try:
        from ultralytics import YOLO
        _model = YOLO(path)
        _model_path_loaded = path
        logger.info("视觉模型已加载: %s", path)
        return _model
    except Exception as e:
        logger.warning("视觉模型加载失败 (model_path=%s): %s", path, e)
        return None


def get_vision_model_version(cfg: dict) -> str:
    """
    M2 版本映射：返回当前生效的视觉模型版本（已加载的模型路径或 config 中的 vision_model_version）。
    仅读配置与单例状态，不硬编码。
    """
    if _model_path_loaded:
        return _model_path_loaded
    return (cfg.get("version_mapping") or {}).get("vision_model_version") or ""


def _sample_frames(
    video_path: str,
    sample_seconds: float,
) -> List[Tuple[Any, int]]:
    """
    按 config vision.sample_seconds 间隔从视频抽帧。返回 [(frame_bgr, frame_idx), ...]。
    sample_seconds 从 config 读取，此处不硬编码。
    """
    if not os.path.isfile(video_path):
        return []
    cap = cv2.VideoCapture(video_path)
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25
    step_frames = max(1, int(fps * sample_seconds))
    out: List[Tuple[Any, int]] = []
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % step_frames == 0:
            out.append((frame.copy(), frame_idx))
        frame_idx += 1
    cap.release()
    return out


def _frame_to_thumbnail_b64(img_bgr: np.ndarray, max_width: int = 320) -> Optional[str]:
    """将 BGR 图缩成缩略图并转为 JPEG base64，便于嵌入 HTML。"""
    if img_bgr is None or img_bgr.size == 0:
        return None
    h, w = img_bgr.shape[:2]
    if w > max_width:
        scale = max_width / w
        new_w, new_h = max_width, int(h * scale)
        img_bgr = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    try:
        _, buf = cv2.imencode(".jpg", img_bgr)
        return base64.b64encode(buf.tobytes()).decode("utf-8")
    except Exception:
        return None


def run_vision_scan(
    cfg: dict,
    video_paths: List[str],
    max_thumbnails_per_video: int = 3,
    thumb_width: int = 320,
) -> List[Dict[str, Any]]:
    """
    视觉扫描入口：若 vision.enabled 且模型加载成功，则按 sample_seconds 抽帧并做 YOLO 推理。
    返回每视频的推理摘要（含可选缩略图 base64，供智能检测报告嵌入）。
    调用方应传入当前可访问的视频路径（如归档后的路径）。
    """
    if not is_enabled(cfg):
        return []
    v = _vision_cfg(cfg)
    sample_seconds = v.get("sample_seconds")
    if sample_seconds is None:
        logger.warning("vision.sample_seconds 未配置，跳过视觉推理")
        return []
    model = get_model(cfg)
    if model is None:
        logger.info("AI 正在扫描...（视觉模型未加载，跳过推理）")
        return []
    logger.info("AI 正在扫描...")
    params = get_inference_params(cfg)
    per_video: List[Dict[str, Any]] = []
    for v_path in video_paths:
        if not os.path.isfile(v_path):
            logger.warning("视觉扫描跳过不存在的文件: %s", v_path)
            continue
        frames_with_idx = _sample_frames(v_path, sample_seconds)
        if not frames_with_idx:
            per_video.append({
                "path": v_path,
                "name": os.path.basename(v_path),
                "n_frames": 0,
                "n_detections": 0,
                "thumbnails": [],
            })
            continue
        frames = [f[0] for f in frames_with_idx]
        try:
            results = model.predict(frames, **params)
        except Exception as e:
            logger.warning("视觉推理异常 %s: %s", os.path.basename(v_path), e)
            per_video.append({
                "path": v_path,
                "name": os.path.basename(v_path),
                "n_frames": len(frames),
                "error": str(e),
                "thumbnails": [],
            })
            continue
        n_det = 0
        thumbnails: List[str] = []
        for r in results:
            n_boxes = len(r.boxes) if (hasattr(r, "boxes") and r.boxes is not None) else 0
            n_det += n_boxes
            if len(thumbnails) < max_thumbnails_per_video and n_boxes > 0 and hasattr(r, "plot"):
                try:
                    plotted = r.plot()
                    if plotted is not None:
                        img = np.asarray(plotted)
                        if img.dtype != np.uint8:
                            img = (np.clip(img, 0, 255)).astype(np.uint8)
                        b64 = _frame_to_thumbnail_b64(img, max_width=thumb_width)
                        if b64:
                            thumbnails.append(b64)
                except Exception:
                    pass
        per_video.append({
            "path": v_path,
            "name": os.path.basename(v_path),
            "n_frames": len(frames),
            "n_detections": n_det,
            "thumbnails": thumbnails,
        })
        logger.info("视觉扫描: %s 抽帧 %d 张，检测框 %d 个，缩略图 %d 张", os.path.basename(v_path), len(frames), n_det, len(thumbnails))
    return per_video
