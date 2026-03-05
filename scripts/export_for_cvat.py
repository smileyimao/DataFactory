#!/usr/bin/env python3
# scripts/export_for_cvat.py — 将 for_labeling 打包为 CVAT 用 zip（仅图片，供创建 Task）
"""
用法:
  python scripts/export_for_cvat.py
  python scripts/export_for_cvat.py --vehicle   # 无影响，保持兼容

生成 for_cvat.zip（扁平结构，根目录即图片），供 CVAT Create task 时 Select files 上传。
标注用 export_for_cvat_native.py 生成，Upload annotations 选 CVAT for images 1.1。
"""
import argparse
import os
import sys
import tempfile
import zipfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)

from utils import file_tools

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def export_task_zip_flat(for_labeling_dir: str, output_zip: str) -> str:
    """打包为扁平 zip，仅含根目录图片，供 CVAT 创建 Task。"""
    images_dir = os.path.join(for_labeling_dir, "images")
    if not os.path.isdir(images_dir):
        raise FileNotFoundError(f"images 目录不存在: {images_dir}")

    os.makedirs(os.path.dirname(output_zip) or ".", exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        for name in sorted(os.listdir(images_dir)):
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMAGE_EXT:
                continue
            src = os.path.join(images_dir, name)
            if not os.path.isfile(src):
                continue
            safe_name = file_tools.sanitize_filename(name)
            dst = os.path.join(tmp, safe_name)
            with open(src, "rb") as f:
                with open(dst, "wb") as g:
                    g.write(f.read())

        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for fn in sorted(os.listdir(tmp)):
                full = os.path.join(tmp, fn)
                if os.path.isfile(full):
                    zf.write(full, fn)

    return output_zip


def main():
    parser = argparse.ArgumentParser(description="将 for_labeling 打包为 CVAT 图片 zip（创建 Task 用）")
    parser.add_argument("-o", "--output", type=str, default="", help="输出 zip 路径")
    parser.add_argument("--vehicle", action="store_true", help="兼容参数，无影响")
    args = parser.parse_args()

    from config import config_loader
    cfg, paths = config_loader.get_config_and_paths(BASE_DIR)
    for_labeling = paths["for_labeling"]
    output = args.output or os.path.join(for_labeling, "for_cvat.zip")
    if not os.path.isabs(output):
        output = os.path.join(BASE_DIR, output)

    export_task_zip_flat(for_labeling, output)
    print(f"✅ for_cvat.zip: {output}")
    print("   标注：python scripts/export_for_cvat_native.py --vehicle")
    print("   CVAT：Create task → 此 zip；Upload annotations → CVAT for images 1.1 → for_cvat_native.zip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
