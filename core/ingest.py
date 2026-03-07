# core/ingest.py — 入场：解析或扫描得到待处理视频路径列表
# Ingest 预检：dedup + 首帧解码检查，失败项移入 quarantine
import os
import logging
from typing import List, Optional, Tuple

from utils import file_tools, fingerprinter, retry_utils
from utils.usage_tracker import track
from db import db_tools
from vision import modality_handlers
from vision.foundation_models import load_clip_embedder
from config import config_loader

logger = logging.getLogger(__name__)


def get_video_paths(
    cfg: dict,
    video_paths: Optional[List[str]] = None,
) -> List[str]:
    """
    若 video_paths 已传入则校验并返回绝对路径列表；
    否则从 paths.raw_video 扫描：按 image_mode 或自动检测选择图片/视频通路。
    """
    paths = cfg.get("paths", {})
    raw_dir = paths.get("raw_video", "")
    if video_paths is not None:
        out = [os.path.abspath(p) for p in video_paths if os.path.isfile(p)]
        return out
    mode = config_loader.get_content_mode(cfg)
    if mode == "image":
        logger.info("Ingest 通路: image（自动检测或显式配置）")
    elif mode == "both":
        logger.info("Ingest 通路: both（图片+视频混合）")
    else:
        logger.info("Ingest 通路: video（自动检测或显式配置）")
    ingest_cfg = cfg.get("ingest", {})
    img_exts = tuple(ingest_cfg.get("image_extensions", [".jpg", ".jpeg", ".png"]))
    vid_exts = tuple(ingest_cfg.get("video_extensions", [".mp4", ".mov", ".avi", ".mkv"]))
    if mode == "image":
        return file_tools.list_image_paths_recursive(raw_dir, img_exts)
    if mode == "both":
        return file_tools.list_media_paths_recursive(raw_dir, img_exts, vid_exts)
    return file_tools.list_video_paths_recursive(raw_dir, vid_exts)


def _move_to_quarantine(src: str, subdir: str, cfg: dict) -> bool:
    """将文件移到 quarantine/subdir/，使用 retry_utils。成功返回 True。"""
    paths = cfg.get("paths", {})
    base = paths.get("quarantine", "")
    if not base:
        return False
    dest_dir = os.path.join(base, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(src))
    if os.path.exists(dest):
        base_name, ext = os.path.splitext(os.path.basename(src))
        dest = os.path.join(dest_dir, f"{base_name}_dup{ext}")
    retry_cfg = cfg.get("retry", {})
    return retry_utils.safe_move_with_retry(
        src, dest,
        max_attempts=retry_cfg.get("max_attempts", 3),
        backoff_seconds=retry_cfg.get("backoff_seconds", 1.0),
    )


def pre_filter(cfg: dict, video_paths: List[str]) -> Tuple[List[str], dict]:
    """
    Ingest 预检：dedup + 首帧解码检查。失败项移入 quarantine，并记录日志。
    返回 (通过预检的路径列表, 统计 {"quarantine_duplicate": N, "quarantine_decode_failed": N})。
    """
    track("ingest_video")
    ingest_cfg = cfg.get("ingest", {})
    if not ingest_cfg.get("pre_filter_enabled", False):
        return video_paths, {"quarantine_duplicate": 0, "quarantine_decode_failed": 0}

    dedup = ingest_cfg.get("dedup_at_ingest", True)
    decode_check = ingest_cfg.get("decode_check_at_ingest", True)
    db_path = cfg.get("paths", {}).get("db_url", "")

    # CLIP 语义去重初始化
    fm_cfg = cfg.get("foundation_models", {})
    semantic_dedup_clip = fm_cfg.get("clip_enabled") and fm_cfg.get("clip_semantic_dedup_enabled")
    clip_embedder = load_clip_embedder(cfg) if semantic_dedup_clip else None
    seen_clip_embs: list = []
    dedup_thr = float(fm_cfg.get("clip_semantic_dedup_threshold", 0.98))

    passed: List[str] = []
    stats = {"quarantine_duplicate": 0, "quarantine_decode_failed": 0, "quarantine_semantic_dup": 0}
    seen_fp: set = set()

    try:
        from tqdm import tqdm
        path_iter = tqdm(video_paths, desc="Ingest  pre-filter", unit="file")
    except ImportError:
        path_iter = video_paths
    for path in path_iter:
        if not os.path.isfile(path):
            continue

        # 1. Dedup
        if dedup and db_path:
            fp = fingerprinter.compute(path) or ""
            if fp:
                rep = db_tools.get_reproduce_info(db_path, fp)
                dup_in_batch = fp in seen_fp
                if rep is not None or dup_in_batch:
                    if _move_to_quarantine(path, "duplicate", cfg):
                        stats["quarantine_duplicate"] += 1
                        logger.info("Ingest 预检-重复: 已移入 quarantine — %s", os.path.basename(path))
                    continue
                seen_fp.add(fp)

                # CLIP 语义去重（MD5 通过后再检查语义相似度）
                if clip_embedder:
                    track("clip_dedup")
                    try:
                        emb = clip_embedder.get_embedding(path)
                        if clip_embedder.is_semantic_duplicate(emb, seen_clip_embs, dedup_thr):
                            _move_to_quarantine(path, "semantic_dup", cfg)
                            stats["quarantine_semantic_dup"] += 1
                            logger.info("CLIP 语义去重: %s", os.path.basename(path))
                            continue
                        seen_clip_embs.append(emb)
                    except Exception as e:
                        logger.warning("CLIP 语义去重异常跳过: %s", e)

        # 2. Decode check（按 modality 分发，v2.9 解耦）
        if decode_check:
            if not modality_handlers.decode_check(path, cfg):
                if _move_to_quarantine(path, "decode_failed", cfg):
                    stats["quarantine_decode_failed"] += 1
                    logger.warning("Ingest 预检-解码失败: 已移入 quarantine — %s", os.path.basename(path))
                continue

        passed.append(path)

    if stats["quarantine_duplicate"] or stats["quarantine_decode_failed"] or stats["quarantine_semantic_dup"]:
        logger.info("Ingest 预检: 隔离 重复=%d 解码失败=%d 语义重复=%d，%d 个进入 pipeline",
                    stats["quarantine_duplicate"], stats["quarantine_decode_failed"], stats["quarantine_semantic_dup"], len(passed))
    return passed, stats
