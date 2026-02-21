# engines/production_tools.py — 在视频上跑质检并生成 manifest/报告（调用 quality_tools + report_tools）
import os
from typing import List, Any, Dict, Optional

import cv2
from tqdm import tqdm

from . import quality_tools
from . import report_tools


def run_production(
    video_paths: List[str],
    target_dir: str,
    batch_id: str,
    cfg: Dict[str, Any],
    limit_seconds: int = None,
    reports_archive_dir: Optional[str] = None,
) -> int:
    """
    对每段视频按秒抽帧，做质量分析（工具层 raw + 决策层 env），写 Normal/Warning 图、manifest、报告。
    cfg 需含 quality_thresholds + production_setting（min_brightness, max_brightness, min_blur_score, ...）。
    返回总采样帧数。
    """
    all_stats: List[Dict[str, Any]] = []
    normal_dir = os.path.join(target_dir, "Normal")
    warning_dir = os.path.join(target_dir, "Warning")
    os.makedirs(normal_dir, exist_ok=True)
    os.makedirs(warning_dir, exist_ok=True)
    qc_cfg = {**cfg.get("quality_thresholds", {}), **cfg.get("production_setting", {})}
    save_normal = qc_cfg.get("save_normal", True)
    save_warning = qc_cfg.get("save_warning", True)

    for v_path in video_paths:
        v_name = os.path.basename(v_path)
        cap = cv2.VideoCapture(v_path)
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25
        prev_gray = None
        limit = fps * limit_seconds if limit_seconds else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        pbar = tqdm(total=limit, desc=f"加工: {v_name[:15]}")
        f_idx = 0
        while cap.isOpened() and f_idx < limit:
            ret, frame = cap.read()
            if not ret:
                break
            if f_idx % fps == 0:
                raw, gray = quality_tools.analyze_frame(frame, prev_gray)
                prev_gray = gray
                env = quality_tools.decide_env(raw, qc_cfg)
                record = {"frame_id": f_idx, "filename": f"{v_name}_f{f_idx:05d}.jpg", "source": v_name}
                record.update(raw)
                record["env"] = env
                all_stats.append(record)
                img_name = record["filename"]
                if env == "Normal":
                    if save_normal:
                        cv2.imwrite(os.path.join(normal_dir, img_name), frame)
                else:
                    if save_warning:
                        cv2.imwrite(os.path.join(warning_dir, img_name), frame)
            f_idx += 1
            pbar.update(1)
        cap.release()
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
