# core/qc_engine.py — 质检编排：指纹、质量检测、建档、发邮件，决策合格/不合格/重复（无试产，进厂即质检）
import os
import json
import shutil
import tempfile
import logging
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

from config import config_loader
from utils import time_utils, file_tools
from utils import fingerprinter, notifier, report_tools, retry_utils
from utils.usage_tracker import track
from db import db_tools
from vision import production_tools, vision_detector
from vision.foundation_models import load_clip_embedder

logger = logging.getLogger(__name__)


# ─────────────────────────── 私有子函数 ───────────────────────────────────────

def _collect_fingerprints(video_paths: List[str]) -> Dict[str, str]:
    """对每个文件计算指纹，返回 {path: md5}。"""
    path_to_md5: Dict[str, str] = {}
    for v in video_paths:
        fp = fingerprinter.compute(v) or ""
        path_to_md5[v] = fp
        logger.info("指纹采集结果: 文件=%s 指纹=%s", os.path.basename(v), (fp[:16] + "...") if len(fp) > 16 else fp)
    return path_to_md5


def _filter_duplicates(video_paths: List[str], path_to_md5: Dict[str, str], db_path: str) -> List[str]:
    """返回需要抽检的非重复文件列表（过滤历史 DB 重复 + 批次内重复）。"""
    track("qc_hash_dedup")
    seen_fp: set = set()
    paths_need_sample: List[str] = []
    for v_path in video_paths:
        fp = path_to_md5.get(v_path, "")
        rep = db_tools.get_reproduce_info(db_path, fp) if fp else None
        if rep is not None or (fp and fp in seen_fp):
            logger.info("跳过抽检（重复）: %s", os.path.basename(v_path))
            continue
        paths_need_sample.append(v_path)
        if fp:
            seen_fp.add(fp)
    return paths_need_sample


def _extract_first_frame_tmp(video_path: str) -> Optional[str]:
    """提取视频中间帧为临时文件（供 CLIP 分类用）。失败返回 None。"""
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        import tempfile as _tf
        fd, tmp_path = _tf.mkstemp(suffix=".jpg")
        os.close(fd)
        cv2.imwrite(tmp_path, frame)
        return tmp_path
    except Exception as e:
        logger.debug("提取帧失败: %s", e)
        return None


def _run_sampling(
    paths_need_sample: List[str],
    video_paths: List[str],
    cfg: dict,
    batch_id: str,
    source_archive_dir: str,
    report_dir: str,
    qc_sample_seconds: int,
) -> List[Dict[str, Any]]:
    """抽检 + 归档 source，返回 manifest results 列表。"""
    retry_cfg = cfg.get("retry", {})
    max_attempts = retry_cfg.get("max_attempts", 3)
    backoff = retry_cfg.get("backoff_seconds", 1.0)
    results: List[Dict[str, Any]] = []

    # CLIP 场景分类初始化
    fm_cfg = cfg.get("foundation_models", {})
    scene_classify = fm_cfg.get("clip_enabled") and fm_cfg.get("clip_scene_classify_enabled")
    clip_embedder = load_clip_embedder(cfg) if scene_classify else None
    scene_thresholds = fm_cfg.get("scene_thresholds", {})

    with tempfile.TemporaryDirectory(prefix="datafactory_qc_") as temp_qc:
        try:
            if not paths_need_sample:
                file_tools.atomic_write_json(os.path.join(temp_qc, "manifest.json"), [])
                logger.info("本批次均为重复，已跳过抽检")
            elif clip_embedder:
                # 逐视频运行：每个视频按场景分类覆写质量阈值
                merged: List[Dict[str, Any]] = []
                for video_path in paths_need_sample:
                    cfg_video = cfg
                    tmp_frame = None
                    try:
                        classify_path = video_path
                        ext = os.path.splitext(video_path)[1].lower()
                        if ext not in {".jpg", ".jpeg", ".png", ".bmp"}:
                            tmp_frame = _extract_first_frame_tmp(video_path)
                            if tmp_frame:
                                classify_path = tmp_frame
                        scene = clip_embedder.classify_scene(classify_path)
                        track("clip_scene_classify")
                        logger.info("场景分类: %s → %s", os.path.basename(video_path), scene)
                        override = scene_thresholds.get(scene, {})
                        if override:
                            cfg_video = dict(cfg)
                            cfg_video["quality_thresholds"] = {
                                **cfg.get("quality_thresholds", {}), **override
                            }
                    except Exception as e:
                        logger.warning("CLIP 场景分类异常: %s", e)
                    finally:
                        if tmp_frame and os.path.isfile(tmp_frame):
                            os.unlink(tmp_frame)

                    with tempfile.TemporaryDirectory(prefix="datafactory_v_") as temp_v:
                        try:
                            production_tools.run_production(
                                [video_path], temp_v, batch_id, cfg_video,
                                limit_seconds=qc_sample_seconds, reports_archive_dir=report_dir,
                                tqdm_desc="QC sampling",
                            )
                            mf = os.path.join(temp_v, "manifest.json")
                            if os.path.isfile(mf):
                                with open(mf, "r", encoding="utf-8") as f:
                                    merged.extend(json.load(f))
                        except Exception as e:
                            logger.exception("抽检异常 [%s]: %s", os.path.basename(video_path), e)
                file_tools.atomic_write_json(os.path.join(temp_qc, "manifest.json"), merged)
            else:
                production_tools.run_production(
                    paths_need_sample, temp_qc, batch_id, cfg,
                    limit_seconds=qc_sample_seconds, reports_archive_dir=report_dir,
                    tqdm_desc="QC sampling",
                )

            print("            Step 2/3  Moving source files to archive ...", flush=True)
            os.makedirs(source_archive_dir, exist_ok=True)
            seen = set()
            unique_paths = []
            for p in video_paths:
                ap = os.path.abspath(p)
                if ap not in seen:
                    seen.add(ap)
                    unique_paths.append(p)
            try:
                from tqdm import tqdm
                iter_paths = tqdm(unique_paths, desc="Archive source", unit="file")
            except ImportError:
                iter_paths = unique_paths
            for v_path in iter_paths:
                dest = os.path.join(source_archive_dir, os.path.basename(v_path))
                if not os.path.isfile(v_path):
                    if os.path.isfile(dest):
                        logger.info("已归档（跳过重复项）: %s", os.path.basename(v_path))
                    else:
                        logger.warning("源文件不存在，跳过: %s", v_path)
                    continue
                logger.info("Moving [%s] to [%s] due to [Batch archive source]", os.path.basename(v_path), os.path.abspath(dest))
                if not retry_utils.safe_move_with_retry(v_path, dest, max_attempts, backoff):
                    logger.warning("归档失败: %s", v_path)

            manifest_path = os.path.join(temp_qc, "manifest.json")
            with open(manifest_path, "r", encoding="utf-8") as f:
                raw_items = json.load(f)
            _MANIFEST_REQUIRED = {"filename", "source"}
            for item in raw_items:
                missing = _MANIFEST_REQUIRED - set(item.keys())
                if missing:
                    logger.warning("manifest 条目缺少必需字段 %s，跳过: %s", missing, item.get("filename", "?"))
                    continue
                results.append(item)
        except Exception as e:
            logger.exception("抽检/读取 manifest 异常: %s", e)

    return results


def _build_rule_stats(src: str, by_source_raw: dict, qc_cfg: dict) -> dict:
    """从原始帧数值计算规则分项统计（亮度/模糊/抖动/对比度）。"""
    min_br_th = qc_cfg.get("min_brightness", 55)
    max_br_th = qc_cfg.get("max_brightness", 225)
    min_bl_th = qc_cfg.get("min_blur_score", 20)
    max_jitter_th = qc_cfg.get("max_jitter", 35)
    min_contrast_th = qc_cfg.get("min_contrast", 15)
    max_contrast_th = qc_cfg.get("max_contrast", 100)

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
        track("qc_overexpose")
        stats["brightness"] = {"min": mn, "max": mx, "pass": not fail, "fail_reason": "; ".join(fail) if fail else None}
    bls = raw.get("bl") or []
    if bls:
        mn = min(bls)
        track("qc_blur")
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


def _build_qc_archive(
    video_paths: List[str],
    path_to_md5: Dict[str, str],
    results: List[Dict[str, Any]],
    source_archive_dir: str,
    db_path: str,
    gate: float,
    batch_id: str,
    qc_cfg: dict,
) -> List[Dict[str, Any]]:
    """汇总每个视频的质检结果，返回 qc_archive 列表。"""
    by_source: Dict[str, Dict] = defaultdict(lambda: {"normal": 0, "total": 0})
    by_source_raw: Dict[str, Dict] = defaultdict(lambda: {"br": [], "bl": [], "jitter": [], "std_dev": []})
    for r in results:
        src = r.get("source", "")
        by_source[src]["total"] += 1
        if r.get("env") == "Normal":
            by_source[src]["normal"] += 1
        for k in ("br", "bl", "jitter", "std_dev"):
            v = r.get(k)
            if v is not None:
                by_source_raw[src][k].append(float(v))

    seen_fp_in_batch: set = set()
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
        rule_stats = _build_rule_stats(bname, by_source_raw, qc_cfg) if not is_dup else {}
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
    return qc_archive


def _gate_split(
    qc_archive: List[Dict[str, Any]],
    gate: float,
    dual_high: Optional[float],
    dual_low: Optional[float],
    batch_id: str,
) -> Tuple[List, List, List]:
    """按单/双门槛将 qc_archive 分为 qualified, blocked, auto_reject。"""
    use_dual = dual_high is not None and dual_low is not None
    if use_dual:
        qualified = [x for x in qc_archive if not x["is_duplicate"] and x["score"] >= dual_high]
        auto_reject = [(x, "quality") for x in qc_archive if not x["is_duplicate"] and x["score"] < dual_low]
        blocked = [x for x in qc_archive if x["is_duplicate"] or (dual_low <= x["score"] < dual_high)]
        logger.info("质检结果 批次=%s 文件数=%d 双门槛 高>=%s%% 自动放行 低<%s%% 自动拦截 中间人工复核", batch_id, len(qc_archive), dual_high, dual_low)
    else:
        qualified = [x for x in qc_archive if x["passed"] and not x["is_duplicate"]]
        auto_reject = []
        blocked = [x for x in qc_archive if not (x["passed"] and not x["is_duplicate"])]
        logger.info("质检结果 批次=%s 文件数=%d 准入标准 %s%%", batch_id, len(qc_archive), gate)
    return qualified, blocked, auto_reject


def _generate_reports(
    cfg: dict,
    qc_archive: List[Dict[str, Any]],
    qualified: List,
    blocked: List,
    auto_reject: List,
    batch_id: str,
    report_dir: str,
    gate: float,
    dual_high: Optional[float],
    dual_low: Optional[float],
    version_info: dict,
    vision_result: list,
    vision_skipped: bool,
) -> Tuple[str, str, str]:
    """生成工业报表 + 视觉检测报告，返回 (report_path, industrial_report_path, vision_report_path)。"""
    report_path = os.path.join(report_dir, "quality_report.html")
    industrial_report_path = report_tools.generate_batch_industrial_report(
        qc_archive, qualified, blocked, auto_reject,
        batch_id, report_dir, gate,
        dual_high=float(dual_high) if dual_high is not None else None,
        dual_low=float(dual_low) if dual_low is not None else None,
        version_info=version_info,
    )
    logger.info("工业报表已生成: %s", industrial_report_path)
    vision_report_path = report_tools.generate_vision_report(
        vision_result, batch_id, report_dir, version_info=version_info, vision_skipped=vision_skipped,
    )
    logger.info("智能检测报告已生成: %s", vision_report_path)
    logger.info("质量报告: file://%s", os.path.abspath(report_path))
    logger.info("工业报表: file://%s", os.path.abspath(industrial_report_path))
    logger.info("智能检测报告: file://%s", os.path.abspath(vision_report_path))
    return report_path, industrial_report_path, vision_report_path


def _send_qc_email(
    cfg: dict,
    qc_archive: List[Dict[str, Any]],
    batch_id: str,
    gate: float,
    report_path: str,
    industrial_report_path: str,
    vision_report_path: str,
    vision_model_load_failed: bool,
) -> None:
    """发送批次质检报告邮件。"""
    email_cfg = cfg.get("email_setting", {})
    if not email_cfg:
        return
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
        logger.warning("邮件未发送成功，请检查 .env 中 EMAIL_PASSWORD 及 smtp 配置")


# ─────────────────────────── 公开入口 ─────────────────────────────────────────

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
    qc_sample_seconds = qc_cfg.get("qc_sample_seconds", 10)
    gate = float(qc_cfg.get("pass_rate_gate", 80.0))
    dual_high = qc_cfg.get("dual_gate_high")
    dual_low = qc_cfg.get("dual_gate_low")
    if dual_high is not None and dual_low is not None:
        dual_high, dual_low = float(dual_high), float(dual_low)
    else:
        dual_high = dual_low = None

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

    # ── 1. 指纹采集 & 去重过滤 ──────────────────────────────────────────────
    path_to_md5 = _collect_fingerprints(video_paths)
    paths_need_sample = _filter_duplicates(video_paths, path_to_md5, db_path)

    logger.info("指挥部 质量准入标准 %s%%", gate)

    # ── 2. 视觉模型预检 ──────────────────────────────────────────────────────
    vision_cfg = cfg.get("vision") or {}
    vision_enabled = vision_detector.is_enabled(cfg)
    vision_model_path = (vision_cfg.get("model_path") or "").strip() or "未配置"
    vision_model = vision_detector.get_model(cfg) if vision_enabled else None
    vision_model_load_failed = vision_enabled and (vision_model is None)
    vision_version = vision_detector.get_vision_model_version(cfg) or (cfg.get("version_mapping") or {}).get("vision_model_version") or "—"
    vision_status = "已开启" if vision_enabled else "未开启"
    logger.info("质检 批次=%s 抽检=%ss/视频 质量要求 brightness=%s~%s blur>=%s jitter<=%s contrast=%s~%s 视觉=%s 模型=%s 版本=%s",
                batch_id, qc_sample_seconds,
                qc_cfg.get("min_brightness", 55), qc_cfg.get("max_brightness", 225),
                qc_cfg.get("min_blur_score", 20), qc_cfg.get("max_jitter", 35),
                qc_cfg.get("min_contrast", 15), qc_cfg.get("max_contrast", 100),
                vision_status, vision_model_path, vision_version)
    if vision_model_load_failed:
        load_reason = (vision_detector.get_vision_load_error() or "未知原因").strip()
        logger.warning("批次 %s 视觉模型未加载 model_path=%s 原因=%s", batch_id, vision_model_path, load_reason)
    logger.info("批次 %s 视觉检测 enabled=%s model_path=%s version=%s load_ok=%s",
                batch_id, vision_enabled, vision_model_path, vision_version, not vision_model_load_failed)

    # ── 3. 抽检 + source 归档 ────────────────────────────────────────────────
    results = _run_sampling(paths_need_sample, video_paths, cfg, batch_id, source_archive_dir, report_dir, qc_sample_seconds)

    # ── 4. 汇总 qc_archive ───────────────────────────────────────────────────
    qc_archive = _build_qc_archive(video_paths, path_to_md5, results, source_archive_dir, db_path, gate, batch_id, qc_cfg)

    # ── 5. 版本映射 & 视觉扫描 ───────────────────────────────────────────────
    vm_cfg = cfg.get("version_mapping") or {}
    version_info = {
        "algorithm_version": vm_cfg.get("algorithm_version", ""),
        "vision_model_version": (
            vision_detector.get_vision_model_version(cfg)
            or vm_cfg.get("vision_model_version", "")
            or vision_cfg.get("model_path", "")
        ),
    }
    logger.info("版本映射: algorithm_version=%s vision_model_version=%s",
                version_info["algorithm_version"], version_info["vision_model_version"])
    print("            Step 3/3  YOLO object detection scan ...", flush=True)
    vision_result = vision_detector.run_vision_scan(
        cfg, [item["archive_path"] for item in qc_archive], return_detections=True,
    )
    vision_skipped = False
    if not vision_result and qc_archive:
        vision_skipped = True
        vision_result = [
            {"name": item["filename"], "n_frames": 0, "n_detections": 0, "error": "未执行（模型未加载或未启用）"}
            for item in qc_archive
        ]
    version_info_path = os.path.join(report_dir, "version_info.json")
    try:
        file_tools.atomic_write_json(version_info_path, version_info)
    except OSError as e:
        logger.warning("写入 version_info.json 失败: %s", e)

    # ── 6. 门槛分流 ──────────────────────────────────────────────────────────
    qualified, blocked, auto_reject = _gate_split(qc_archive, gate, dual_high, dual_low, batch_id)

    # ── 7. 报表生成 ──────────────────────────────────────────────────────────
    report_path, industrial_report_path, vision_report_path = _generate_reports(
        cfg, qc_archive, qualified, blocked, auto_reject,
        batch_id, report_dir, gate, dual_high, dual_low,
        version_info, vision_result, vision_skipped,
    )

    # ── 8. 发邮件 ────────────────────────────────────────────────────────────
    _send_qc_email(cfg, qc_archive, batch_id, gate, report_path, industrial_report_path, vision_report_path, vision_model_load_failed)

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
