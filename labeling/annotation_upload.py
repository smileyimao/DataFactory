# labeling/annotation_upload.py — 标注平台上传适配层
# 解耦 pipeline 与具体标注平台：main.py 只调用 upload()，换平台改配置即可
import logging
import os
import sys

from utils.usage_tracker import track

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def upload(cfg: dict, task_name: str = "DataFactory") -> str:
    """
    将最新批次导出并上传到配置的标注平台。
    返回任务 URL（成功）或空字符串（失败/跳过）。

    平台选择优先级：
      1. 环境变量 ANNOTATION_PLATFORM
      2. cfg["annotation_platform"]
      3. 若 CVAT_LOCAL_URL 已设置，默认 "cvat"
      4. 否则 "none"
    """
    platform = (
        os.environ.get("ANNOTATION_PLATFORM", "").strip()
        or cfg.get("annotation_platform", "").strip()
        or ("cvat" if os.environ.get("CVAT_LOCAL_URL") else "none")
    )
    platform = platform.lower()

    if platform == "none":
        return ""

    # 解析 for_labeling 路径（各平台共用）
    for_labeling = cfg.get("paths", {}).get("labeling_export", "")
    if not for_labeling:
        for_labeling = os.path.join(BASE_DIR, "storage", "for_labeling")
    if not os.path.isabs(for_labeling):
        for_labeling = os.path.join(BASE_DIR, for_labeling)

    archive_dir = cfg.get("paths", {}).get("data_warehouse", "")
    if not archive_dir:
        archive_dir = os.path.join(BASE_DIR, "storage", "archive")
    if not os.path.isabs(archive_dir):
        archive_dir = os.path.join(BASE_DIR, archive_dir)

    if platform == "cvat":
        return _upload_cvat(cfg, for_labeling, archive_dir, task_name)

    logger.warning("annotation_upload: 未知平台 '%s'，跳过上传", platform)
    return ""


def _apply_sam_to_images_dir(images_dir: str, sam, coco_names: list) -> None:
    """
    遍历 images_dir 中图片，读取同名 YOLO .txt，调 SAM 生成 polygon，
    写出 {base}.poly.json: [{"label": str, "points": [[x,y],...], "score": float}]
    """
    import json as _json
    try:
        import cv2
        from PIL import Image as _PILImage
    except ImportError:
        logger.warning("cv2/Pillow 未安装，SAM 预标注跳过")
        return

    IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
    for fname in sorted(os.listdir(images_dir)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in IMAGE_EXT:
            continue
        img_path = os.path.join(images_dir, fname)
        base = os.path.splitext(fname)[0]
        txt_path = os.path.join(images_dir, base + ".txt")
        if not os.path.isfile(txt_path):
            continue

        # 读图尺寸（用 PIL，避免 cv2 解码失败）
        try:
            with _PILImage.open(img_path) as _im:
                w, h = _im.size
        except Exception as e:
            logger.debug("读图尺寸失败 %s: %s", fname, e)
            continue

        # 解析 YOLO .txt → 像素 bbox
        boxes_xyxy = []
        with open(txt_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                try:
                    cid = int(parts[0])
                    cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                except (ValueError, IndexError):
                    continue
                label = coco_names[cid] if cid < len(coco_names) else str(cid)
                x1 = (cx - bw / 2) * w
                y1 = (cy - bh / 2) * h
                x2 = (cx + bw / 2) * w
                y2 = (cy + bh / 2) * h
                boxes_xyxy.append((label, x1, y1, x2, y2))

        if not boxes_xyxy:
            continue

        # 读 BGR 图（SAM 需要）
        img_bgr = cv2.imread(img_path)
        if img_bgr is None:
            continue

        try:
            polygons = sam.boxes_to_polygons(img_bgr, boxes_xyxy)
        except Exception as e:
            logger.warning("SAM boxes_to_polygons 失败 %s: %s", fname, e)
            continue

        if polygons:
            poly_path = os.path.join(images_dir, base + ".poly.json")
            with open(poly_path, "w", encoding="utf-8") as f:
                _json.dump(polygons, f, ensure_ascii=False)


def _upload_cvat(cfg: dict, for_labeling: str, archive_dir: str, task_name: str) -> str:
    """CVAT 上传驱动：导出带置信度标注的图片 → 打包 zip → 上传 CVAT。"""
    import shutil
    from labeling import labeling_export
    from engines.labeling_export import _COCO_NAMES
    sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
    from export_for_cvat import export_task_zip_flat
    from export_for_cvat_native import export_cvat_native

    # 清空旧批次图片，避免混批
    images_dir = os.path.join(for_labeling, "images")
    shutil.rmtree(images_dir, ignore_errors=True)
    os.makedirs(images_dir, exist_ok=True)

    # 导出最新批次（带置信度标注）到 for_labeling
    labeling_export.export_manifest_for_labeling(
        archive_dir, for_labeling, max_batches=1, cfg=cfg,
    )

    # SAM bbox→polygon 预标注（开关控制）
    fm_cfg = cfg.get("foundation_models", {})
    if fm_cfg.get("sam_enabled") and fm_cfg.get("sam_cvat_enabled"):
        try:
            from vision.foundation_models import load_sam_refiner
            sam = load_sam_refiner(cfg)
            if sam:
                _apply_sam_to_images_dir(images_dir, sam, _COCO_NAMES)
                track("sam_refine")
                logger.info("SAM: polygon mask 已生成 -> %s", images_dir)
        except Exception as e:
            logger.warning("SAM 预标注失败，跳过: %s", e)

    upload_pseudo = cfg.get("cvat", {}).get("upload_pseudo_labels", True)
    z1 = os.path.join(for_labeling, "for_cvat.zip")
    z2 = os.path.join(for_labeling, "for_cvat_native.zip") if upload_pseudo else ""
    try:
        export_task_zip_flat(for_labeling, z1)
        if upload_pseudo:
            export_cvat_native(for_labeling, z2, class_names=_COCO_NAMES)
        from cvat_api import auto_cvat_upload
        url = auto_cvat_upload(for_labeling, z1, z2, task_name=task_name)
        logger.info("CVAT 上传成功: %s", url)
        return url or ""
    except Exception as e:
        logger.exception("CVAT 上传失败: %s", e)
        print(f"⚠️ CVAT 自动上传失败: {e}")
        return ""
