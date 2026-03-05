# labeling/annotation_upload.py — 标注平台上传适配层
# 解耦 pipeline 与具体标注平台：main.py 只调用 upload()，换平台改配置即可
import logging
import os
import sys

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
