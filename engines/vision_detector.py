# engines/vision_detector.py — v2.0 视觉质检：YOLO 单例加载，抽帧推理，仅返回检测结果，不决策
# 支持四板斧：运动唤醒、I-帧、级联检测。
import base64
import io
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import motion_filter
from . import frame_io

logger = logging.getLogger(__name__)

_model: Any = None
_model_path_loaded: Optional[str] = None
_cascade_model: Any = None
_cascade_path_loaded: Optional[str] = None
_last_load_error: Optional[str] = None  # 最近一次加载失败原因，供邮件/日志展示


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
    global _model, _model_path_loaded, _last_load_error
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
        _last_load_error = None
        logger.info("视觉模型已加载: %s", path)
        return _model
    except Exception as e:
        _last_load_error = str(e)
        logger.warning("视觉模型加载失败 (model_path=%s): %s", path, e)
        return None


def get_vision_load_error() -> str:
    """返回最近一次视觉模型加载失败的原因，成功或未尝试则为空字符串。供邮件/运行日志展示。"""
    return _last_load_error or ""


def get_vision_model_version(cfg: dict) -> str:
    """
    M2 版本映射：返回当前生效的视觉模型版本（已加载的模型路径或 config 中的 vision_model_version）。
    仅读配置与单例状态，不硬编码。
    """
    if _model_path_loaded:
        return _model_path_loaded
    return (cfg.get("version_mapping") or {}).get("vision_model_version") or ""


def get_cascade_model(cfg: dict):
    """级联检测：加载轻量模型，用于初筛。若未配置或与主模型相同则返回 None。"""
    global _cascade_model, _cascade_path_loaded
    v = _vision_cfg(cfg)
    path = (v.get("cascade_light_model_path") or "").strip()
    if not path:
        return None
    main_path = (v.get("model_path") or "").strip()
    if path == main_path:
        return None
    if path == _cascade_path_loaded and _cascade_model is not None:
        return _cascade_model
    try:
        from ultralytics import YOLO
        _cascade_model = YOLO(path)
        _cascade_path_loaded = path
        logger.info("级联轻量模型已加载: %s", path)
        return _cascade_model
    except Exception as e:
        logger.warning("级联模型加载失败 (path=%s): %s", path, e)
        return None


def _cascade_has_detection(model, frame, conf_threshold: float, base_params: dict) -> bool:
    """轻量模型是否有检测（超过阈值即返回 True）。"""
    params = {**base_params, "conf": conf_threshold, "verbose": False}
    try:
        r = model.predict(frame, **params)
        if not r:
            return False
        r0 = r[0]
        if not hasattr(r0, "boxes") or r0.boxes is None:
            return False
        confs = r0.boxes.conf.cpu().numpy() if hasattr(r0.boxes, "conf") else []
        return any(float(c) >= conf_threshold for c in confs)
    except Exception:
        return False


def _sample_frames(
    video_path: str,
    sample_seconds: float,
    use_i_frame_only: bool = False,
) -> List[Tuple[Any, int]]:
    """
    按 config vision.sample_seconds 间隔从视频抽帧。返回 [(frame_bgr, frame_idx), ...]。
    use_i_frame_only=True 时用 frame_io.sample_i_frames 只读 I-帧，减少解码量。
    """
    if not os.path.isfile(video_path):
        return []
    if use_i_frame_only:
        return frame_io.sample_i_frames(video_path, sample_seconds)
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


def _boxes_to_detections(r, frame_h: int, frame_w: int, conf_threshold: float = 0.0) -> List[Dict[str, Any]]:
    """将 YOLO 单帧 result 转为 [{class_id, x_center, y_center, w, h, conf}] 归一化坐标。"""
    out = []
    if not hasattr(r, "boxes") or r.boxes is None:
        return out
    try:
        xyxy = r.boxes.xyxy.cpu().numpy()
        cls = r.boxes.cls.cpu().numpy()
        conf = r.boxes.conf.cpu().numpy()
    except Exception:
        return out
    for i in range(len(cls)):
        c = float(conf[i])
        if c < conf_threshold:
            continue
        x1, y1, x2, y2 = xyxy[i]
        xc = ((x1 + x2) / 2) / frame_w
        yc = ((y1 + y2) / 2) / frame_h
        w = (x2 - x1) / frame_w
        h = (y2 - y1) / frame_h
        out.append({
            "class_id": int(cls[i]),
            "x_center": xc, "y_center": yc, "w": w, "h": h,
            "conf": c,
        })
    return out


def run_vision_scan(
    cfg: dict,
    video_paths: List[str],
    max_thumbnails_per_video: int = 3,
    thumb_width: int = 320,
    return_detections: bool = False,
    sample_seconds_override: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    视觉扫描入口：若 vision.enabled 且模型加载成功，则按 sample_seconds 抽帧并做 YOLO 推理。
    支持四板斧：use_i_frame_only（只解 I-帧）、motion_threshold（运动唤醒）、cascade_light_model_path（级联初筛）。
    返回每视频的推理摘要；若 return_detections=True 则每视频带 detections_by_frame。
    """
    if not is_enabled(cfg):
        return []
    v = _vision_cfg(cfg)
    sample_seconds = sample_seconds_override if sample_seconds_override is not None else v.get("sample_seconds")
    if sample_seconds is None:
        logger.warning("vision.sample_seconds 未配置，跳过视觉推理")
        return []
    use_i_frame = bool(v.get("use_i_frame_only", False))
    motion_threshold = float(v.get("motion_threshold", 0.0))  # 0=关闭运动唤醒
    cascade_model = get_cascade_model(cfg)
    cascade_conf = float(v.get("cascade_light_conf", 0.2)) if cascade_model else 0.0

    model = get_model(cfg)
    if model is None:
        logger.info("AI 正在扫描...（视觉模型未加载，跳过推理）")
        return []
    logger.info("AI 正在扫描... (I帧=%s 运动唤醒=%s 级联=%s)", use_i_frame, motion_threshold > 0, cascade_model is not None)
    params = get_inference_params(cfg)
    conf_threshold = float(v.get("conf", 0.25)) if return_detections else 0.0
    per_video: List[Dict[str, Any]] = []
    for v_path in video_paths:
        if not os.path.isfile(v_path):
            logger.warning("视觉扫描跳过不存在的文件: %s", v_path)
            continue
        frames_with_idx = _sample_frames(v_path, sample_seconds, use_i_frame_only=use_i_frame)
        if not frames_with_idx:
            entry = {"path": v_path, "name": os.path.basename(v_path), "n_frames": 0, "n_detections": 0, "thumbnails": []}
            if return_detections:
                entry["detections_by_frame"] = {}
            per_video.append(entry)
            continue

        # 运动唤醒 + 级联：筛选需要跑主模型的帧
        prev_gray = None
        frames_to_run: List[Tuple[Any, int, int]] = []  # (frame, frame_idx, orig_index)
        for i, (frame, frame_idx) in enumerate(frames_with_idx):
            if motion_threshold > 0:
                run_det, _ = motion_filter.should_run_detection(
                    prev_gray, frame, motion_threshold, method="diff"
                )
                if not run_det:
                    continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            prev_gray = gray
            if cascade_model:
                if not _cascade_has_detection(cascade_model, frame, cascade_conf, params):
                    continue
            frames_to_run.append((frame, frame_idx, i))

        if not frames_to_run:
            entry = {"path": v_path, "name": os.path.basename(v_path), "n_frames": len(frames_with_idx), "n_detections": 0, "thumbnails": []}
            if return_detections:
                entry["detections_by_frame"] = {}
            per_video.append(entry)
            logger.info("视觉扫描: %s 抽帧 %d 张，四板斧过滤后 0 张需检测", os.path.basename(v_path), len(frames_with_idx))
            continue

        frames_only = [f[0] for f in frames_to_run]
        try:
            results = model.predict(frames_only, **params)
        except Exception as e:
            logger.warning("视觉推理异常 %s: %s", os.path.basename(v_path), e)
            entry = {"path": v_path, "name": os.path.basename(v_path), "n_frames": len(frames_with_idx), "error": str(e), "thumbnails": []}
            if return_detections:
                entry["detections_by_frame"] = {}
            per_video.append(entry)
            continue

        n_det = 0
        thumbnails: List[str] = []
        detections_by_frame: Dict[int, List[Dict[str, Any]]] = {}
        for j, r in enumerate(results):
            if j >= len(frames_to_run):
                break
            _, frame_idx, _ = frames_to_run[j]
            frame = frames_only[j]
            frame_h, frame_w = frame.shape[:2]
            dets = _boxes_to_detections(r, frame_h, frame_w, conf_threshold) if return_detections else []
            if return_detections and dets:
                detections_by_frame[frame_idx] = dets
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
        entry = {
            "path": v_path,
            "name": os.path.basename(v_path),
            "n_frames": len(frames_with_idx),
            "n_detections": n_det,
            "thumbnails": thumbnails,
        }
        if return_detections:
            entry["detections_by_frame"] = detections_by_frame
        per_video.append(entry)
        logger.info("视觉扫描: %s 抽帧 %d 张，四板斧后检测 %d 张，框 %d 个", os.path.basename(v_path), len(frames_with_idx), len(frames_to_run), n_det)
    return per_video
