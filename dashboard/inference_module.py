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

def _load_fonts():
    """返回 (font_sm, font_md)，兼容 Pillow 旧版。"""
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=12), ImageFont.load_default(size=15)
    except TypeError:
        f = ImageFont.load_default()
        return f, f


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
    font_sm, font_md = _load_fonts()

    # ---- 检测框 ----
    for (x1, y1, x2, y2, conf, cls) in detections:
        draw.rectangle([x1, y1, x2, y2], outline=_GREEN, width=2)
        label = f"vehicle {conf:.2f}"
        # 小背景块提升文字可读性
        tw = len(label) * 7
        draw.rectangle([x1, max(y1 - 16, 0), x1 + tw, max(y1, 16)],
                       fill=(0, 0, 0, 160))
        draw.text((x1 + 2, max(y1 - 15, 1)), label, fill=_GREEN, font=font_sm)

    # ---- 左上：FPS ----
    fps_txt = f"FPS  {fps:5.1f}"
    draw.rectangle([6, 4, 6 + len(fps_txt) * 9, 22], fill=(0, 0, 0))
    draw.text((8, 5), fps_txt, fill=_GREEN, font=font_md)

    # ---- 右上：硬件温度 ----
    hw = get_hw_temps()
    tmp_txt = f"CPU {hw['cpu']}  GPU {hw['gpu']}"
    tx = img.width - len(tmp_txt) * 8 - 8
    draw.rectangle([tx - 2, 4, img.width - 4, 22], fill=(0, 0, 0))
    draw.text((tx, 5), tmp_txt, fill=_GREEN, font=font_sm)

    # ---- 左下：帧号水印 ----
    fid_txt = f"#{frame_id:08d}"
    draw.text((8, img.height - 18), fid_txt, fill=_DIM, font=font_sm)

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
