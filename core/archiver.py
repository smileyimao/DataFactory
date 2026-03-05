# core/archiver.py — 归档：丢弃项移动至废片/冗余库，放行项量产并登记
import os
import shutil
import logging
from typing import List, Dict, Any, Tuple, Optional

from config import config_loader
from utils import time_utils
from engines import db_tools, production_tools, vision_detector
from utils import retry_utils

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


def _split_approved_by_vision_conf(
    cfg: dict,
    items: List[Dict[str, Any]],
    precomputed_detections: Optional[Dict[str, Dict[int, List[Dict[str, Any]]]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Dict[int, List[Dict[str, Any]]]]]:
    """
    放行项按 YOLO 置信度分流：高置信 -> refinery，低置信/无检测 -> inspection。
    若 vision 未开启，全部进 refinery（用户已认可）。
    若传入 precomputed_detections（QC 阶段结果），则复用，不再跑 YOLO。
    返回 (to_fuel, to_human, detections_by_video) 供后续量产复用。
    """
    from engines import vision_detector
    threshold = float(cfg.get("production_setting", {}).get("approved_split_confidence_threshold", 0.6))
    video_paths = [x["archive_path"] for x in items if os.path.isfile(x.get("archive_path", ""))]
    empty_dets: Dict[str, Dict[int, List[Dict[str, Any]]]] = {}
    if not video_paths or not vision_detector.is_enabled(cfg):
        return list(items), [], empty_dets  # vision 未开启：全部 refinery

    video_tier_map: Dict[str, str] = {}

    if precomputed_detections:
        detections_by_video = precomputed_detections
        # precomputed 来自 QC 阶段采样帧少，分级不准，跳过视频级分级
    else:
        sample_sec = float((cfg.get("vision") or {}).get("sample_seconds", 10))
        result = vision_detector.run_vision_scan(
            cfg, video_paths, return_detections=True, sample_seconds_override=sample_sec,
        )
        detections_by_video = {}
        for entry in result:
            name = entry.get("name", "")
            dets_map = entry.get("detections_by_frame") or {}
            detections_by_video[name] = dets_map

        # 视频级三档分流（仅非 precomputed 路径）
        total_frames_by_video = {e.get("name", ""): e.get("n_frames", 0) for e in result}
        video_tier_map = production_tools.compute_video_tiers(
            detections_by_video, total_frames_by_video, cfg
        )

    name_to_max_conf: Dict[str, float] = {}
    for name, dets_map in detections_by_video.items():
        max_conf = 0.0
        for frame_dets in (dets_map or {}).values():
            for d in frame_dets:
                c = d.get("conf", 0.0)
                if c > max_conf:
                    max_conf = c
        name_to_max_conf[name] = max_conf

    to_fuel: List[Dict[str, Any]] = []
    to_human: List[Dict[str, Any]] = []
    for item in items:
        bname = os.path.basename(item.get("archive_path", ""))
        max_conf = name_to_max_conf.get(bname, 0.0)
        tier = video_tier_map.get(bname, "standard")
        if max_conf >= threshold and tier != "low":
            to_fuel.append(item)
        else:
            to_human.append(item)

    if video_tier_map:
        high_n = sum(1 for t in video_tier_map.values() if t == "high")
        std_n  = sum(1 for t in video_tier_map.values() if t == "standard")
        low_n  = sum(1 for t in video_tier_map.values() if t == "low")
        print(f"   📊 视频分级: 高质 {high_n}  标准 {std_n}  低质 {low_n}（低质 → inspection）")

    return to_fuel, to_human, detections_by_video


def archive_approved_items(
    cfg: dict,
    items: List[Dict[str, Any]],
    path_info: Dict[str, Any],
) -> None:
    """
    放行项：先跑 YOLO，按置信度分流到 refinery / inspection，再量产（复用同次 YOLO 结果）。
    """
    qc_dets = path_info.get("qc_detections_by_video") or {}
    to_fuel, to_human, detections_by_video = _split_approved_by_vision_conf(
        cfg, items, precomputed_detections=qc_dets if qc_dets else None
    )
    if qc_dets:
        print("   ♻️ 复用 QC 阶段 YOLO 结果")
    if to_fuel or to_human:
        print(f"   📊 放行项按 YOLO 置信度分流: {len(to_fuel)} → refinery, {len(to_human)} → inspection")
    batch_id = path_info.get("batch_id", "")
    tiered = path_info.get("confidence_tiered_output", True)
    if not tiered:
        to_fuel = to_fuel + to_human
        to_human = []
    os.makedirs(path_info.get("fuel_dir", ""), exist_ok=True)
    os.makedirs(path_info.get("human_dir", ""), exist_ok=True)
    if to_fuel:
        print(f"\n🏭 [阶段 2] refinery（放行高置信，共 {len(to_fuel)} 个文件）...")
        _run_produce_chunk(
            cfg, to_fuel, path_info["fuel_dir"], batch_id, "refinery",
            detections_by_video=detections_by_video if detections_by_video else None,
            use_flat_output=True, skip_html_report=True,
        )
    if to_human:
        print(f"\n🏭 [阶段 2] inspection（放行待人工，共 {len(to_human)} 个文件）...")
        human_flat = cfg.get("production_setting", {}).get("human_review_flat", False)
        _run_produce_chunk(
            cfg, to_human, path_info["human_dir"], batch_id, "inspection",
            detections_by_video=detections_by_video if detections_by_video else None,
            use_flat_output=human_flat,
        )
    if to_fuel or to_human:
        print(f"📔 [档案入库] 批次 {batch_id} 的指纹已存入历史大账本。")


def _get_detections_by_video(
    cfg: dict, video_paths: List[str],
) -> Dict[str, Dict[int, List[Dict[str, Any]]]]:
    """对给定视频按 vision.sample_seconds 间隔跑视觉检测，返回 {basename: {frame_idx: [bbox]}} 供写伪标签。"""
    if not video_paths or not vision_detector.is_enabled(cfg):
        return {}
    sample_sec = float((cfg.get("vision") or {}).get("sample_seconds", 10))
    result = vision_detector.run_vision_scan(
        cfg, video_paths, return_detections=True, sample_seconds_override=sample_sec,
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
    inspection_dir: str = "",
) -> None:
    """对一批 item 执行量产并写入 production_history。
    inspection_dir 非空时启用帧级分流：高置信帧 → target_dir(refinery)，低置信/无检测帧 → inspection_dir。
    """
    paths = cfg.get("paths", {})
    db_path = paths.get("db_url", "")
    new_video_paths = [x["archive_path"] for x in items if os.path.isfile(x.get("archive_path", ""))]
    if not new_video_paths:
        return
    count = production_tools.run_production(
        new_video_paths, target_dir, batch_id, cfg, limit_seconds=None, detections_by_video=detections_by_video,
        use_flat_output=use_flat_output,
        skip_html_report=skip_html_report,
        inspection_dir=inspection_dir,
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
        fuel_dir = path_info.get("fuel_dir", "")
        human_dir = path_info.get("human_dir", "")
        os.makedirs(fuel_dir, exist_ok=True)
        os.makedirs(human_dir, exist_ok=True)
        qc_detections = path_info.get("qc_detections_by_video") or {}
        all_items = to_fuel + to_human
        if not all_items:
            print("🛑 无物料进入量产，本批次结束。")
        else:
            if qc_detections:
                print("   ♻️ 复用 QC 阶段 YOLO 结果，跳过二次推理")
                detections = qc_detections
            else:
                all_paths = [x["archive_path"] for x in all_items if os.path.isfile(x.get("archive_path", ""))]
                detections = _get_detections_by_video(cfg, all_paths)
            print(f"\n🏭 [阶段 2] 帧级分流（共 {len(all_items)} 个文件）→ refinery / inspection ...")
            _run_produce_chunk(
                cfg, all_items,
                fuel_dir, batch_id,
                "refinery+inspection",
                detections_by_video=detections,
                use_flat_output=True,
                skip_html_report=True,
                inspection_dir=human_dir,
            )
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
