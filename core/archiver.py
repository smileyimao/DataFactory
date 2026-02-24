# core/archiver.py — 归档：丢弃项移动至废片/冗余库，放行项量产并登记
import os
import shutil
import logging
from typing import List, Dict, Any, Tuple, Optional

from config import config_loader
from core import time_utils
from engines import db_tools, production_tools, vision_detector, retry_utils

logger = logging.getLogger(__name__)


def _retry_cfg(cfg: dict) -> tuple:
    """从配置读取重试参数。"""
    r = cfg.get("retry", {})
    return r.get("max_attempts", 3), r.get("backoff_seconds", 1.0)


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
    prefix = config_loader.get_batch_prefix(cfg)
    suffix = config_loader.get_batch_fails_suffix(cfg)
    batch_fails_dir = os.path.join(rejected_dir, f"{prefix}{batch_id}{suffix}")
    os.makedirs(batch_fails_dir, exist_ok=True)
    for item, reason in to_reject:
        src = item.get("archive_path")
        if not src or not os.path.isfile(src):
            continue
        name = item["filename"]
        max_attempts, backoff = _retry_cfg(cfg)
        if reason == "duplicate":
            dest = os.path.join(redundant_dir, name)
            logger.info("Moving [%s] to [%s] due to [Duplicate -> redundant_archives]", name, os.path.abspath(dest))
            if retry_utils.safe_move_with_retry(src, dest, max_attempts, backoff):
                print(f"📦 [冗余库] {name} 已移入 redundant_archives")
        else:
            base, ext = os.path.splitext(name)
            new_name = f"{base}_{item['score']:.0f}pts{ext}"
            dest = os.path.join(batch_fails_dir, new_name)
            logger.info("Moving [%s] to [%s] due to [Rejected material _XXpts]", name, os.path.abspath(dest))
            if retry_utils.safe_move_with_retry(src, dest, max_attempts, backoff):
                print(f"📦 [废片库] {name} -> {new_name}")


def _get_detections_by_video(
    cfg: dict, video_paths: List[str],
) -> Dict[str, Dict[int, List[Dict[str, Any]]]]:
    """对给定视频按 1 秒间隔跑视觉检测，返回 {basename: {frame_idx: [bbox]}} 供写伪标签。"""
    if not video_paths or not vision_detector.is_enabled(cfg):
        return {}
    result = vision_detector.run_vision_scan(
        cfg, video_paths, return_detections=True, sample_seconds_override=1.0,
    )
    out = {}
    for entry in result:
        name = entry.get("name", "")
        if name and "detections_by_frame" in entry:
            out[name] = entry["detections_by_frame"]
    return out


def _run_produce_chunk(
    cfg: dict,
    items: List[Dict[str, Any]],
    target_dir: str,
    batch_id: str,
    label: str,
    detections_by_video: Optional[Dict[str, Dict[int, List[Dict[str, Any]]]]] = None,
    use_flat_output: bool = False,
    skip_html_report: bool = False,
) -> None:
    """对一批 item 执行量产并写入 production_history；可选 detections_by_video 写伪标签。use_flat_output=True 时平铺（无 Normal/Warning）；skip_html_report=True 时燃料目录只保留 manifest+图+txt。"""
    paths = cfg.get("paths", {})
    db_path = paths.get("db_file", "")
    new_video_paths = [x["archive_path"] for x in items if os.path.isfile(x.get("archive_path", ""))]
    if not new_video_paths:
        return
    count = production_tools.run_production(
        new_video_paths, target_dir, batch_id, cfg, limit_seconds=None, detections_by_video=detections_by_video,
        use_flat_output=use_flat_output,
        skip_html_report=skip_html_report,
    )
    print(f"🏆 {label}：共加工 {count} 张样图 -> {os.path.abspath(target_dir)}")
    ts = time_utils.now_toronto(cfg).strftime("%Y-%m-%d %H:%M:%S")
    for x in items:
        if x.get("fingerprint"):
            db_tools.record_production(db_path, batch_id, x["fingerprint"], x["score"], "SUCCESS", created_at=ts)


def archive_produced(
    cfg: dict,
    to_fuel: List[Dict[str, Any]],
    to_human: List[Dict[str, Any]],
    path_info: Dict[str, Any],
) -> None:
    """按置信分层落盘：高置信 -> refinery，复核通过 -> inspection；否则合并写 refinery。"""
    batch_id = path_info.get("batch_id", "")
    tiered = path_info.get("confidence_tiered_output", True)

    if tiered:
        os.makedirs(path_info.get("fuel_dir", ""), exist_ok=True)
        os.makedirs(path_info.get("human_dir", ""), exist_ok=True)
        if to_fuel:
            print(f"\n🏭 [阶段 2] refinery（高置信燃料，共 {len(to_fuel)} 个文件）...")
            fuel_paths = [x["archive_path"] for x in to_fuel if os.path.isfile(x.get("archive_path", ""))]
            fuel_detections = _get_detections_by_video(cfg, fuel_paths)
            _run_produce_chunk(
                cfg, to_fuel,
                path_info["fuel_dir"], batch_id,
                "refinery",
                detections_by_video=fuel_detections,
                use_flat_output=True,
                skip_html_report=True,
            )
        if to_human:
            print(f"\n🏭 [阶段 2] inspection（待人工，共 {len(to_human)} 个文件）...")
            human_paths = [x["archive_path"] for x in to_human if os.path.isfile(x.get("archive_path", ""))]
            human_detections = _get_detections_by_video(cfg, human_paths)
            human_flat = cfg.get("production_setting", {}).get("human_review_flat", False)
            _run_produce_chunk(
                cfg, to_human,
                path_info["human_dir"], batch_id,
                "inspection",
                detections_by_video=human_detections,
                use_flat_output=human_flat,
            )
        if not to_fuel and not to_human:
            print("🛑 无物料进入量产，本批次结束。")
        else:
            print(f"📔 [档案入库] 批次 {batch_id} 的指纹已存入历史大账本。")
        return

    # 兼容：不按置信分层时，合并写 2_Mass_Production
    to_produce = to_fuel + to_human
    if not to_produce:
        print("🛑 无物料进入量产，本批次结束。")
        return
    mass_dir = path_info.get("mass_dir", "")
    print(f"\n🏭 [阶段 2] 量产（共 {len(to_produce)} 个文件）-> refinery...")
    _run_produce_chunk(cfg, to_produce, mass_dir, batch_id, "refinery")
    print(f"📔 [档案入库] 批次 {batch_id} 的指纹已存入历史大账本。")
