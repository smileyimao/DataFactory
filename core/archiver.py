# core/archiver.py — 归档：丢弃项移动至废片/冗余库，放行项量产并登记
import os
import shutil
import logging
from typing import List, Dict, Any, Tuple

from engines import db_tools, production_tools
from core.qc_engine import now_toronto

logger = logging.getLogger(__name__)


def archive_rejected(
    cfg: dict,
    to_reject: List[Tuple[Dict[str, Any], str]],
    batch_id: str,
) -> None:
    """将 to_reject 中项按 reason 移至 rejected_material 或 redundant_archives。"""
    paths = cfg.get("paths", {})
    rejected_dir = paths.get("rejected_material", "")
    redundant_dir = paths.get("redundant_archives", "")
    os.makedirs(rejected_dir, exist_ok=True)
    os.makedirs(redundant_dir, exist_ok=True)
    batch_fails_dir = os.path.join(rejected_dir, f"Batch_{batch_id}_Fails")
    os.makedirs(batch_fails_dir, exist_ok=True)
    for item, reason in to_reject:
        src = item.get("archive_path")
        if not src or not os.path.isfile(src):
            continue
        name = item["filename"]
        if reason == "duplicate":
            dest = os.path.join(redundant_dir, name)
            logger.info("Moving [%s] to [%s] due to [Duplicate -> redundant_archives]", name, os.path.abspath(dest))
            try:
                shutil.move(src, dest)
                print(f"📦 [冗余库] {name} 已移入 redundant_archives")
            except Exception as e:
                logger.exception("冗余库移动失败: %s -> %s", name, e)
        else:
            base, ext = os.path.splitext(name)
            new_name = f"{base}_{item['score']:.0f}pts{ext}"
            dest = os.path.join(batch_fails_dir, new_name)
            logger.info("Moving [%s] to [%s] due to [Rejected material _XXpts]", name, os.path.abspath(dest))
            try:
                shutil.move(src, dest)
                print(f"📦 [废片库] {name} -> {new_name}")
            except Exception as e:
                logger.exception("废片移动失败: %s -> %s", name, e)


def archive_produced(
    cfg: dict,
    to_produce: List[Dict[str, Any]],
    path_info: Dict[str, Any],
) -> None:
    """对 to_produce 执行量产（写 2_Mass_Production）并写入 production_history。"""
    paths = cfg.get("paths", {})
    db_path = paths.get("db_file", "")
    mass_dir = path_info.get("mass_dir", "")
    batch_id = path_info.get("batch_id", "")
    if not to_produce:
        print("🛑 无物料进入量产，本批次结束。")
        return
    new_video_paths = [x["archive_path"] for x in to_produce if os.path.isfile(x.get("archive_path", ""))]
    if not new_video_paths:
        print("❌ 量产列表为空或文件已移动，跳过量产。")
        return
    print(f"\n🏭 [阶段 2] 大规模制造流水线（共 {len(new_video_paths)} 个文件）...")
    count = production_tools.run_production(new_video_paths, mass_dir, batch_id, cfg, limit_seconds=None)
    print(f"🏆 量产报捷！共加工 {count} 张样图，成品存放在: {os.path.abspath(mass_dir)}")
    ts = now_toronto().strftime("%Y-%m-%d %H:%M:%S")
    for x in to_produce:
        if x.get("fingerprint"):
            db_tools.record_production(db_path, batch_id, x["fingerprint"], x["score"], "SUCCESS", created_at=ts)
    print(f"📔 [档案入库] 批次 {batch_id} 的指纹已存入历史大账本。")
