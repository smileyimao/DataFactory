#!/usr/bin/env python3
# scripts/download_models.py — 下载 YOLO 模型到 models/
"""
将 yolov8n（nano）、yolov8s（small）等下载到 models/ 目录。
级联检测：cascade 用 nano 初筛，main 用 small 精检。

  python scripts/download_models.py
  python scripts/download_models.py --model yolov8s   # 只下载指定模型
"""
import argparse
import os
import sys

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "models")
ASSETS_URL = "https://github.com/ultralytics/assets/releases/download/v8.1.0"


def download_to_models(model_name: str) -> str:
    """下载模型到 models/，返回落盘路径。"""
    os.makedirs(MODELS_DIR, exist_ok=True)
    out_path = os.path.join(MODELS_DIR, f"{model_name}.pt")
    if os.path.isfile(out_path):
        print(f"✓ {model_name}.pt 已存在: {out_path}")
        return out_path
    try:
        from urllib.request import urlretrieve
        url = f"{ASSETS_URL}/{model_name}.pt"
        print(f"正在下载 {model_name}.pt ...")
        urlretrieve(url, out_path)
        print(f"✓ 已保存: {out_path}")
        return out_path
    except Exception as e:
        print(f"❌ 下载失败: {e}", file=sys.stderr)
        print("备选：pip install ultralytics 后运行 python -c \"from ultralytics import YOLO; YOLO('yolov8s.pt')\" 会缓存到 ~/.config/Ultralytics/", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Download YOLO models to models/")
    parser.add_argument("--model", default=None, help="只下载指定模型，如 yolov8s；默认下载 nano + small")
    args = parser.parse_args()
    if args.model:
        download_to_models(args.model)
    else:
        download_to_models("yolov8n")
        download_to_models("yolov8s")
    print("\n配置建议：vision.model_path=models/yolov8s.pt, cascade_light_model_path=models/yolov8n.pt")
