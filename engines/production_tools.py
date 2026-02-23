# engines/production_tools.py — 在视频上跑质检并生成 manifest/报告（调用 quality_tools + report_tools）
import os
from typing import List, Any, Dict, Optional

import cv2
from tqdm import tqdm

from . import quality_tools
from . import report_tools
from . import frame_io


def _write_yolo_label(txt_path: str, detections: List[Dict[str, Any]]) -> None:
    """写 YOLO 格式 .txt：每行 class_id x_center y_center w h（归一化）。"""
    lines = []
    for d in detections:
        line = f"{d['class_id']} {d['x_center']:.6f} {d['y_center']:.6f} {d['w']:.6f} {d['h']:.6f}"
        lines.append(line)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_production(
    video_paths: List[str],
    target_dir: str,
    batch_id: str,
    cfg: Dict[str, Any],
    limit_seconds: int = None,
    reports_archive_dir: Optional[str] = None,
    detections_by_video: Optional[Dict[str, Dict[int, List[Dict[str, Any]]]]] = None,
    use_flat_output: bool = False,
) -> int:
    """
    对每段视频按秒抽帧，做质量分析（工具层 raw + 决策层 env），写 Normal/Warning 图、manifest、报告。
    若传入 detections_by_video（video basename -> {frame_idx -> [bbox]}），则对每张写出的小图写同名 .txt 伪标签（YOLO 格式）。
    当 production_setting.save_only_screened=true 时，只落盘「质量异常(Warning) 或 该帧有 YOLO 检测」的帧，减少傻大粗全量切片。
    use_flat_output=True 时（3_待人工精简）：不建 Normal/Warning 子目录，所有图+txt 直接写 target_dir，便于 for_labeling 导入。
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

    for v_path in video_paths:
        v_name = os.path.basename(v_path)
        dets_map = detections_by_video.get(v_name, {})
        fps = int(cv2.VideoCapture(v_path).get(cv2.CAP_PROP_FPS) or 25)

        if use_i_frame:
            max_dur = float(limit_seconds) if limit_seconds else None
            frames_with_idx = frame_io.sample_i_frames(v_path, 1.0, max_duration_seconds=max_dur)
        else:
            frames_with_idx = []
            cap = cv2.VideoCapture(v_path)
            limit = fps * limit_seconds if limit_seconds else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            f_idx = 0
            while cap.isOpened() and f_idx < limit:
                ret, frame = cap.read()
                if not ret:
                    break
                if f_idx % fps == 0:  # 每秒一帧
                    frames_with_idx.append((frame.copy(), f_idx))
                f_idx += 1
            cap.release()

        if not frames_with_idx:
            continue
        pbar = tqdm(total=len(frames_with_idx), desc=f"加工: {v_name[:32]}")
        prev_gray = None
        for frame, f_idx in frames_with_idx:
            raw, gray = quality_tools.analyze_frame(frame, prev_gray)
            prev_gray = gray
            env = quality_tools.decide_env(raw, qc_cfg)
            record = {"frame_id": f_idx, "filename": f"{v_name}_f{f_idx:05d}.jpg", "source": v_name}
            record.update(raw)
            record["env"] = env
            all_stats.append(record)
            img_name = record["filename"]
            has_detection = len(dets_map.get(f_idx, [])) > 0
            if save_only_screened:
                do_write = (env != "Normal" and save_warning) or (has_detection and (save_normal or save_warning))
            else:
                do_write = (env == "Normal" and save_normal) or (env != "Normal" and save_warning)
            out_dir = None
            if do_write:
                if use_flat_output:
                    cv2.imwrite(os.path.join(target_dir, img_name), frame)
                    out_dir = target_dir
                elif env == "Normal" and save_normal:
                    cv2.imwrite(os.path.join(normal_dir, img_name), frame)
                    out_dir = normal_dir
                elif env != "Normal" and save_warning:
                    cv2.imwrite(os.path.join(warning_dir, img_name), frame)
                    out_dir = warning_dir
            if out_dir and detections_by_video is not None:
                base, _ = os.path.splitext(img_name)
                txt_path = os.path.join(out_dir, base + ".txt")
                _write_yolo_label(txt_path, dets_map.get(f_idx, []))
            pbar.update(1)
        pbar.close()

    try:
        report_tools.generate_json_manifest(all_stats, target_dir)
        warning_list = [x for x in all_stats if x.get("env") != "Normal"]
        report_tools.generate_json_manifest(warning_list, target_dir, filename="warning_list.json")
        mode = "QC" if limit_seconds else "Production"
        gate = qc_cfg.get("pass_rate_gate", 80.0)
        report_tools.generate_html_report(
            all_stats, target_dir, batch_id, mode, pass_rate_gate=gate, copy_to_dir=reports_archive_dir
        )
        print("✅ [产线日志] 数字化清单与质量报告已生成完毕。")
    except Exception as e:
        print(f"⚠️ [产线告警] 报告生成环节出现异常，但图片分拣已完成: {e}")
    return len(all_stats)
