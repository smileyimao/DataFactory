# core/qc_engine.py — 质检编排：指纹、质量检测、建档、发邮件，决策合格/不合格/重复（无试产，进厂即质检）
import os
import json
import shutil
import logging
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Tuple

from config import config_loader
from engines import fingerprinter, db_tools, notifier, production_tools, vision_detector, report_tools

logger = logging.getLogger(__name__)


def now_toronto() -> datetime:
    return datetime.now(ZoneInfo("America/Toronto"))


def run_qc(
    cfg: dict,
    video_paths: List[str],
) -> Tuple[List[Dict], List[Dict], List[Dict], List[Tuple[Dict, str]], Dict[str, Any]]:
    """
    执行质检流程：指纹（重复检测）-> 质量检测（不合格检测）-> 源文件归档 -> 建 qc_archive -> 发邮件。
    返回 (qc_archive, qualified, blocked, auto_reject, path_info)。
    path_info 含 qc_dir, source_archive_dir, mass_dir, report_path 等供后续使用。
    v2 双门槛：若配置 dual_gate_high/dual_gate_low，则 score>=high 自动放行、score<low 自动拦截、中间态进 blocked 人工复核；否则单门槛 gate。
    """
    paths = cfg.get("paths", {})
    warehouse = paths.get("data_warehouse", "")
    db_path = paths.get("db_file", "")
    qc_cfg = config_loader.get_quality_thresholds(cfg)
    qc_sample_seconds = qc_cfg.get("qc_sample_seconds", 10)  # 每视频抽检秒数，用于质量判定
    gate = float(qc_cfg.get("pass_rate_gate", 80.0))
    dual_high = qc_cfg.get("dual_gate_high")
    dual_low = qc_cfg.get("dual_gate_low")
    use_dual_gate = dual_high is not None and dual_low is not None
    if use_dual_gate:
        dual_high = float(dual_high)
        dual_low = float(dual_low)

    batch_id = now_toronto().strftime("%Y%m%d_%H%M%S")
    batch_base = os.path.join(warehouse, f"Batch_{batch_id}")
    qc_dir = os.path.join(batch_base, "1_QC")
    source_archive_dir = os.path.join(batch_base, "0_Source_Video")
    mass_dir = os.path.join(batch_base, "2_Mass_Production")
    fuel_dir = os.path.join(batch_base, "2_高置信_燃料")
    human_dir = os.path.join(batch_base, "3_待人工")

    path_to_md5: Dict[str, str] = {}
    for v in video_paths:
        fp = fingerprinter.compute(v) or ""
        path_to_md5[v] = fp
        logger.info("指纹采集结果: 文件=%s 指纹=%s", os.path.basename(v), (fp[:16] + "...") if len(fp) > 16 else fp)

    os.makedirs(qc_dir, exist_ok=True)
    reports_dir = paths.get("reports", "")
    print(f"\n🚀 [质检] 批次: {batch_id} | 重复检测 + 质量检测（抽检 {qc_sample_seconds}s/视频）")
    production_tools.run_production(
        video_paths, qc_dir, batch_id, cfg, limit_seconds=qc_sample_seconds, reports_archive_dir=reports_dir or None
    )

    os.makedirs(source_archive_dir, exist_ok=True)
    for v_path in video_paths:
        dest = os.path.join(source_archive_dir, os.path.basename(v_path))
        try:
            logger.info("Moving [%s] to [%s] due to [Batch archive 0_Source_Video]", os.path.basename(v_path), os.path.abspath(dest))
            shutil.move(v_path, dest)
            print(f"📦 [归档成功]: {os.path.basename(v_path)} -> 0_Source_Video")
        except Exception as e:
            logger.exception("归档失败: %s -> %s", v_path, e)
            print(f"⚠️ [归档失败]: {v_path} -> {e}")

    manifest_path = os.path.join(qc_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    by_source = defaultdict(lambda: {"normal": 0, "total": 0})
    for r in results:
        src = r.get("source", "")
        by_source[src]["total"] += 1
        if r.get("env") == "Normal":
            by_source[src]["normal"] += 1

    # 重复判定：历史 DB + 本批次内同 MD5（终端误复制、同名 copy 等）
    seen_fp_in_batch = set()
    qc_archive = []
    for v_path in video_paths:
        bname = os.path.basename(v_path)
        stat = by_source.get(bname, {"normal": 0, "total": 0})
        total = stat["total"] or 1
        score = (stat["normal"] / total) * 100
        passed = score >= gate
        archive_path = os.path.join(source_archive_dir, bname)
        fp = path_to_md5.get(v_path, "")
        rep = db_tools.get_reproduce_info(db_path, fp) if fp else None
        dup_in_batch = bool(fp and fp in seen_fp_in_batch)
        if dup_in_batch and rep is None:
            rep = {"batch_id": batch_id, "created_at": "本批次内重复"}
        if fp:
            seen_fp_in_batch.add(fp)
        is_dup = rep is not None
        qc_archive.append({
            "filename": bname,
            "archive_path": archive_path,
            "fingerprint": fp,
            "score": score,
            "passed": passed,
            "is_duplicate": is_dup,
            "duplicate_batch_id": rep["batch_id"] if rep else None,
            "duplicate_created_at": rep.get("created_at") if rep else None,
        })
        status = "合格" if passed else "不合格"
        if is_dup:
            logger.info("质量得分: 文件名=%s 指纹=%s 分数=%.2f%% 状态=重复 曾于批次=%s", bname, (fp or "")[:16], score, rep.get("batch_id", ""))
        else:
            logger.info("质量得分: 文件名=%s 指纹=%s 分数=%.2f%% 状态=%s 准入=%.1f%%", bname, (fp or "")[:16], score, status, gate)

    vm_cfg = cfg.get("version_mapping") or {}
    vision_cfg = cfg.get("vision") or {}
    version_info = {
        "algorithm_version": vm_cfg.get("algorithm_version", ""),
        "vision_model_version": (
            vision_detector.get_vision_model_version(cfg)
            or vm_cfg.get("vision_model_version", "")
            or vision_cfg.get("model_path", "")
        ),
    }
    logger.info("版本映射: algorithm_version=%s vision_model_version=%s", version_info["algorithm_version"], version_info["vision_model_version"])
    vision_result = vision_detector.run_vision_scan(cfg, [item["archive_path"] for item in qc_archive])
    vision_skipped = False
    if not vision_result and qc_archive:
        # 模型未加载或未启用时仍生成报告，表格中每文件一行“未执行”，避免报告一片空白
        vision_skipped = True
        vision_result = [
            {"name": item["filename"], "n_frames": 0, "n_detections": 0, "error": "未执行（模型未加载或未启用）"}
            for item in qc_archive
        ]
    version_info_path = os.path.join(qc_dir, "version_info.json")
    try:
        with open(version_info_path, "w", encoding="utf-8") as f:
            json.dump(version_info, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("写入 version_info.json 失败: %s", e)

    if use_dual_gate:
        qualified = [x for x in qc_archive if not x["is_duplicate"] and x["score"] >= dual_high]
        auto_reject = [(x, "quality") for x in qc_archive if not x["is_duplicate"] and x["score"] < dual_low]
        blocked = [x for x in qc_archive if x["is_duplicate"] or (dual_low <= x["score"] < dual_high)]
        print(f"📊 质检结果：批次 {batch_id} 共 {len(qc_archive)} 个文件，双门槛 高>={dual_high}% 自动放行 低<{dual_low}% 自动拦截 中间人工复核")
    else:
        qualified = [x for x in qc_archive if x["passed"] and not x["is_duplicate"]]
        auto_reject = []
        blocked = [x for x in qc_archive if not (x["passed"] and not x["is_duplicate"])]
        print(f"📊 质检结果：批次 {batch_id} 共 {len(qc_archive)} 个文件，准入标准 {gate}%")

    report_path = os.path.join(qc_dir, "quality_report.html")
    industrial_report_path = report_tools.generate_batch_industrial_report(
        qc_archive,
        qualified,
        blocked,
        auto_reject,
        batch_id,
        qc_dir,
        gate,
        dual_high=float(dual_high) if use_dual_gate else None,
        dual_low=float(dual_low) if use_dual_gate else None,
        version_info=version_info,
    )
    logger.info("工业报表已生成: %s", industrial_report_path)
    vision_report_path = report_tools.generate_vision_report(
        vision_result, batch_id, qc_dir, version_info=version_info, vision_skipped=vision_skipped
    )
    logger.info("智能检测报告已生成: %s", vision_report_path)

    email_cfg = cfg.get("email_setting", {})
    if email_cfg:
        body_lines = ["厂长您好，\n\n本批次检测已完成，结果如下（待处理物料清单）：\n\n"]
        for item in qc_archive:
            name = item["filename"]
            if item.get("is_duplicate"):
                body_lines.append(f"  - {name}  [重复] 曾于批次 {item.get('duplicate_batch_id', '')} 处理（{item.get('duplicate_created_at', '')}）")
            elif item["passed"]:
                body_lines.append(f"  - {name}  [合格]")
            else:
                body_lines.append(f"  - {name}  [不合格] 得分: {item['score']:.1f}% / 准入: {gate}%")
        body_lines.append("\n\n请根据控制台逐项复核 (y/n/all/none)，不放行的将移至废片库或冗余库。")
        body_lines.append("\n附件含：1. 重复+质量（工业报表） 2. 智能检测结果（含缩略图）。\n--------------------------------------------------\n本邮件由 Datafactory 自动生成。")
        extra = [p for p in [industrial_report_path, vision_report_path] if p and os.path.isfile(p)]
        notifier.send_mail(
            email_cfg,
            f"【批次质检报告】待处理物料清单 - Batch:{batch_id}",
            "\n".join(body_lines),
            report_path=report_path,
            extra_attachments=extra if extra else None,
        )
    print(f"📍 质量报告: file://{os.path.abspath(report_path)}")
    print(f"📍 工业报表: file://{os.path.abspath(industrial_report_path)}")
    print(f"📍 智能检测报告: file://{os.path.abspath(vision_report_path)}")

    vision_total_detections = sum(p.get("n_detections") or 0 for p in vision_result)
    tiered = cfg.get("production_setting", {}).get("confidence_tiered_output", True)
    path_info = {
        "batch_id": batch_id,
        "qc_dir": qc_dir,
        "source_archive_dir": source_archive_dir,
        "mass_dir": mass_dir,
        "fuel_dir": fuel_dir,
        "human_dir": human_dir,
        "confidence_tiered_output": tiered,
        "report_path": report_path,
        "industrial_report_path": industrial_report_path,
        "vision_report_path": vision_report_path,
        "vision_total_detections": vision_total_detections,
        "gate": gate,
        "version_mapping": version_info,
    }
    return qc_archive, qualified, blocked, auto_reject, path_info
