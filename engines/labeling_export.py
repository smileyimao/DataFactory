# engines/labeling_export.py — 为接入 ML 做准备：导出合格/待标注清单，供 Label Studio / CVAT 等使用
"""
数据清洗与标注管道扩展（Roadmap v1 可选）：
扫描 storage/archive 下已归档批次，生成「待标注清单」manifest（路径、batch_id、元数据），
便于下游标注工具导入，避免重复标注已去重数据。
同时将图片及同名 .txt 拷贝到 export_dir/images/，下游可直接拷走整个 for_labeling 目录。
"""
import os
import json
import logging
import shutil
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 常见可标注媒体扩展
MEDIA_EXT = {".mp4", ".mov", ".avi", ".mkv", ".jpg", ".jpeg", ".png", ".bmp"}


# 产出子目录：按置信分层（2_高置信_燃料、3_待人工）或旧版单一 2_Mass_Production
OUTPUT_SUBDIRS = ("2_高置信_燃料", "3_待人工", "2_Mass_Production")


def list_batch_media(batch_dir: str) -> List[Dict[str, Any]]:
    """扫描 Batch 目录下产出子目录（2_高置信_燃料、3_待人工、2_Mass_Production）及 1_QC 中的媒体文件。
    支持两种结构：1) 子目录内直接 .jpg/.png；2) 子目录内 Normal/、Warning/ 含媒体文件。"""
    out = []
    qc_sub = "1_QC" if os.path.isdir(os.path.join(batch_dir, "1_QC")) else "1_Pilot_Room"
    for sub in OUTPUT_SUBDIRS + (qc_sub,):
        d = os.path.join(batch_dir, sub)
        if not os.path.isdir(d):
            continue
        # 收集媒体文件：直接子目录或 Normal/Warning 下
        for root, _, files in os.walk(d, topdown=True):
            for name in sorted(files):
                ext = os.path.splitext(name)[1].lower()
                if ext not in MEDIA_EXT:
                    continue
                full = os.path.join(root, name)
                if not os.path.isfile(full):
                    continue
                rel = os.path.relpath(full, batch_dir)
                out.append({
                    "path": full,
                    "relative_path": rel,
                    "filename": name,
                    "subdir": sub,
                })
    return out


def export_manifest_for_labeling(
    archive_dir: str,
    export_dir: str,
    max_batches: Optional[int] = None,
) -> str:
    """
    扫描 archive_dir 下所有 Batch_* 目录，汇总媒体文件清单，写入 export_dir/manifest_for_labeling.json。
    返回写入的 manifest 文件路径。
    """
    os.makedirs(export_dir, exist_ok=True)
    batch_dirs = sorted([
        os.path.join(archive_dir, x)
        for x in os.listdir(archive_dir)
        if os.path.isdir(os.path.join(archive_dir, x)) and x.startswith("Batch_")
    ])
    if max_batches is not None:
        batch_dirs = batch_dirs[-max_batches:]

    manifest = []
    for batch_dir in batch_dirs:
        batch_id = os.path.basename(batch_dir)
        items = list_batch_media(batch_dir)
        for item in items:
            item["batch_id"] = batch_id
            manifest.append(item)

    out_path = os.path.join(export_dir, "manifest_for_labeling.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    logger.info("导出待标注清单: %d 条, 写入 %s", len(manifest), out_path)

    # 一键拷走：图片 + 同名 .txt 到 images/，用 batch_id_filename 避免跨批次重名
    images_dir = os.path.join(export_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    copied = 0
    for item in manifest:
        src_path = item["path"]
        batch_id = item["batch_id"]
        filename = item["filename"]
        base, ext = os.path.splitext(filename)
        dest_name = f"{batch_id}_{filename}"
        dest_path = os.path.join(images_dir, dest_name)
        try:
            shutil.copy2(src_path, dest_path)
            copied += 1
        except OSError as e:
            logger.warning("拷贝媒体失败 %s -> %s: %s", src_path, dest_path, e)
        # 同名 .txt（YOLO 伪标签）
        txt_src = os.path.join(os.path.dirname(src_path), base + ".txt")
        if os.path.isfile(txt_src):
            txt_dest = os.path.join(images_dir, f"{batch_id}_{base}.txt")
            try:
                shutil.copy2(txt_src, txt_dest)
            except OSError as e:
                logger.warning("拷贝 txt 失败 %s -> %s: %s", txt_src, txt_dest, e)
    logger.info("已拷贝 %d 个媒体文件及同名 .txt 到 %s", copied, images_dir)
    return out_path


def run_export_from_config(cfg: Dict[str, Any], max_batches: Optional[int] = None) -> Optional[str]:
    """
    从配置读取 paths.data_warehouse（archive）与 paths.labeling_export（导出目录），
    若存在 labeling_export 则执行导出并返回 manifest 路径；否则返回 None。
    """
    paths = cfg.get("paths", {})
    archive = paths.get("data_warehouse", "")
    export_dir = paths.get("labeling_export")
    if not export_dir or not os.path.isdir(archive):
        return None
    return export_manifest_for_labeling(archive, export_dir, max_batches=max_batches)


def _collect_media_from_dir(dir_path: str) -> List[Dict[str, Any]]:
    """从目录递归收集媒体文件（含 Normal/Warning 子目录或平铺）。"""
    out = []
    if not os.path.isdir(dir_path):
        return out
    for root, _, files in os.walk(dir_path, topdown=True):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in MEDIA_EXT:
                continue
            full = os.path.join(root, name)
            if not os.path.isfile(full):
                continue
            out.append({"path": full, "filename": name})
    return out


def auto_update_after_batch(cfg: Dict[str, Any], path_info: Dict[str, Any]) -> Optional[str]:
    """
    待标池自动更新：本批次 3_待人工 的媒体文件追加到 for_labeling，并合并 manifest。
    若配置 labeling_pool.auto_update_after_batch 为 false 则跳过。
    返回 manifest 路径或 None。
    """
    pool_cfg = cfg.get("labeling_pool") or {}
    if not pool_cfg.get("auto_update_after_batch", True):
        return None
    paths = cfg.get("paths", {})
    export_dir = paths.get("labeling_export")
    human_dir = path_info.get("human_dir", "")
    batch_id = path_info.get("batch_id", "")
    if not export_dir or not human_dir or not batch_id:
        return None
    items = _collect_media_from_dir(human_dir)
    if not items:
        return None
    images_dir = os.path.join(export_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    manifest_path = os.path.join(export_dir, "manifest_for_labeling.json")
    existing = []
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            logger.warning("读取现有 manifest 失败，将覆盖: %s", e)
    seen = {f"{x.get('batch_id', '')}_{x.get('filename', '')}" for x in existing}
    added = 0
    for item in items:
        src_path = item["path"]
        filename = item["filename"]
        base, ext = os.path.splitext(filename)
        dest_name = f"{batch_id}_{filename}"
        if dest_name in seen:
            continue
        seen.add(dest_name)
        dest_path = os.path.join(images_dir, dest_name)
        try:
            shutil.copy2(src_path, dest_path)
            added += 1
        except OSError as e:
            logger.warning("拷贝媒体失败 %s -> %s: %s", src_path, dest_path, e)
        txt_src = os.path.join(os.path.dirname(src_path), base + ".txt")
        if os.path.isfile(txt_src):
            txt_dest = os.path.join(images_dir, f"{batch_id}_{base}.txt")
            try:
                shutil.copy2(txt_src, txt_dest)
            except OSError as e:
                logger.warning("拷贝 txt 失败 %s -> %s: %s", txt_src, txt_dest, e)
        existing.append({
            "path": dest_path,
            "relative_path": f"images/{dest_name}",
            "filename": filename,
            "subdir": "3_待人工",
            "batch_id": batch_id,
        })
    if added > 0:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        logger.info("待标池自动更新: 本批 3_待人工 追加 %d 条 -> %s", added, manifest_path)
        return manifest_path
    return None
