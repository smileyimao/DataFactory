#!/usr/bin/env python3
# scripts/export_for_cvat_native.py — 将 for_labeling 转为 CVAT for images 原生 XML 格式
"""
用法:
  python scripts/export_for_cvat_native.py --vehicle

生成 annotations.xml（CVAT 原生格式），打包为 zip 供 Upload Annotations。
格式与 CVAT 导出完全一致，Upload 成功率最高。

流程：1. Create task → for_cvat.zip（图片）2. Upload annotations → CVAT for images 1.1 → for_cvat_native.zip
"""
import argparse
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)

from utils import file_tools

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}

COCO_NAMES_8 = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck"]
COCO_COLORS = ["#c06060", "#004040", "#2080c0", "#80a0a0", "#800080", "#204080", "#50a080", "#906080"]


def _get_image_size(path: str) -> tuple:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size[0], im.size[1]
    except Exception:
        pass
    try:
        import cv2
        img = cv2.imread(path)
        if img is not None:
            return img.shape[1], img.shape[0]
    except Exception:
        pass
    return 0, 0


def _parse_yolo_label(txt_path: str) -> list:
    """解析 YOLO .txt，返回 [(cid, cx, cy, w, h, conf?), ...]。第 6 列 conf 可选。"""
    out = []
    if not os.path.isfile(txt_path):
        return out
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                cid = int(parts[0])
                cx, cy, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                conf = float(parts[5]) if len(parts) >= 6 else None
                out.append((cid, cx, cy, w, h, conf))
            except (ValueError, IndexError):
                continue
    return out


def export_cvat_native(for_labeling_dir: str, output_zip: str, class_names: list) -> str:
    """
    生成 CVAT for images 1.1 格式 XML，打包为 zip。
    格式与 CVAT 导出完全一致。
    """
    images_dir = os.path.join(for_labeling_dir, "images")
    if not os.path.isdir(images_dir):
        raise FileNotFoundError(f"images 目录不存在: {images_dir}")

    os.makedirs(os.path.dirname(output_zip) or ".", exist_ok=True)

    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"

    meta = ET.SubElement(root, "meta")
    task = ET.SubElement(meta, "task")
    ET.SubElement(task, "id").text = "0"
    ET.SubElement(task, "name").text = "DataFactory"
    labels_el = ET.SubElement(task, "labels")
    for i, name in enumerate(class_names):
        lbl = ET.SubElement(labels_el, "label")
        ET.SubElement(lbl, "name").text = name
        ET.SubElement(lbl, "color").text = COCO_COLORS[i % len(COCO_COLORS)]
        ET.SubElement(lbl, "type").text = "rectangle"
        attrs_el = ET.SubElement(lbl, "attributes")
        attr = ET.SubElement(attrs_el, "attribute")
        ET.SubElement(attr, "name").text = "confidence"
        ET.SubElement(attr, "mutable").text = "false"
        ET.SubElement(attr, "input_type").text = "number"
        ET.SubElement(attr, "default_value").text = "0"
        ET.SubElement(attr, "values").text = "0.0,1.0"
    ET.SubElement(meta, "dumped").text = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f+00:00")

    items = []
    for name in sorted(os.listdir(images_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXT:
            continue
        src = os.path.join(images_dir, name)
        if not os.path.isfile(src):
            continue
        items.append((name, src))

    for idx, (name, src) in enumerate(items):
        safe_name = file_tools.sanitize_filename(name)
        w, h = _get_image_size(src)
        if w <= 0 or h <= 0:
            w, h = 1920, 1080

        base, _ = os.path.splitext(name)
        txt_src = os.path.join(images_dir, base + ".txt")
        boxes = []
        for cid, cx, cy, bw, bh, conf in _parse_yolo_label(txt_src):
            if cid >= len(class_names) or not class_names[cid]:
                continue
            xtl = (cx - bw / 2) * w
            ytl = (cy - bh / 2) * h
            xbr = (cx + bw / 2) * w
            ybr = (cy + bh / 2) * h
            boxes.append((class_names[cid], xtl, ytl, xbr, ybr, conf))

        # 读取 SAM polygon sidecar（若存在）
        import json as _json
        poly_path = os.path.join(images_dir, base + ".poly.json")
        poly_map = {}  # label -> list of point-lists（先进先出）
        if os.path.isfile(poly_path):
            try:
                for entry in _json.load(open(poly_path, encoding="utf-8")):
                    poly_map.setdefault(entry["label"], []).append(
                        (entry["points"], entry.get("score"))
                    )
            except Exception:
                pass

        img_el = ET.SubElement(root, "image", id=str(idx), name=safe_name, width=str(w), height=str(h))
        for label, xtl, ytl, xbr, ybr, conf in boxes:
            if label in poly_map and poly_map[label]:
                pts, score = poly_map[label].pop(0)
                pts_str = ";".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                poly_el = ET.SubElement(
                    img_el, "polygon",
                    label=label,
                    source="auto",
                    occluded="0",
                    z_order="0",
                    points=pts_str,
                )
                use_conf = conf if conf is not None else score
                if use_conf is not None:
                    ET.SubElement(poly_el, "attribute", name="confidence").text = f"{use_conf:.4f}"
            else:
                box = ET.SubElement(
                    img_el, "box",
                    label=label,
                    source="auto",
                    occluded="0",
                    xtl=f"{xtl:.2f}",
                    ytl=f"{ytl:.2f}",
                    xbr=f"{xbr:.2f}",
                    ybr=f"{ybr:.2f}",
                    z_order="0",
                )
                if conf is not None:
                    attr_el = ET.SubElement(box, "attribute", name="confidence")
                    attr_el.text = f"{conf:.4f}"

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")

    with tempfile.TemporaryDirectory() as tmp:
        xml_path = os.path.join(tmp, "annotations.xml")
        tree.write(xml_path, encoding="utf-8", xml_declaration=True, default_namespace="")
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(xml_path, "annotations.xml")

    return output_zip


def main():
    parser = argparse.ArgumentParser(description="将 for_labeling 转为 CVAT 原生 XML 供 Upload Annotations")
    parser.add_argument("-o", "--output", type=str, default="", help="输出 zip 路径")
    parser.add_argument("--vehicle", action="store_true", help="车辆 demo：COCO 8 类")
    args = parser.parse_args()

    from config import config_loader
    cfg, paths = config_loader.get_config_and_paths(BASE_DIR)
    for_labeling = paths["for_labeling"]
    output = args.output or os.path.join(for_labeling, "for_cvat_native.zip")
    if not os.path.isabs(output):
        output = os.path.join(BASE_DIR, output)

    class_names = COCO_NAMES_8 if args.vehicle else COCO_NAMES_8
    export_cvat_native(for_labeling, output, class_names)
    print(f"✅ for_cvat_native.zip: {output}")
    print("   流程：1. Create task → for_cvat.zip  2. Upload annotations → CVAT for images 1.1 → 选此 zip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
