# dashboard/inference_module.py — 帧渲染 + IoU 历史管理
"""
draw_frame()   — PIL 绘制检测框 / FPS / 硬件温度，输出 base64 data URL
IoUTracker     — 维护 labeled_return IoU 快照历史
get_hw_temps() — CPU / GPU 温度（3 秒 TTL 缓存，避免频繁系统调用）
"""
import base64
import io
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

# 荧光绿 RGB(57, 255, 20) = #39FF14
_GREEN  = (57,  255,  20)
_AMBER  = (255, 179,   0)
_RED    = (255,  59,  59)
_DIM    = (80,   80,  80)

_COCO_NAMES = [
    "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat",
    "traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat",
    "dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack",
    "umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball",
    "kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
    "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
    "sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair",
    "couch","potted plant","bed","dining table","toilet","tv","laptop","mouse",
    "remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator",
    "book","clock","vase","scissors","teddy bear","hair drier","toothbrush",
]

# ── 硬件温度（带 TTL 缓存）────────────────────────────────────────────────

_hw_cache: Dict[str, object] = {"ts": 0.0, "cpu": "N/A", "gpu": "N/A"}
_HW_TTL = 3.0   # 秒


def get_hw_temps() -> Dict[str, str]:
    """返回 {"cpu": "52°C", "gpu": "N/A"}，失败时优雅降级。"""
    now = time.time()
    if now - _hw_cache["ts"] < _HW_TTL:
        return {"cpu": str(_hw_cache["cpu"]), "gpu": str(_hw_cache["gpu"])}

    cpu_str = "N/A"
    try:
        import psutil
        temps = psutil.sensors_temperatures() or {}
        for key in ("coretemp", "cpu_thermal", "k10temp", "acpitz"):
            if key in temps and temps[key]:
                cpu_str = f"{temps[key][0].current:.0f}°C"
                break
    except Exception:
        pass

    gpu_str = "N/A"
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu_str = f"{gpus[0].temperature:.0f}°C"
    except Exception:
        pass

    _hw_cache.update({"ts": now, "cpu": cpu_str, "gpu": gpu_str})
    return {"cpu": cpu_str, "gpu": gpu_str}


# ── 字体辅助 ─────────────────────────────────────────────────────────────

def _load_font(size: int):
    """按 size 加载字体：优先 TrueType，降级为 Pillow 内置 bitmap。"""
    from PIL import ImageFont
    _TRUETYPE_PATHS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for path in _TRUETYPE_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _load_fonts(img_height: int = 480):
    """根据图片高度计算比例字体大小，返回 (font_label, font_hud)。"""
    size_label = max(14, img_height // 30)   # 检测框标签
    size_hud   = max(14, img_height // 35)   # FPS / 温度 HUD
    return _load_font(size_label), _load_font(size_hud)


# ── 帧渲染 ───────────────────────────────────────────────────────────────

def draw_frame(
    frame_rgb:  np.ndarray,
    detections: List[Tuple],
    fps:        float,
    frame_id:   int,
) -> str:
    """
    在 RGB 帧上叠加检测框、FPS（左上）、硬件温度（右上）、帧号（左下），
    返回 base64 JPEG data URL（供 Dash html.Img 直接使用）。
    """
    from PIL import Image, ImageDraw

    img  = Image.fromarray(frame_rgb, "RGB")
    draw = ImageDraw.Draw(img)
    W, H = img.width, img.height
    font_label, font_hud = _load_fonts(H)
    lh = max(14, H // 30)   # 标签行高（与 font_label 对齐）

    def _text_w(text, font):
        """获取文字像素宽度，兼容旧版 Pillow。"""
        try:
            return draw.textbbox((0, 0), text, font=font)[2]
        except AttributeError:
            return len(text) * (lh // 2)

    # ---- 检测框 ----
    for (x1, y1, x2, y2, conf, cls) in detections:
        bw = max(2, H // 200)   # 框线宽与图高成比例
        color = _AMBER if conf < 0.60 else _GREEN
        draw.rectangle([x1, y1, x2, y2], outline=color, width=bw)
        cls_name = _COCO_NAMES[cls] if 0 <= cls < len(_COCO_NAMES) else str(cls)
        label = f"{cls_name} {conf:.2f}"
        tw = _text_w(label, font_label)
        ty = max(y1 - lh - 2, 0)
        # 纯黑背景（RGB 不支持 alpha，直接用实色）
        draw.rectangle([x1, ty, x1 + tw + 4, ty + lh + 2], fill=(0, 0, 0))
        draw.text((x1 + 2, ty + 1), label, fill=color, font=font_label)

    # ---- 左上：FPS ----
    fps_txt = f"FPS  {fps:5.1f}"
    fw = _text_w(fps_txt, font_hud)
    draw.rectangle([4, 4, fw + 12, lh + 6], fill=(0, 0, 0))
    draw.text((8, 5), fps_txt, fill=_GREEN, font=font_hud)

    # ---- 右上：硬件温度 ----
    hw = get_hw_temps()
    tmp_txt = f"CPU {hw['cpu']}  GPU {hw['gpu']}"
    tw2 = _text_w(tmp_txt, font_hud)
    tx = W - tw2 - 12
    draw.rectangle([tx - 2, 4, W - 4, lh + 6], fill=(0, 0, 0))
    draw.text((tx, 5), tmp_txt, fill=_GREEN, font=font_hud)

    # ---- 左下：帧号水印 ----
    fid_txt = f"#{frame_id:08d}"
    draw.text((8, H - lh - 4), fid_txt, fill=_DIM, font=font_hud)

    # ---- 编码 ----
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _placeholder_frame(width: int = 640, height: int = 360) -> str:
    """启动前无帧时显示的深色占位图（纯 numpy，无 PIL 依赖）。"""
    arr = np.full((height, width, 3), 26, dtype=np.uint8)
    # 中央十字准星
    cy, cx = height // 2, width // 2
    arr[cy - 1:cy + 2, cx - 30:cx + 30] = [40, 80, 40]
    arr[cy - 30:cy + 30, cx - 1:cx + 2] = [40, 80, 40]
    try:
        from PIL import Image
        img = Image.fromarray(arr, "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except ImportError:
        return ""


# ── IoU 快照追踪器 ───────────────────────────────────────────────────────

class IoUTracker:
    """
    维护标注回传 IoU 快照历史。
    快照由 DataSource.get_iou_snapshot() 低频推送（模拟每次 Import 批次到达）。
    """

    def __init__(self, maxlen: int = 100):
        self._history: deque = deque(maxlen=maxlen)
        self._latest:  Optional[float] = None
        self._last_ts: Optional[str]   = None

    def update(self, iou: float, ts: Optional[str] = None) -> None:
        self._history.append(iou)
        self._latest  = iou
        self._last_ts = ts

    @property
    def latest(self) -> Optional[float]:
        return self._latest

    @property
    def last_ts(self) -> Optional[str]:
        return self._last_ts

    @property
    def history(self) -> List[float]:
        return list(self._history)
