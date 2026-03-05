# core/pending_queue.py — 待复核队列：blocked 项入队，供中控台读取与决策
"""
厂长中控台队列：blocked 项写入 JSON，不阻塞产线；中控台读取后单项/批量放行或拒绝。
路径从 config 读取（path decoupling）。
"""
import json
import os
import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple

import cv2

from utils import time_utils

logger = logging.getLogger(__name__)

THUMBS_SUBDIR = "thumbs"


def _toronto_now(cfg: Dict[str, Any] = None) -> str:
    return time_utils.now_toronto(cfg).strftime("%Y-%m-%d %H:%M:%S")


def _extract_thumbnail(video_path: str, thumb_path: str, max_size: int = 320) -> bool:
    """从视频首帧提取缩略图，保存为 jpg。"""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return False
        h, w = frame.shape[:2]
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        cv2.imwrite(thumb_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return True
    except Exception as e:
        logger.warning("缩略图提取失败 %s: %s", video_path, e)
        return False


def add_items(
    cfg: Dict[str, Any],
    blocked: List[Dict[str, Any]],
    path_info: Dict[str, Any],
) -> int:
    """
    将 blocked 项加入待复核队列，生成缩略图。返回入队数量。
    """
    if not blocked:
        return 0
    from config import config_loader
    queue_path = config_loader.get_pending_queue_path(cfg)
    thumbs_dir = config_loader.get_pending_thumbs_dir(cfg)
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)
    os.makedirs(thumbs_dir, exist_ok=True)

    existing: List[Dict] = []
    if os.path.isfile(queue_path):
        try:
            with open(queue_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []

    batch_id = path_info.get("batch_id", "")
    added = 0
    for item in blocked:
        item_id = str(uuid.uuid4())[:8]
        archive_path = item.get("archive_path", "")
        thumb_rel = f"{THUMBS_SUBDIR}/{item_id}.jpg"
        thumb_abs = os.path.join(thumbs_dir, f"{item_id}.jpg")
        if archive_path and os.path.isfile(archive_path):
            _extract_thumbnail(archive_path, thumb_abs)
        entry = {
            "id": item_id,
            "batch_id": batch_id,
            "filename": item.get("filename", ""),
            "archive_path": archive_path,
            "score": item.get("score", 0),
            "rule_stats": item.get("rule_stats") or {},
            "is_duplicate": item.get("is_duplicate", False),
            "duplicate_batch_id": item.get("duplicate_batch_id"),
            "duplicate_created_at": item.get("duplicate_created_at"),
            "fingerprint": item.get("fingerprint"),
            "thumbnail": thumb_rel,
            "created_at": _toronto_now(cfg),
            "path_info": path_info,
        }
        existing.append(entry)
        added += 1

    try:
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.exception("写入待复核队列失败: %s", e)
        return 0
    logger.info("待复核队列: 新增 %d 项，共 %d 项", added, len(existing))
    return added


def get_all(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """获取队列中全部待复核项。"""
    from config import config_loader
    queue_path = config_loader.get_pending_queue_path(cfg)
    if not os.path.isfile(queue_path):
        return []
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("读取待复核队列失败: %s", e)
        return []


def _save_queue(cfg: Dict[str, Any], items: List[Dict[str, Any]]) -> bool:
    from config import config_loader
    queue_path = config_loader.get_pending_queue_path(cfg)
    try:
        os.makedirs(os.path.dirname(queue_path), exist_ok=True)
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        logger.exception("保存待复核队列失败: %s", e)
        return False


def apply_decision(
    cfg: Dict[str, Any],
    item_id: str,
    decision: str,
) -> Tuple[bool, Optional[str]]:
    """
    对单项执行放行或拒绝，调用 archiver 归档。返回 (成功, 错误信息)。
    """
    items = get_all(cfg)
    idx = next((i for i, x in enumerate(items) if x.get("id") == item_id), None)
    if idx is None:
        return False, "未找到该项"
    item = items.pop(idx)
    path_info = item.get("path_info") or {}
    if decision == "approve":
        from core import archiver
        archiver.archive_approved_items(cfg, [item], path_info)
    else:
        reason = "duplicate" if item.get("is_duplicate") else "quality"
        from core import archiver
        archiver.archive_rejected(cfg, [(item, reason)], path_info.get("batch_id", ""))
    if not _save_queue(cfg, items):
        return False, "队列保存失败"
    return True, None


def apply_batch_decision(
    cfg: Dict[str, Any],
    item_ids: List[str],
    decision: str,
) -> Tuple[int, List[str]]:
    """
    批量执行放行或拒绝。返回 (成功数, 失败 id 列表)。
    放行时一次性调用 archive_produced，避免逐项跑量产（抽帧+YOLO）导致极慢。
    """
    items_list = get_all(cfg)
    found_ids = {x.get("id") for x in items_list}
    failed = [iid for iid in item_ids if iid not in found_ids]

    to_process: List[Tuple[int, Dict[str, Any]]] = []
    for iid in item_ids:
        if iid in failed:
            continue
        idx = next((i for i, x in enumerate(items_list) if x.get("id") == iid), None)
        if idx is not None:
            to_process.append((idx, items_list[idx]))

    if not to_process:
        return 0, failed

    # 从队列移除（按索引倒序，避免 pop 后索引错位）
    for idx, _ in sorted(to_process, key=lambda x: -x[0]):
        items_list.pop(idx)

    collected = [item for _, item in to_process]
    path_info = collected[0].get("path_info") or {}

    if decision == "approve":
        from core import archiver
        archiver.archive_approved_items(cfg, collected, path_info)
    else:
        from core import archiver
        reasons = [("duplicate" if x.get("is_duplicate") else "quality") for x in collected]
        archiver.archive_rejected(cfg, list(zip(collected, reasons)), path_info.get("batch_id", ""))

    if not _save_queue(cfg, items_list):
        return 0, list(item_ids)
    return len(collected), failed
