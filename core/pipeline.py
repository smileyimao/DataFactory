# core/pipeline.py — 主流程编排：Ingest -> QC -> Review -> Archive
import os
import time
import logging
from typing import List, Optional

from config import config_loader
from core import ingest, qc_engine, reviewer, archiver, pending_queue
from engines import db_tools, labeling_export, metrics, modality_handlers

logger = logging.getLogger(__name__)


def _batch_summary(
    batch_id: str,
    file_count: int,
    total_bytes: int,
    start_time: float,
    t_ingest: float,
    t_qc: float,
    t_review: float,
    t_archive: float,
    db_path: Optional[str] = None,
) -> None:
    """基础指标：批次结束输出摘要（文件数、总大小、耗时、各阶段耗时、吞吐量），并写入 DB batch_metrics。"""
    elapsed = time.time() - start_time
    size_gb = total_bytes / (1024 ** 3)
    d_ingest = t_ingest - start_time
    d_qc = t_qc - t_ingest
    d_review = t_review - t_qc
    d_archive = t_archive - t_review
    throughput_gb_h = size_gb / (elapsed / 3600) if elapsed > 0 else 0.0
    files_per_h = file_count / (elapsed / 3600) if elapsed > 0 else 0.0

    print(f"📊 [批次摘要] Batch {batch_id} | 文件 {file_count} 个，{size_gb:.3f} GB，总耗时 {elapsed:.1f} 秒")
    print(f"   阶段耗时: Ingest {d_ingest:.1f}s | QC {d_qc:.1f}s | Review {d_review:.1f}s | Archive {d_archive:.1f}s")
    print(f"   吞吐量: {throughput_gb_h:.2f} GB/h，{files_per_h:.1f} 文件/h")
    logger.info(
        "批次摘要: batch_id=%s 文件数=%d 总大小_GB=%.3f 耗时_秒=%.1f "
        "ingest=%.1f qc=%.1f review=%.1f archive=%.1f throughput_gb_h=%.2f files_per_h=%.1f",
        batch_id, file_count, size_gb, elapsed, d_ingest, d_qc, d_review, d_archive, throughput_gb_h, files_per_h,
    )

    if db_path:
        db_tools.record_batch_metrics(
            db_path,
            batch_id,
            file_count,
            size_gb,
            elapsed,
            d_ingest,
            d_qc,
            d_review,
            d_archive,
            throughput_gb_h,
            files_per_h,
        )


def _maybe_log_mlflow(
    cfg: dict,
    batch_id: str,
    file_count: int,
    total_bytes: int,
    start_time: float,
    t_ingest: float,
    t_qc: float,
    t_review: float,
    t_archive: float,
    path_info: dict,
) -> None:
    """若 config mlflow.enabled 为 True，则记录批次级实验与指标到 MLflow。"""
    mf = cfg.get("mlflow") or {}
    if not mf.get("enabled"):
        return
    try:
        import mlflow
        tracking_uri = mf.get("tracking_uri")
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(mf.get("experiment_name", "datafactory"))
        elapsed = t_archive - start_time
        size_gb = total_bytes / (1024 ** 3)
        throughput_gb_h = size_gb / (elapsed / 3600) if elapsed > 0 else 0.0
        with mlflow.start_run(run_name=f"batch_{batch_id}"):
            mlflow.log_params({
                "batch_id": batch_id,
                "algorithm_version": (path_info.get("version_mapping") or {}).get("algorithm_version", ""),
                "vision_model_version": (path_info.get("version_mapping") or {}).get("vision_model_version", ""),
                "gate": path_info.get("gate"),
                "refinery_dir": path_info.get("fuel_dir", ""),
                "inspection_dir": path_info.get("human_dir", ""),
                "source_archive_dir": path_info.get("source_archive_dir", ""),
            })
            mlflow.log_metrics({
                "file_count": file_count,
                "size_gb": size_gb,
                "elapsed_sec": elapsed,
                "throughput_gb_per_h": throughput_gb_h,
                "d_ingest_sec": t_ingest - start_time,
                "d_qc_sec": t_qc - t_ingest,
                "d_review_sec": t_review - t_qc,
                "d_archive_sec": t_archive - t_review,
            })
            industrial_report_path = path_info.get("industrial_report_path")
            if industrial_report_path and os.path.isfile(industrial_report_path):
                mlflow.log_artifact(industrial_report_path, artifact_path="industrial_report")
            vision_report_path = path_info.get("vision_report_path")
            if vision_report_path and os.path.isfile(vision_report_path):
                mlflow.log_artifact(vision_report_path, artifact_path="vision_report")
            vision_total_detections = path_info.get("vision_total_detections")
            if vision_total_detections is not None:
                mlflow.log_metric("vision_total_detections", vision_total_detections)
        logger.info("MLflow 已记录批次 run: batch_id=%s", batch_id)
    except Exception as e:
        logger.warning("MLflow 记录失败（已跳过）: %s", e)


def _record_batch_lineage(cfg: dict, path_info: dict) -> None:
    """v3 血缘：写入 batch_lineage 表。"""
    db_path = cfg.get("paths", {}).get("db_url")
    if not db_path:
        return
    batch_id = path_info.get("batch_id", "")
    source_archive_dir = path_info.get("source_archive_dir", "")
    fuel_dir = path_info.get("fuel_dir", "")
    human_dir = path_info.get("human_dir", "")
    if not batch_id or not source_archive_dir:
        return
    batch_base = os.path.dirname(source_archive_dir)
    source_dir = cfg.get("paths", {}).get("raw_video", "")
    vm = path_info.get("version_mapping") or {}
    transform_params = {
        "gate": path_info.get("gate"),
        "algorithm_version": vm.get("algorithm_version", ""),
        "vision_model_version": vm.get("vision_model_version", ""),
    }
    db_tools.record_batch_lineage(
        db_path,
        batch_id,
        batch_base,
        source_dir,
        fuel_dir,
        human_dir,
        transform_params,
    )


def run_smart_factory(
    cfg: Optional[dict] = None,
    video_paths: Optional[List[str]] = None,
    gate_val: Optional[float] = None,
) -> None:
    """
    集中质检复核：获取视频列表 -> QC（指纹+质量检测+建档+邮件）-> 仅对被拦项复核 -> 归档（丢弃+量产+登记）。
    cfg 若传入则使用该配置（测试模式临时环境）；否则从 config_loader 加载。
    video_paths 若传入则只处理该列表（绝对路径）；否则从 config paths.raw_video 扫描。
    gate_val 覆盖 config 中的 pass_rate_gate。
    """
    if cfg is None:
        base = config_loader.get_base_dir()
        config_loader.set_base_dir(base)
        cfg = config_loader.load_config()
    if gate_val is not None:
        cfg.setdefault("production_setting", {})["pass_rate_gate"] = float(gate_val)

    modality = modality_handlers.get_modality(cfg)
    if modality not in ("video", "image"):
        print(f"❌ 当前仅支持 modality=video/image，config 中 modality={modality} 将在 v3 实现（audio/vibration）。")
        logger.warning("modality=%s 未实现，跳过 pipeline", modality)
        return

    videos = ingest.get_video_paths(cfg, video_paths)
    if not videos:
        paths = cfg.get("paths", {})
        raw = paths.get("raw_video", "")
        if video_paths:
            print("❌ 警告：指定的视频路径无效或文件不存在。")
        else:
            print(f"❌ 警告：未发现视频物料：{raw}")
        return

    # Ingest 预检：dedup + 首帧解码，失败项移入 quarantine
    if cfg.get("ingest", {}).get("pre_filter_enabled", False):
        print("\n🔍 [Ingest 预检] dedup + 首帧解码检查...")
        videos, q_stats = ingest.pre_filter(cfg, videos)
        if not videos:
            print("❌ 预检后无有效物料（全部已隔离至 quarantine）")
            return

    start_time = time.time()
    t_ingest = time.time()
    total_bytes = sum(os.path.getsize(p) for p in videos if os.path.isfile(p))

    qc_archive, qualified, blocked, auto_reject, path_info = qc_engine.run_qc(cfg, videos)
    t_qc = time.time()
    to_fuel = list(qualified)
    to_reject = list(auto_reject)
    to_human = []
    review_mode = cfg.get("review", {}).get("mode", "terminal")
    if blocked:
        if review_mode == "dashboard":
            n = pending_queue.add_items(cfg, blocked, path_info)
            if n:
                print(f"📋 [待复核队列] 本批 {n} 项已入队，厂长可打开中控台复核: python -m dashboard.app")
        else:
            timeout = cfg.get("review", {}).get("timeout_seconds", 600)
            added_produce, review_reject = reviewer.review_blocked(blocked, path_info["gate"], timeout_seconds=timeout)
            to_human = list(added_produce)
            to_reject.extend(review_reject)
    t_review = time.time()

    archiver.archive_rejected(cfg, to_reject, path_info["batch_id"])
    archiver.archive_produced(cfg, to_fuel, to_human, path_info)
    metrics.inc("batch_processed_total")
    # v3 血缘：记录 batch_lineage
    _record_batch_lineage(cfg, path_info)
    # 待标池自动更新：本批 inspection 追加到 for_labeling
    updated = labeling_export.auto_update_after_batch(cfg, path_info)
    if updated:
        print(f"📋 [待标池] 已自动更新: {updated}")
    t_archive = time.time()

    _batch_summary(
        path_info["batch_id"],
        len(videos),
        total_bytes,
        start_time,
        t_ingest,
        t_qc,
        t_review,
        t_archive,
        db_path=cfg.get("paths", {}).get("db_url"),
    )
    _maybe_log_mlflow(
        cfg,
        path_info["batch_id"],
        len(videos),
        total_bytes,
        start_time,
        t_ingest,
        t_qc,
        t_review,
        t_archive,
        path_info,
    )
