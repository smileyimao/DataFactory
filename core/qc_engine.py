# core/qc_engine.py — 质检编排：指纹、质量检测、建档、发邮件，决策合格/不合格/重复（无试产，进厂即质检）
import os
import json
import shutil
import tempfile
import logging
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Tuple

from config import config_loader
from core import time_utils
from engines import fingerprinter, db_tools, notifier, production_tools, vision_detector, report_tools, retry_utils

logger = logging.getLogger(__name__)


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
    db_path = paths.get("db_url", "")
    qc_cfg = config_loader.get_quality_thresholds(cfg)
    qc_sample_seconds = qc_cfg.get("qc_sample_seconds", 10)  # 每视频抽检秒数，用于质量判定
    gate = float(qc_cfg.get("pass_rate_gate", 80.0))
    dual_high = qc_cfg.get("dual_gate_high")
    dual_low = qc_cfg.get("dual_gate_low")
    use_dual_gate = dual_high is not None and dual_low is not None
    if use_dual_gate:
        dual_high = float(dual_high)
        dual_low = float(dual_low)

    batch_id = time_utils.now_toronto(cfg).strftime("%Y%m%d_%H%M%S")
    batch_prefix = config_loader.get_batch_prefix(cfg)
    batch_base = os.path.join(warehouse, f"{batch_prefix}{batch_id}")
    bp = config_loader.get_batch_paths(cfg, batch_base)
    report_dir = bp["qc_dir"]
    source_archive_dir = bp["source_archive_dir"]
    mass_dir = bp["mass_dir"]
    fuel_dir = bp["fuel_dir"]
    human_dir = bp["human_dir"]
    os.makedirs(report_dir, exist_ok=True)

    path_to_md5: Dict[str, str] = {}
    for v in video_paths:
        fp = fingerprinter.compute(v) or ""
        path_to_md5[v] = fp
        logger.info("指纹采集结果: 文件=%s 指纹=%s", os.path.basename(v), (fp[:16] + "...") if len(fp) > 16 else fp)

    # 先判重：重复文件不参与抽检，节省计算
    seen_fp_in_batch: set = set()
    paths_need_sample: List[str] = []
    for v_path in video_paths:
        fp = path_to_md5.get(v_path, "")
        rep = db_tools.get_reproduce_info(db_path, fp) if fp else None
        dup_in_batch = bool(fp and fp in seen_fp_in_batch)
        if rep is not None or dup_in_batch:
            logger.info("跳过抽检（重复）: %s", os.path.basename(v_path))
            continue
        paths_need_sample.append(v_path)
        if fp:
            seen_fp_in_batch.add(fp)

    print(f"\n🚀 [指挥部] 质量准入标准 {gate}%")

    # 抽检用临时目录，P2：TemporaryDirectory 上下文管理器，异常时自动清理
    results: List[Dict[str, Any]] = []
    vision_model_load_failed = False  # 若配置开启但模型未加载成功，用于邮件标红提醒
    with tempfile.TemporaryDirectory(prefix="datafactory_qc_") as temp_qc:
        try:
            print(f"\n🚀 [质检] 批次: {batch_id} | 质量检测（抽检 {qc_sample_seconds}s/视频）")
            # 质量要求清单（与 quality_tools 判定一致）
            print("  质量要求清单:")
            print(f"    亮度 brightness: {qc_cfg.get('min_brightness', 55)} ~ {qc_cfg.get('max_brightness', 225)} （低于下限→太暗 Too Dark，高于上限→过曝 Harsh Light）")
            print(f"    模糊 blur: 不低于 {qc_cfg.get('min_blur_score', 20)} （低于→Blurry）")
            print(f"    抖动 jitter: 不高于 {qc_cfg.get('max_jitter', 35)} （高于→High Jitter）")
            print(f"    对比度 contrast: {qc_cfg.get('min_contrast', 15)} ~ {qc_cfg.get('max_contrast', 100)} （低于→Low Contrast，高于→High Contrast）")
            # 本批次视觉检测：是否开启、模型、版本（打印到控制台并写入运行日志）
            vision_cfg = cfg.get("vision") or {}
            vision_enabled = vision_detector.is_enabled(cfg)
            vision_model_path = (vision_cfg.get("model_path") or "").strip() or "未配置"
            vision_model = vision_detector.get_model(cfg) if vision_enabled else None
            vision_model_load_failed = vision_enabled and (vision_model is None)
            vision_version = vision_detector.get_vision_model_version(cfg) or (cfg.get("version_mapping") or {}).get("vision_model_version") or "—"
            vision_status = "已开启" if vision_enabled else "未开启"
            print(f"  本批次视觉检测: {vision_status} | 模型: {vision_model_path} | 版本: {vision_version}")
            if vision_model_load_failed:
                load_reason = (vision_detector.get_vision_load_error() or "未知原因").strip()
                print(f"  [运行日志] ⚠️ 视觉模型未成功加载，本批次未进行智能检测。原因: {load_reason}")
                logger.warning("批次 %s 视觉模型未成功加载 (model_path=%s)，原因: %s，本批次未进行智能检测", batch_id, vision_model_path, load_reason)
            logger.info(
                "批次 %s 视觉检测 enabled=%s model_path=%s version=%s load_ok=%s",
                batch_id, vision_enabled, vision_model_path, vision_version, not vision_model_load_failed,
            )
            if paths_need_sample:
                production_tools.run_production(
                    paths_need_sample, temp_qc, batch_id, cfg, limit_seconds=qc_sample_seconds, reports_archive_dir=report_dir
                )
            else:
                with open(os.path.join(temp_qc, "manifest.json"), "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False)
                print("  （本批次均为重复，已跳过抽检）")

            os.makedirs(source_archive_dir, exist_ok=True)
            retry_cfg = cfg.get("retry", {})
            max_attempts = retry_cfg.get("max_attempts", 3)
            backoff = retry_cfg.get("backoff_seconds", 1.0)
            from tqdm import tqdm
            for v_path in tqdm(video_paths, desc="归档 source", unit="文件"):
                dest = os.path.join(source_archive_dir, os.path.basename(v_path))
                logger.info("Moving [%s] to [%s] due to [Batch archive source]", os.path.basename(v_path), os.path.abspath(dest))
                if not retry_utils.safe_move_with_retry(v_path, dest, max_attempts, backoff):
                    print(f"⚠️ [归档失败]: {v_path}")

            manifest_path = os.path.join(temp_qc, "manifest.json")
            with open(manifest_path, "r", encoding="utf-8") as f:
                results.extend(json.load(f))
        except Exception as e:
            logger.exception("抽检/读取 manifest 异常: %s", e)

    if not results:
        results = []
    by_source = defaultdict(lambda: {"normal": 0, "total": 0})
    by_source_raw = defaultdict(lambda: {"br": [], "bl": [], "jitter": [], "std_dev": []})
    for r in results:
        src = r.get("source", "")
        by_source[src]["total"] += 1
        if r.get("env") == "Normal":
            by_source[src]["normal"] += 1
        for k in ("br", "bl", "jitter", "std_dev"):
            v = r.get(k)
            if v is not None:
                by_source_raw[src][k].append(float(v))

    # 规则分项统计（亮度/模糊/抖动/对比度），用于复核时标红展示
    min_br_th = qc_cfg.get("min_brightness", 55)
    max_br_th = qc_cfg.get("max_brightness", 225)
    min_bl_th = qc_cfg.get("min_blur_score", 20)
    max_jitter_th = qc_cfg.get("max_jitter", 35)
    min_contrast_th = qc_cfg.get("min_contrast", 15)
    max_contrast_th = qc_cfg.get("max_contrast", 100)

    def _build_rule_stats(src: str) -> dict:
        raw = by_source_raw.get(src, {})
        stats = {}
        brs = raw.get("br") or []
        if brs:
            mn, mx = min(brs), max(brs)
            fail = []
            if mn < min_br_th:
                fail.append(f"太暗 {mn:.1f}<{min_br_th}")
            if mx > max_br_th:
                fail.append(f"过曝 {mx:.1f}>{max_br_th}")
            stats["brightness"] = {"min": mn, "max": mx, "pass": not fail, "fail_reason": "; ".join(fail) if fail else None}
        bls = raw.get("bl") or []
        if bls:
            mn = min(bls)
            stats["blur"] = {"min": mn, "threshold": min_bl_th, "pass": mn >= min_bl_th, "fail_reason": f"模糊 {mn:.1f}<{min_bl_th}" if mn < min_bl_th else None}
        jitters = raw.get("jitter") or []
        if jitters:
            mx = max(jitters)
            stats["jitter"] = {"max": mx, "threshold": max_jitter_th, "pass": mx <= max_jitter_th, "fail_reason": f"抖动 {mx:.1f}>{max_jitter_th}" if mx > max_jitter_th else None}
        stds = raw.get("std_dev") or []
        if stds:
            mn, mx = min(stds), max(stds)
            fail = []
            if mn < min_contrast_th:
                fail.append(f"低对比 {mn:.1f}<{min_contrast_th}")
            if mx > max_contrast_th:
                fail.append(f"高对比 {mx:.1f}>{max_contrast_th}")
            stats["contrast"] = {"min": mn, "max": mx, "pass": not fail, "fail_reason": "; ".join(fail) if fail else None}
        return stats

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
        rule_stats = _build_rule_stats(bname) if not is_dup else {}
        qc_archive.append({
            "filename": bname,
            "archive_path": archive_path,
            "fingerprint": fp,
            "score": score,
            "passed": passed,
            "is_duplicate": is_dup,
            "duplicate_batch_id": rep["batch_id"] if rep else None,
            "duplicate_created_at": rep.get("created_at") if rep else None,
            "rule_stats": rule_stats,
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
    vision_result = vision_detector.run_vision_scan(
        cfg, [item["archive_path"] for item in qc_archive], return_detections=True
    )
    vision_skipped = False
    if not vision_result and qc_archive:
        # 模型未加载或未启用时仍生成报告，表格中每文件一行“未执行”，避免报告一片空白
        vision_skipped = True
        vision_result = [
            {"name": item["filename"], "n_frames": 0, "n_detections": 0, "error": "未执行（模型未加载或未启用）"}
            for item in qc_archive
        ]
    version_info_path = os.path.join(report_dir, "version_info.json")
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

    report_path = os.path.join(report_dir, "quality_report.html")
    industrial_report_path = report_tools.generate_batch_industrial_report(
        qc_archive,
        qualified,
        blocked,
        auto_reject,
        batch_id,
        report_dir,
        gate,
        dual_high=float(dual_high) if use_dual_gate else None,
        dual_low=float(dual_low) if use_dual_gate else None,
        version_info=version_info,
    )
    logger.info("工业报表已生成: %s", industrial_report_path)
    vision_report_path = report_tools.generate_vision_report(
        vision_result, batch_id, report_dir, version_info=version_info, vision_skipped=vision_skipped
    )
    logger.info("智能检测报告已生成: %s", vision_report_path)

    email_cfg = cfg.get("email_setting", {})
    if email_cfg:
        body_lines = ["厂长您好，\n\n本批次检测已完成"]
        if vision_model_load_failed:
            load_reason = (vision_detector.get_vision_load_error() or "未知原因").strip()
            body_lines.append(f"\n\n【重要】视觉模型未成功加载，本批次未进行智能检测。原因: {load_reason}\n请检查 ultralytics 安装与 config vision 配置。")
        body_lines.append("，结果如下（待处理物料清单）：\n\n")
        for item in qc_archive:
            name = item["filename"]
            if item.get("is_duplicate"):
                body_lines.append(f"  - {name}  [重复] 曾于批次 {item.get('duplicate_batch_id', '')} 处理（{item.get('duplicate_created_at', '')}）")
            elif item["passed"]:
                body_lines.append(f"  - {name}  [合格]")
            else:
                body_lines.append(f"  - {name}  [不合格] 得分: {item['score']:.1f}% / 准入: {gate}%")
        review_mode = cfg.get("review", {}).get("mode", "terminal")
        if review_mode == "dashboard":
            body_lines.append("\n\n请打开厂长中控台复核: python -m dashboard.app ，不放行的将移至废片库或冗余库。")
        else:
            body_lines.append("\n\n请根据控制台逐项复核 (y/n/all/none)，不放行的将移至废片库或冗余库。")
        body_lines.append("\n附件含：1. 重复+质量（工业报表） 2. 智能检测结果（含缩略图）。\n--------------------------------------------------\n本邮件由 Datafactory 自动生成。")
        extra = [p for p in [industrial_report_path, vision_report_path] if p and os.path.isfile(p)]
        sent = notifier.send_mail(
            email_cfg,
            f"【批次质检报告】待处理物料清单 - Batch:{batch_id}",
            "\n".join(body_lines),
            report_path=report_path,
            extra_attachments=extra if extra else None,
        )
        if not sent:
            print("⚠️ [邮件] 未发送成功，请检查 .env 中 EMAIL_PASSWORD 及 smtp 配置")
    print(f"📍 质量报告: file://{os.path.abspath(report_path)}")
    print(f"📍 工业报表: file://{os.path.abspath(industrial_report_path)}")
    print(f"📍 智能检测报告: file://{os.path.abspath(vision_report_path)}")

    vision_total_detections = sum(p.get("n_detections") or 0 for p in vision_result)
    tiered = cfg.get("production_setting", {}).get("confidence_tiered_output", True)
    qc_detections_by_video = {
        e.get("name", ""): e.get("detections_by_frame") or {}
        for e in vision_result
        if e.get("name")
    }
    path_info = {
        "batch_id": batch_id,
        "qc_dir": report_dir,
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
        "qc_detections_by_video": qc_detections_by_video,
    }
    return qc_archive, qualified, blocked, auto_reject, path_info
