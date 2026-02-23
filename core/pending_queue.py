# core/pending_queue.py — 待复核队列：blocked 项入队，供中控台读取与决策
"""
厂长中控台队列：blocked 项写入 JSON，不阻塞产线；中控台读取后单项/批量放行或拒绝。
"""
import json
import os
import uuid
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

import cv2

logger = logging.getLogger(__name__)

QUEUE_DIR = "storage/pending_review"
QUEUE_FILE = "queue.json"
THUMBS_DIR = "thumbs"


def _toronto_now() -> str:
    return datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")


def _get_queue_path(base_dir: str) -> str:
    return os.path.join(base_dir, QUEUE_DIR, QUEUE_FILE)


def _get_thumbs_dir(base_dir: str) -> str:
    return os.path.join(base_dir, QUEUE_DIR, THUMBS_DIR)


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
    base_dir: str,
    blocked: List[Dict[str, Any]],
    path_info: Dict[str, Any],
) -> int:
    """
    将 blocked 项加入待复核队列，生成缩略图。返回入队数量。
    """
    if not blocked:
        return 0
    queue_path = _get_queue_path(base_dir)
    thumbs_dir = _get_thumbs_dir(base_dir)
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
        thumb_rel = f"{THUMBS_DIR}/{item_id}.jpg"
        thumb_abs = os.path.join(base_dir, QUEUE_DIR, thumb_rel)
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
            "created_at": _toronto_now(),
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


def get_all(base_dir: str) -> List[Dict[str, Any]]:
    """获取队列中全部待复核项。"""
    queue_path = _get_queue_path(base_dir)
    if not os.path.isfile(queue_path):
        return []
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("读取待复核队列失败: %s", e)
        return []


def _save_queue(base_dir: str, items: List[Dict[str, Any]]) -> bool:
    queue_path = _get_queue_path(base_dir)
    try:
        os.makedirs(os.path.dirname(queue_path), exist_ok=True)
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        logger.exception("保存待复核队列失败: %s", e)
        return False


def apply_decision(
    base_dir: str,
    item_id: str,
    decision: str,
    cfg: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """
    对单项执行放行或拒绝，调用 archiver 归档。返回 (成功, 错误信息)。
    """
    items = get_all(base_dir)
    idx = next((i for i, x in enumerate(items) if x.get("id") == item_id), None)
    if idx is None:
        return False, "未找到该项"
    item = items.pop(idx)
    if cfg is None:
        from config import config_loader
        config_loader.set_base_dir(base_dir)
        cfg = config_loader.load_config()
    path_info = item.get("path_info") or {}
    if decision == "approve":
        from core import archiver
        archiver.archive_produced(cfg, [], [item], path_info)
    else:
        reason = "duplicate" if item.get("is_duplicate") else "quality"
        from core import archiver
        archiver.archive_rejected(cfg, [(item, reason)], path_info.get("batch_id", ""))
    if not _save_queue(base_dir, items):
        return False, "队列保存失败"
    return True, None


def apply_batch_decision(
    base_dir: str,
    item_ids: List[str],
    decision: str,
    cfg: Optional[dict] = None,
) -> Tuple[int, List[str]]:
    """
    批量执行放行或拒绝。返回 (成功数, 失败 id 列表)。
    """
    if cfg is None:
        from config import config_loader
        config_loader.set_base_dir(base_dir)
        cfg = config_loader.load_config()
    failed = []
    for iid in item_ids:
        ok, err = apply_decision(base_dir, iid, decision, cfg)
        if not ok:
            failed.append(iid)
    return len(item_ids) - len(failed), failed
