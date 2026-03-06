# core/system_probe.py — 启动时硬件自动检测与配置推荐（v3.9）
# 依赖：psutil（必须），torch（可选）
# 所有检测失败均有 fallback，不会让 pipeline 崩溃。
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ───────────────────────────── 检测 ────────────────────────────────────────

def detect_capabilities() -> Dict[str, Any]:
    """
    检测本机硬件能力，返回：
      cpu        : str   CPU 型号字符串
      ram_gb     : float 内存大小（GB）
      has_gpu    : bool  是否有 GPU
      vram_gb    : float GPU 显存（GB），无 GPU 则 0.0
      device     : str   "cuda" | "mps" | "cpu"
      is_jetson  : bool  是否 Jetson 设备
    """
    caps: Dict[str, Any] = {
        "cpu": "unknown",
        "ram_gb": 0.0,
        "has_gpu": False,
        "vram_gb": 0.0,
        "device": "cpu",
        "is_jetson": False,
        "is_apple_silicon": False,
    }

    # ── CPU 型号 + Apple Silicon 检测 ───────────────────────────────────────
    try:
        import platform
        caps["cpu"] = platform.processor() or platform.machine() or "unknown"
        # arm64 = Apple Silicon；x86_64 = Intel Mac / AMD64 Linux
        caps["is_apple_silicon"] = platform.machine() == "arm64"
    except Exception as e:
        logger.debug("CPU 型号检测失败: %s", e)

    # ── RAM ─────────────────────────────────────────────────────────────────
    try:
        import psutil
        caps["ram_gb"] = psutil.virtual_memory().total / (1024 ** 3)
    except Exception as e:
        logger.debug("RAM 检测失败: %s", e)

    # ── Jetson 检测 ─────────────────────────────────────────────────────────
    caps["is_jetson"] = os.path.isfile("/etc/nv_tegra_release")

    # ── GPU / device ────────────────────────────────────────────────────────
    try:
        import torch
        if torch.cuda.is_available():
            caps["has_gpu"] = True
            caps["device"] = "cuda"
            # 取第一张 GPU 的显存
            props = torch.cuda.get_device_properties(0)
            caps["vram_gb"] = props.total_memory / (1024 ** 3)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            caps["has_gpu"] = True
            caps["device"] = "mps"
            caps["vram_gb"] = 0.0  # MPS 共享 unified memory，无法直接查询独立显存
    except ImportError:
        logger.debug("torch 未安装，GPU 检测跳过")
    except Exception as e:
        logger.debug("GPU 检测失败: %s", e)

    return caps


# ───────────────────────────── 自动配置 ────────────────────────────────────

def auto_configure(caps: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据硬件 caps 返回 foundation_models 建议配置字典，包含：
      clip_enabled, sam_enabled, sam_model_type, yolo_model
    该字典直接覆盖 cfg["foundation_models"]（若未设 override: true）。
    """
    device = caps.get("device", "cpu")
    ram_gb = caps.get("ram_gb", 0.0)
    vram_gb = caps.get("vram_gb", 0.0)
    is_apple_silicon = caps.get("is_apple_silicon", False)

    # ── Mac M 系列（MPS + arm64）────────────────────────────────────────────
    # Intel Mac 带 AMD Radeon 时 mps 也可能为 True，须额外判断架构
    if device == "mps" and is_apple_silicon:
        return {
            "clip_enabled": True,
            "sam_enabled": True,
            "sam_model_type": "vit_l",
            "yolo_model": "yolov8m",
        }

    # ── CUDA 设备 ───────────────────────────────────────────────────────────
    if device == "cuda":
        if vram_gb >= 32:
            return {
                "clip_enabled": True,
                "sam_enabled": True,
                "sam_model_type": "vit_h",
                "yolo_model": "yolov8x",
            }
        if vram_gb >= 16:
            return {
                "clip_enabled": True,
                "sam_enabled": True,
                "sam_model_type": "vit_l",
                "yolo_model": "yolov8m",
            }
        # Jetson AGX Orin / 低端 GPU（vram < 16GB）
        return {
            "clip_enabled": True,
            "sam_enabled": True,
            "sam_model_type": "vit_b",
            "yolo_model": "yolov8s",
        }

    # ── CPU only ────────────────────────────────────────────────────────────
    if ram_gb >= 8:
        # Intel Mac / 普通 CPU 服务器
        return {
            "clip_enabled": True,
            "sam_enabled": True,
            "sam_model_type": "vit_b",
            "yolo_model": "yolov8s",
        }

    # ── 低端设备（无 GPU，RAM < 8GB）───────────────────────────────────────
    return {
        "clip_enabled": False,
        "sam_enabled": False,
        "sam_model_type": None,
        "yolo_model": "yolov8n",
    }


# ───────────────────────────── 打印 ────────────────────────────────────────

def print_system_info(caps: Dict[str, Any], config: Dict[str, Any]) -> None:
    """启动时打印硬件检测结果与自动配置摘要。"""
    device = caps.get("device", "cpu")
    ram_gb = caps.get("ram_gb", 0.0)
    vram_gb = caps.get("vram_gb", 0.0)
    vram_str = f"{vram_gb:.1f}gb" if vram_gb else "None"

    clip_on = config.get("clip_enabled", False)
    sam_on = config.get("sam_enabled", False)
    sam_type = config.get("sam_model_type") or "disabled"
    yolo_model = config.get("yolo_model", "—")

    clip_str = "✅ enabled" if clip_on else "❌ disabled"
    sam_str = f"✅ {sam_type}" if sam_on else "❌ disabled"

    print(
        f"\n🔍 System probe:\n"
        f"   Device: {device}\n"
        f"   RAM: {ram_gb:.0f}gb\n"
        f"   GPU VRAM: {vram_str}\n"
        f"\n⚙️  Auto-configured:\n"
        f"   CLIP: {clip_str}\n"
        f"   SAM:  {sam_str}\n"
        f"   YOLO: {yolo_model}"
    )
