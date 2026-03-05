# vision/modality_handlers.py — v2.9 多模态解耦：按 modality 分发 decode_check / sample / produce
# 流程与信号类型解耦，未来 config 切换 modality 即可接入 audio/vibration（predictive maintenance）
"""
Modality 抽象层：Ingest decode_check、Funnel QC sample/quality、Archive produce 均按 modality 分发。
当前仅实现 video；v3 扩展 audio/vibration 时，在此注册 handler 即可。
"""
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# 接口：decode_check(path, cfg) -> bool
_DECODE_CHECK: Dict[str, Callable[[str, dict], bool]] = {}


def _decode_check_video(path: str, cfg: dict) -> bool:
    """Video：cv2 首帧解码。"""
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return False
        ret, frame = cap.read()
        cap.release()
        return bool(ret and frame is not None)
    except Exception as e:
        logger.warning("Video 首帧解码失败: path=%s — %s", path, e)
        return False


def _decode_check_audio(path: str, cfg: dict) -> bool:
    """Audio：v3 实现。librosa/soundfile 可读性检查。"""
    # TODO v3: librosa.load 或 soundfile.read 尝试打开
    logger.debug("Audio decode_check 未实现，跳过检查: %s", path)
    return True


def _decode_check_vibration(path: str, cfg: dict) -> bool:
    """Vibration：v3 实现。传感器数据可读性检查。"""
    # TODO v3: 解析 CSV/二进制格式
    logger.debug("Vibration decode_check 未实现，跳过检查: %s", path)
    return True


def _decode_check_image(path: str, cfg: dict) -> bool:
    """Image：cv2.imread 可读性检查。"""
    try:
        import cv2
        img = cv2.imread(path)
        return img is not None
    except Exception as e:
        logger.warning("Image decode_check 失败: path=%s — %s", path, e)
        return False


def _register_defaults() -> None:
    if _DECODE_CHECK:
        return
    _DECODE_CHECK["video"] = _decode_check_video
    _DECODE_CHECK["image"] = _decode_check_image
    _DECODE_CHECK["audio"] = _decode_check_audio
    _DECODE_CHECK["vibration"] = _decode_check_vibration


def get_modality(cfg: dict) -> str:
    """从配置读取 modality；按 image_mode 或自动检测选择 image/video 通路。"""
    from config import config_loader
    mode = config_loader.get_content_mode(cfg)
    if mode == "image":
        return "image"
    return (cfg.get("modality") or "video").strip().lower()


def get_modality_for_path(path: str, cfg: dict) -> str:
    """按文件扩展名判定单文件 modality，用于混合模式。未知扩展名回退到 get_modality(cfg)。"""
    low = (path or "").lower()
    img_exts = (".jpg", ".jpeg", ".png", ".bmp")
    vid_exts = (".mp4", ".mov", ".avi", ".mkv")
    if any(low.endswith(ext) for ext in img_exts):
        return "image"
    if any(low.endswith(ext) for ext in vid_exts):
        return "video"
    return get_modality(cfg)


def decode_check(path: str, cfg: dict) -> bool:
    """
    按 modality 分发 decode_check。成功返回 True，失败返回 False。
    混合模式时按文件扩展名自动选择 image/video handler；否则用配置的 modality。
    未实现的 modality 默认返回 True（跳过检查）。
    """
    _register_defaults()
    from config import config_loader
    mode = config_loader.get_content_mode(cfg)
    if mode == "both":
        modality = get_modality_for_path(path, cfg)
    else:
        modality = get_modality(cfg)
    handler = _DECODE_CHECK.get(modality)
    if handler is None:
        logger.warning("未知 modality=%s，跳过 decode_check", modality)
        return True
    return handler(path, cfg)


# 预留接口（v3 实现）：
# def sample(path: str, cfg: dict) -> Any: ...
# def quality_check(samples: Any, cfg: dict) -> dict: ...
# def produce(items: list, target_dir: str, cfg: dict) -> int: ...
