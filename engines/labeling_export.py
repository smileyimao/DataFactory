# engines/labeling_export.py — 为接入 ML 做准备：导出合格/待标注清单，供 Label Studio / CVAT 等使用
"""
数据清洗与标注管道扩展（Roadmap v1 可选）：
扫描 storage/archive 下已归档批次，生成「待标注清单」manifest（路径、batch_id、元数据），
便于下游标注工具导入，避免重复标注已去重数据。
"""
import os
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 常见可标注媒体扩展
MEDIA_EXT = {".mp4", ".mov", ".avi", ".mkv", ".jpg", ".jpeg", ".png", ".bmp"}


def list_batch_media(batch_dir: str) -> List[Dict[str, Any]]:
    """扫描 Batch 目录下 2_Mass_Production、1_QC（无则用 1_Pilot_Room 兼容旧批次）中的媒体文件。"""
    out = []
    qc_sub = "1_QC" if os.path.isdir(os.path.join(batch_dir, "1_QC")) else "1_Pilot_Room"
    for sub in ("2_Mass_Production", qc_sub):
        d = os.path.join(batch_dir, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            ext = os.path.splitext(name)[1].lower()
            if ext not in MEDIA_EXT:
                continue
            full = os.path.join(d, name)
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
