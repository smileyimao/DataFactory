# vision/production_tools.py — 在视频/图片上跑质检并生成 manifest/报告（调用 quality_tools + report_tools）
import os
import shutil
import logging
from typing import List, Any, Dict, Optional

import cv2
from tqdm import tqdm

from utils import file_tools

logger = logging.getLogger(__name__)
from . import quality_tools
from utils import report_tools
from . import frame_io

IMAGE_EXT = (".jpg", ".jpeg", ".png")


def compute_video_tiers(
    detections_by_video: dict,
    total_frames_by_video: dict,
    cfg: dict,
) -> dict:
    """
    按视频整体质量分三档：
      high     = hit_rate >= high_detection_rate AND mean_conf >= high_conf
      low      = hit_rate < low_detection_rate OR mean_conf < low_conf
      standard = 其余
    若 total_frames_by_video 为空，退回仅用 mean_conf（无 hit_rate 时不判 hit_rate 条件）。
    """
    prod_cfg = cfg.get("production_setting", {})
    high_dr   = float(prod_cfg.get("video_tier_high_detection_rate", 0.60))
    high_conf = float(prod_cfg.get("video_tier_high_conf", 0.70))
    low_dr    = float(prod_cfg.get("video_tier_low_detection_rate", 0.30))
    low_conf  = float(prod_cfg.get("video_tier_low_conf", 0.50))

    use_hit_rate = bool(total_frames_by_video)
    tiers: dict = {}

    for name, dets_map in detections_by_video.items():
        # 检测帧最高置信度的均值
        frame_max_confs = [
            max((d.get("conf", 0.0) for d in frame_dets), default=0.0)
            for frame_dets in (dets_map or {}).values()
            if frame_dets
        ]
        mean_conf = sum(frame_max_confs) / len(frame_max_confs) if frame_max_confs else 0.0

        if use_hit_rate:
            n_total  = total_frames_by_video.get(name, 0)
            hit_frames = sum(1 for v in (dets_map or {}).values() if v)
            hit_rate = hit_frames / n_total if n_total > 0 else 0.0
            if hit_rate < low_dr or mean_conf < low_conf:
                tiers[name] = "low"
            elif hit_rate >= high_dr and mean_conf >= high_conf:
                tiers[name] = "high"
            else:
                tiers[name] = "standard"
        else:
            # 无采样帧数，仅用 mean_conf
            if mean_conf < low_conf:
                tiers[name] = "low"
            elif mean_conf >= high_conf:
                tiers[name] = "high"
            else:
                tiers[name] = "standard"

    return tiers


def _is_image_path(path: str) -> bool:
    return any(path.lower().endswith(ext) for ext in IMAGE_EXT)


def _find_label_path(image_path: str) -> Optional[str]:
    """YOLO 格式：images/xxx.jpg 对应 labels/xxx.txt。返回 label 路径，不存在则 None。"""
    parent = os.path.dirname(os.path.dirname(image_path))
    base = os.path.splitext(os.path.basename(image_path))[0]
    label_path = os.path.join(parent, "labels", base + ".txt")
    return label_path if os.path.isfile(label_path) else None


def _write_yolo_label(txt_path: str, detections: List[Dict[str, Any]]) -> None:
    """写 YOLO 格式 .txt：每行 class_id x_center y_center w h [conf]。含 conf 时写第 6 列供 CVAT 显示置信度。"""
    lines = []
    for d in detections:
        line = f"{d['class_id']} {d['x_center']:.6f} {d['y_center']:.6f} {d['w']:.6f} {d['h']:.6f}"
        if "conf" in d:
            line += f" {d['conf']:.4f}"
        lines.append(line)
    file_tools.atomic_write_text(txt_path, "\n".join(lines))


def run_production(
    video_paths: List[str],
    target_dir: str,
    batch_id: str,
    cfg: Dict[str, Any],
    limit_seconds: int = None,
    reports_archive_dir: Optional[str] = None,
    detections_by_video: Optional[Dict[str, Dict[int, List[Dict[str, Any]]]]] = None,
    use_flat_output: bool = False,
    skip_html_report: bool = False,
    inspection_dir: str = "",
    **kwargs,
) -> int:
    """
    对每段视频按 vision.sample_seconds 抽帧，做质量分析，写 Normal/Warning 图、manifest、报告。
    若传入 detections_by_video，对每张写出的小图写同名 .txt 伪标签（YOLO 格式）。
    inspection_dir 非空时启用帧级分流：帧最高置信 >= approved_split_confidence_threshold → target_dir(refinery)，否则 → inspection_dir。
    use_flat_output=True 时平铺输出；skip_html_report=True 时燃料目录只保留 manifest+图+txt。
    cfg 需含 quality_thresholds + production_setting。
    返回总采样帧数。
    """
    all_stats: List[Dict[str, Any]] = []
    qc_cfg = {**cfg.get("quality_thresholds", {}), **cfg.get("production_setting", {})}
    if use_flat_output:
        out_dir = target_dir
        os.makedirs(out_dir, exist_ok=True)
    else:
        normal_dir = os.path.join(target_dir, "Normal")
        warning_dir = os.path.join(target_dir, "Warning")
        os.makedirs(normal_dir, exist_ok=True)
        os.makedirs(warning_dir, exist_ok=True)
    save_normal = qc_cfg.get("save_normal", True)
    save_warning = qc_cfg.get("save_warning", True)
    save_only_screened = qc_cfg.get("save_only_screened", False)
    use_i_frame = bool(cfg.get("vision", {}).get("use_i_frame_only", False))
    detections_by_video = detections_by_video or {}
    # 帧级分流参数
    do_frame_split = bool(inspection_dir)
    if do_frame_split:
        os.makedirs(inspection_dir, exist_ok=True)
        # 动态门槛：取所有检测帧最高置信度分布的第 N 百分位
        # refinery_top_pct=30 → 置信度前 30% 的帧进 refinery，其余进 inspection
        refinery_top_pct = float(qc_cfg.get("refinery_top_pct", 30))
        all_frame_confs = [
            max((d.get("conf", 0.0) for d in dets), default=0.0)
            for dets_map in detections_by_video.values()
            for dets in dets_map.values()
        ]
        detected_confs = [c for c in all_frame_confs if c > 0]
        refinery_min_conf = float(qc_cfg.get("refinery_min_confidence", 0.65))
        if detected_confs:
            detected_confs.sort()
            cutoff_idx = max(0, int(len(detected_confs) * (1 - refinery_top_pct / 100)) - 1)
            conf_threshold = detected_confs[cutoff_idx]
        else:
            conf_threshold = float(qc_cfg.get("approved_split_confidence_threshold", 0.60))
        logger.info("动态分流门槛: %s（前 %s%% 高置信帧 → refinery，绝对下限 %s）", conf_threshold, refinery_top_pct, refinery_min_conf)
    else:
        conf_threshold = float(qc_cfg.get("approved_split_confidence_threshold", 0.60))
    # 归档阶段帧提取间隔与 YOLO 检测对齐；QC 阶段（limit_seconds 非空）仍用 1 秒
    _sample_sec = float(cfg.get("vision", {}).get("sample_seconds", 1.0)) if not limit_seconds else 1.0

    best_frame_sel = bool(qc_cfg.get("best_frame_selection", False))
    best_frame_top_k = int(qc_cfg.get("best_frame_top_k", 5))

    _desc = kwargs.pop("tqdm_desc", "Processing")
    pbar = tqdm(video_paths, desc=_desc, unit="file")
    for v_path in pbar:
        v_name = os.path.basename(v_path)
        dets_map = detections_by_video.get(v_name, {})

        if _is_image_path(v_path):
            frame = cv2.imread(v_path)
            if frame is None:
                continue
            frames_with_idx = [(frame, 0)]
        else:
            fps = int(cv2.VideoCapture(v_path).get(cv2.CAP_PROP_FPS) or 25)
            if use_i_frame:
                max_dur = float(limit_seconds) if limit_seconds else None
                frames_with_idx = frame_io.sample_i_frames(v_path, 1.0, max_duration_seconds=max_dur)
            else:
                frames_with_idx = []
                cap = cv2.VideoCapture(v_path)
                limit = fps * limit_seconds if limit_seconds else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                step = max(1, int(fps * _sample_sec))
                f_idx = 0
                while cap.isOpened() and f_idx < limit:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if f_idx % step == 0:
                        frames_with_idx.append((frame.copy(), f_idx))
                    f_idx += 1
                cap.release()

        if not frames_with_idx:
            continue

        # -- Pass 1: analyze all frames, collect scores --
        candidates = []
        prev_gray = None
        for frame, f_idx in frames_with_idx:
            raw, gray = quality_tools.analyze_frame(frame, prev_gray)
            prev_gray = gray
            env = quality_tools.decide_env(raw, qc_cfg)
            safe_name = file_tools.sanitize_filename(v_name)
            out_img_name = safe_name if _is_image_path(v_path) else f"{safe_name}_f{f_idx:05d}.jpg"
            record = {"frame_id": f_idx, "filename": out_img_name, "source": v_name}
            record.update(raw)
            record["env"] = env

            frame_dets = dets_map.get(f_idx, [])
            mean_conf = (sum(d.get("conf", 0.0) for d in frame_dets) / len(frame_dets)) if frame_dets else 0.0
            sharpness = raw.get("bl", 0.0)
            bf_score = mean_conf * sharpness
            record["_bf_score"] = bf_score

            candidates.append((frame, f_idx, record, env, frame_dets))

        # -- Pass 2: if best-frame selection is on, keep only top-K per video --
        if best_frame_sel and len(candidates) > best_frame_top_k and not _is_image_path(v_path):
            candidates.sort(key=lambda c: c[2]["_bf_score"], reverse=True)
            kept = candidates[:best_frame_top_k]
            kept.sort(key=lambda c: c[1])
            logger.info("Best-frame: %s — %d/%d frames kept (top_k=%d)",
                        v_name, len(kept), len(candidates), best_frame_top_k)
            candidates = kept

        # -- Pass 3: write selected frames --
        for frame, f_idx, record, env, frame_dets in candidates:
            all_stats.append(record)
            img_name = record["filename"]
            has_detection = len(frame_dets) > 0
            if save_only_screened:
                do_write = (env != "Normal" and save_warning) or (has_detection and (save_normal or save_warning))
            else:
                do_write = (env == "Normal" and save_normal) or (env != "Normal" and save_warning)
            out_dir = None
            if do_write:
                if do_frame_split:
                    max_conf = max((d.get("conf", 0.0) for d in frame_dets), default=0.0) if frame_dets else 0.0
                    write_dir = target_dir if (max_conf >= conf_threshold and max_conf >= refinery_min_conf) else inspection_dir
                    cv2.imwrite(os.path.join(write_dir, img_name), frame)
                    out_dir = write_dir
                elif use_flat_output:
                    cv2.imwrite(os.path.join(target_dir, img_name), frame)
                    out_dir = target_dir
                elif env == "Normal" and save_normal:
                    cv2.imwrite(os.path.join(normal_dir, img_name), frame)
                    out_dir = normal_dir
                elif env != "Normal" and save_warning:
                    cv2.imwrite(os.path.join(warning_dir, img_name), frame)
                    out_dir = warning_dir
            if out_dir:
                base, _ = os.path.splitext(img_name)
                txt_path = os.path.join(out_dir, base + ".txt")
                dets = frame_dets if detections_by_video else []
                if dets:
                    _write_yolo_label(txt_path, dets)
                elif _is_image_path(v_path):
                    label_src = _find_label_path(v_path)
                    if label_src:
                        try:
                            shutil.copy2(label_src, txt_path)
                        except OSError:
                            pass

    try:
        report_tools.generate_json_manifest(all_stats, target_dir)
        if not skip_html_report:
            warning_list = [x for x in all_stats if x.get("env") != "Normal"]
            report_tools.generate_json_manifest(warning_list, target_dir, filename="warning_list.json")
            mode = "QC" if limit_seconds else "Production"
            gate = qc_cfg.get("pass_rate_gate", 80.0)
            report_tools.generate_html_report(
                all_stats, target_dir, batch_id, mode, pass_rate_gate=gate, copy_to_dir=reports_archive_dir
            )
            logger.info("产线日志: 数字化清单与质量报告已生成完毕")
        else:
            logger.info("产线日志: 数字化清单已生成（燃料目录，无报告）")
    except Exception as e:
        logger.warning("产线告警: 报告生成环节出现异常，但图片分拣已完成: %s", e)
    return len(all_stats)
