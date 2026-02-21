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
from engines import fingerprinter, db_tools, notifier, production_tools

logger = logging.getLogger(__name__)


def now_toronto() -> datetime:
    return datetime.now(ZoneInfo("America/Toronto"))


def run_qc(
    cfg: dict,
    video_paths: List[str],
) -> Tuple[List[Dict], List[Dict], List[Dict], Dict[str, Any]]:
    """
    执行质检流程：指纹（重复检测）-> 质量检测（不合格检测）-> 源文件归档 -> 建 qc_archive -> 发邮件。
    返回 (qc_archive, qualified, blocked, path_info)。
    path_info 含 qc_dir, source_archive_dir, mass_dir, report_path 等供后续使用。
    """
    paths = cfg.get("paths", {})
    warehouse = paths.get("data_warehouse", "")
    db_path = paths.get("db_file", "")
    qc_cfg = config_loader.get_quality_thresholds(cfg)
    qc_sample_seconds = qc_cfg.get("qc_sample_seconds", 10)  # 每视频抽检秒数，用于质量判定
    gate = float(qc_cfg.get("pass_rate_gate", 80.0))

    batch_id = now_toronto().strftime("%Y%m%d_%H%M%S")
    qc_dir = os.path.join(warehouse, f"Batch_{batch_id}", "1_QC")
    source_archive_dir = os.path.join(warehouse, f"Batch_{batch_id}", "0_Source_Video")
    mass_dir = os.path.join(warehouse, f"Batch_{batch_id}", "2_Mass_Production")

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

    print(f"📊 质检结果：批次 {batch_id} 共 {len(qc_archive)} 个文件，准入标准 {gate}%")
    qualified = [x for x in qc_archive if x["passed"] and not x["is_duplicate"]]
    blocked = [x for x in qc_archive if not (x["passed"] and not x["is_duplicate"])]
    report_path = os.path.join(qc_dir, "quality_report.html")

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
        body_lines.append("\n\n请根据控制台逐项复核 (y/n/all/none)，不放行的将移至废片库或冗余库。\n--------------------------------------------------\n本邮件由 Datafactory 自动生成。")
        notifier.send_mail(
            email_cfg,
            f"【批次质检报告】待处理物料清单 - Batch:{batch_id}",
            "\n".join(body_lines),
            report_path=report_path,
        )
    print(f"📍 报告: file://{os.path.abspath(report_path)}")

    path_info = {
        "batch_id": batch_id,
        "qc_dir": qc_dir,
        "source_archive_dir": source_archive_dir,
        "mass_dir": mass_dir,
        "report_path": report_path,
        "gate": gate,
    }
    return qc_archive, qualified, blocked, path_info
