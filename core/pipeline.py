# core/pipeline.py — 主流程编排：Ingest -> QC -> Review -> Archive
import os
import time
import logging
from typing import List, Optional

from config import config_loader
from core import ingest, qc_engine, reviewer, archiver
from engines import db_tools

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

    if db_path and os.path.isfile(os.path.abspath(db_path)):
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


def run_smart_factory(
    video_paths: Optional[List[str]] = None,
    gate_val: Optional[float] = None,
) -> None:
    """
    集中质检复核：获取视频列表 -> QC（指纹+质量检测+建档+邮件）-> 仅对被拦项复核 -> 归档（丢弃+量产+登记）。
    video_paths 若传入则只处理该列表（绝对路径）；否则从 config paths.raw_video 扫描。
    gate_val 覆盖 config 中的 pass_rate_gate。
    """
    base = config_loader.get_base_dir()
    config_loader.set_base_dir(base)
    cfg = config_loader.load_config()
    if gate_val is not None:
        cfg.setdefault("production_setting", {})["pass_rate_gate"] = float(gate_val)

    videos = ingest.get_video_paths(cfg, video_paths)
    if not videos:
        paths = cfg.get("paths", {})
        raw = paths.get("raw_video", "")
        if video_paths:
            print("❌ 警告：指定的视频路径无效或文件不存在。")
        else:
            print(f"❌ 警告：未发现视频物料：{raw}")
        return

    gate = cfg.get("production_setting", {}).get("pass_rate_gate", 80.0)
    print(f"🚀 [指挥部] 准入标准 {gate}% | 重复检测 + 不合格检测")

    start_time = time.time()
    t_ingest = time.time()
    total_bytes = sum(os.path.getsize(p) for p in videos if os.path.isfile(p))

    qc_archive, qualified, blocked, path_info = qc_engine.run_qc(cfg, videos)
    t_qc = time.time()
    to_produce = list(qualified)
    to_reject = []
    if blocked:
        timeout = cfg.get("review", {}).get("timeout_seconds", 600)
        added_produce, to_reject = reviewer.review_blocked(blocked, path_info["gate"], timeout_seconds=timeout)
        to_produce.extend(added_produce)
    t_review = time.time()

    archiver.archive_rejected(cfg, to_reject, path_info["batch_id"])
    archiver.archive_produced(cfg, to_produce, path_info)
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
        db_path=cfg.get("paths", {}).get("db_file"),
    )
