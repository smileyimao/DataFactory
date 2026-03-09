# labeling/labeling_export.py — 为接入 ML 做准备：导出合格/待标注清单，供 Label Studio / CVAT 等使用
"""
数据清洗与标注管道扩展（Roadmap v1 可选）：
扫描 storage/archive 下已归档批次，生成「待标注清单」manifest（路径、batch_id、元数据），
便于下游标注工具导入，避免重复标注已去重数据。
同时将图片及同名 .txt 拷贝到 export_dir/images/，下游可直接拷走整个 for_labeling 目录。
"""
import math
import os
import re
import json
import logging
import shutil
from collections import defaultdict
from typing import Any, Dict, List, Optional

from utils import file_tools
from utils.usage_tracker import track

logger = logging.getLogger(__name__)

# 常见可标注媒体扩展（含视频，用于批次浏览）
MEDIA_EXT = {".mp4", ".mov", ".avi", ".mkv", ".jpg", ".jpeg", ".png", ".bmp"}
# for_labeling 只接受图片帧，不接受视频文件
IMAGE_EXT  = {".jpg", ".jpeg", ".png", ".bmp"}

# COCO 80类名（yolov8s.pt 默认）
_COCO_NAMES = [
    "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat",
    "traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat",
    "dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack",
    "umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball",
    "kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
    "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
    "sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair",
    "couch","potted plant","bed","dining table","toilet","tv","laptop","mouse",
    "remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator",
    "book","clock","vase","scissors","teddy bear","hair drier","toothbrush",
]


def _annotate_image(src_img: str, txt_path: str, dst_img: str) -> bool:
    """将检测框和置信度画在图片上，保存到 dst_img。无检测数据则直接复制。"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        shutil.copy2(src_img, dst_img)
        return False

    img = cv2.imread(src_img)
    if img is None:
        shutil.copy2(src_img, dst_img)
        return False

    if not os.path.isfile(txt_path):
        cv2.imwrite(dst_img, img)
        return True

    h, w = img.shape[:2]
    with open(txt_path, "r") as f:
        lines = f.read().strip().splitlines()

    for line in lines:
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        cls_id = int(parts[0])
        xc, yc, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
        conf = float(parts[5]) if len(parts) >= 6 else None

        x1 = int((xc - bw / 2) * w)
        y1 = int((yc - bh / 2) * h)
        x2 = int((xc + bw / 2) * w)
        y2 = int((yc + bh / 2) * h)

        label = _COCO_NAMES[cls_id] if cls_id < len(_COCO_NAMES) else str(cls_id)
        text = f"{label} {conf:.2f}" if conf is not None else label

        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        font_scale = max(0.4, min(w, h) / 1000)
        thickness = max(1, int(font_scale * 2))
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        ty = max(y1 - 4, th + 4)
        cv2.rectangle(img, (x1, ty - th - 4), (x1 + tw + 4, ty), (0, 255, 0), -1)
        cv2.putText(img, text, (x1 + 2, ty - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness)

    cv2.imwrite(dst_img, img)
    return True


def list_batch_media(batch_dir: str, media_subdirs: Optional[tuple] = None, cfg: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """扫描 Batch 目录下产出子目录中的媒体文件。media_subdirs 或 cfg 二选一，cfg 时从 config 读取。
    支持两种结构：1) 子目录内直接 .jpg/.png；2) 子目录内 Normal/、Warning/ 含媒体文件。"""
    if media_subdirs is None and cfg is not None:
        from config import config_loader
        media_subdirs = config_loader.get_batch_media_subdirs(cfg)
    if media_subdirs is None:
        media_subdirs = ("refinery", "inspection", "source", "2_高置信_燃料", "3_待人工", "2_Mass_Production")
    out = []
    for sub in media_subdirs:
        d = os.path.join(batch_dir, sub)
        if not os.path.isdir(d):
            continue
        # 收集媒体文件：直接子目录或 Normal/Warning 下
        for root, _, files in os.walk(d, topdown=True):
            for name in sorted(files):
                ext = os.path.splitext(name)[1].lower()
                if ext not in MEDIA_EXT:
                    continue
                full = os.path.join(root, name)
                if not os.path.isfile(full):
                    continue
                rel = os.path.relpath(full, batch_dir)
                out.append({
                    "path": full,
                    "relative_path": rel,
                    "filename": name,
                    "subdir": sub,
                })
    return out


def export_manifest_for_labeling(
    archive_dir: str,
    export_dir: str,
    max_batches: Optional[int] = None,
    cfg: Optional[Dict[str, Any]] = None,
    inspection_only: bool = False,
    refinery_only: bool = False,
) -> str:
    """
    扫描 archive_dir 下所有 Batch_* 目录，汇总媒体文件清单，写入 export_dir/manifest_for_labeling.json。
    返回写入的 manifest 文件路径。cfg 可选，用于 path decoupling。
    inspection_only / refinery_only 二选一，仅导出对应子目录。
    """
    if inspection_only and refinery_only:
        raise ValueError("inspection_only 与 refinery_only 不可同时指定")
    os.makedirs(export_dir, exist_ok=True)
    batch_prefix = "Batch_"
    if cfg:
        from config import config_loader
        batch_prefix = config_loader.get_batch_prefix(cfg)
    batch_dirs = sorted([
        os.path.join(archive_dir, x)
        for x in os.listdir(archive_dir)
        if os.path.isdir(os.path.join(archive_dir, x)) and x.startswith(batch_prefix)
    ])
    if max_batches is not None:
        batch_dirs = batch_dirs[-max_batches:]

    subdirs = (cfg.get("paths", {}) or {}).get("batch_subdirs") or {}
    inspection_subdir = subdirs.get("inspection", "inspection")
    refinery_subdir = subdirs.get("refinery", "refinery")
    manifest = []
    for batch_dir in batch_dirs:
        batch_id = os.path.basename(batch_dir)
        items = list_batch_media(batch_dir, cfg=cfg)
        for item in items:
            if inspection_only and item.get("subdir") != inspection_subdir:
                continue
            if refinery_only and item.get("subdir") != refinery_subdir:
                continue
            item["batch_id"] = batch_id
            manifest.append(item)

    out_path = os.path.join(export_dir, "manifest_for_labeling.json")
    file_tools.atomic_write_json(out_path, manifest)
    logger.info("导出待标注清单: %d 条, 写入 %s", len(manifest), out_path)

    # 一键拷走：图片 + 同名 .txt 到 images/，用 batch_id_filename 避免跨批次重名
    images_dir = os.path.join(export_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    copied = 0
    for item in manifest:
        src_path = item["path"]
        batch_id = item["batch_id"]
        filename = item["filename"]
        base, ext = os.path.splitext(filename)
        dest_name = f"{batch_id}_{filename}"
        dest_path = os.path.join(images_dir, dest_name)
        txt_src = os.path.join(os.path.dirname(src_path), base + ".txt")
        try:
            shutil.copy2(src_path, dest_path)
            copied += 1
        except OSError as e:
            logger.warning("拷贝媒体失败 %s -> %s: %s", src_path, dest_path, e)
        if os.path.isfile(txt_src):
            txt_dest = os.path.join(images_dir, f"{batch_id}_{base}.txt")
            try:
                shutil.copy2(txt_src, txt_dest)
            except OSError as e:
                logger.warning("拷贝 txt 失败 %s -> %s: %s", txt_src, txt_dest, e)
    logger.info("已拷贝 %d 个媒体文件及同名 .txt 到 %s", copied, images_dir)
    return out_path


def run_export_from_config(
    cfg: Dict[str, Any],
    max_batches: Optional[int] = None,
    inspection_only: bool = False,
    refinery_only: bool = False,
) -> Optional[str]:
    """
    从配置读取 paths.data_warehouse（archive）与 paths.labeling_export（导出目录），
    若存在 labeling_export 则执行导出并返回 manifest 路径；否则返回 None。
    """
    paths = cfg.get("paths", {})
    archive = paths.get("data_warehouse", "")
    export_dir = paths.get("labeling_export")
    if not export_dir or not os.path.isdir(archive):
        return None
    return export_manifest_for_labeling(
        archive, export_dir, max_batches=max_batches, cfg=cfg,
        inspection_only=inspection_only, refinery_only=refinery_only,
    )


_FRAME_RE = re.compile(r"^(.+)_f\d{5}\.")


def _video_key(filename: str) -> str:
    """从帧文件名提取视频键（strip _fNNNNN 后缀），图片模式返回原名。"""
    m = _FRAME_RE.match(filename)
    return m.group(1) if m else filename


def _stratified_sample_by_video(items: list, rate: float) -> list:
    """
    按视频分组后各取 ceil(n * rate) 帧（至少 1 帧）。
    单帧组（图片模式）整批按 rate 全局抽，避免每张图都被抽到 100%。
    """
    groups = defaultdict(list)
    for item in items:
        groups[_video_key(item["filename"])].append(item)

    multi = [g for g in groups.values() if len(g) > 1]
    single = [g[0] for g in groups.values() if len(g) == 1]

    result = []
    for group in multi:
        k = max(1, math.ceil(len(group) * rate))
        step = len(group) / k
        result.extend(group[int(i * step)] for i in range(k))

    if single:
        k = max(1, math.ceil(len(single) * rate))
        step = len(single) / k
        result.extend(single[int(i * step)] for i in range(k))

    return result


def _collect_media_from_dir(dir_path: str) -> List[Dict[str, Any]]:
    """从目录递归收集图片文件（含 Normal/Warning 子目录或平铺）。只收集 IMAGE_EXT，不含视频。"""
    out = []
    if not os.path.isdir(dir_path):
        return out
    for root, _, files in os.walk(dir_path, topdown=True):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMAGE_EXT:
                continue
            full = os.path.join(root, name)
            if not os.path.isfile(full):
                continue
            out.append({"path": full, "filename": name})
    return out


def auto_update_after_batch(cfg: Dict[str, Any], path_info: Dict[str, Any]) -> Optional[str]:
    """
    待标池自动更新：inspection 全量 + refinery 按视频分层抽样，追加到 for_labeling manifest。
    若配置 labeling_pool.auto_update_after_batch 为 false 则跳过。
    返回 manifest 路径或 None。
    """
    pool_cfg = cfg.get("labeling_pool") or {}
    if not pool_cfg.get("auto_update_after_batch", True):
        return None
    upload_inspection = pool_cfg.get("upload_inspection", True)
    refinery_sample_rate = float(pool_cfg.get("refinery_sample_rate", 0.0))
    fuel_dir = path_info.get("fuel_dir", "")
    paths = cfg.get("paths", {})
    export_dir = paths.get("labeling_export")
    human_dir = path_info.get("human_dir", "")
    batch_id = path_info.get("batch_id", "")
    if not export_dir or not batch_id:
        return None
    images_dir = os.path.join(export_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    manifest_path = os.path.join(export_dir, "manifest_for_labeling.json")
    existing = []
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            logger.warning("读取现有 manifest 失败，将覆盖: %s", e)
    seen = {f"{x.get('batch_id', '')}_{x.get('filename', '')}" for x in existing}
    added = 0
    if upload_inspection and human_dir:
        # 读 inspection/manifest.json 获取 max_conf，用于主动学习排序
        insp_scores: dict = {}
        insp_manifest_path = os.path.join(human_dir, "manifest.json")
        if os.path.isfile(insp_manifest_path):
            try:
                with open(insp_manifest_path, "r", encoding="utf-8") as _f:
                    for entry in json.load(_f):
                        insp_scores[entry.get("filename", "")] = float(entry.get("max_conf", 1.0))
            except Exception as _e:
                logger.warning("读取 inspection manifest.json 失败，跳过排序: %s", _e)

        items = _collect_media_from_dir(human_dir)
        # 主动学习：按 max_conf 升序排列，置信度最低（最不确定）的帧排在最前
        items.sort(key=lambda it: insp_scores.get(it["filename"], 1.0))

        subdir = paths.get("batch_subdirs", {}).get("inspection", "inspection")
        for rank, item in enumerate(items, start=1):
            src_path = item["path"]
            filename = item["filename"]
            base, ext = os.path.splitext(filename)
            # 数字前缀确保 CVAT 按优先级顺序展示（000001_ 最不确定）
            priority_prefix = f"{rank:06d}_"
            dest_name = f"{priority_prefix}{batch_id}_{filename}"
            if dest_name in seen:
                continue
            seen.add(dest_name)
            dest_path = os.path.join(images_dir, dest_name)
            txt_src = os.path.join(os.path.dirname(src_path), base + ".txt")
            try:
                shutil.copy2(src_path, dest_path)
                added += 1
            except OSError as e:
                logger.warning("拷贝媒体失败 %s -> %s: %s", src_path, dest_path, e)
            if os.path.isfile(txt_src):
                txt_dest = os.path.join(images_dir, f"{priority_prefix}{batch_id}_{base}.txt")
                try:
                    shutil.copy2(txt_src, txt_dest)
                except OSError as e:
                    logger.warning("拷贝 txt 失败 %s -> %s: %s", txt_src, txt_dest, e)
            existing.append({
                "path": dest_path,
                "relative_path": f"images/{dest_name}",
                "filename": dest_name,
                "source_filename": filename,
                "subdir": subdir,
                "batch_id": batch_id,
                "max_conf": insp_scores.get(filename, None),
                "priority": rank,
            })
    refinery_added = 0
    if refinery_sample_rate > 0 and fuel_dir:
        refinery_items = _collect_media_from_dir(fuel_dir)

        # CLIP 多样性采样（开关控制，缺包回退到分层抽样）
        fm_cfg = cfg.get("foundation_models", {})
        clip_diversity = fm_cfg.get("clip_enabled") and fm_cfg.get("clip_diversity_sampling_enabled")
        k = max(1, math.ceil(len(refinery_items) * refinery_sample_rate))
        if clip_diversity and len(refinery_items) > k:
            try:
                from vision.foundation_models import load_clip_embedder
                embedder = load_clip_embedder(cfg)
                if embedder:
                    embeddings = [embedder.get_embedding(it["path"]) for it in refinery_items]
                    sampled = embedder.diversity_sample(refinery_items, embeddings, k)
                    track("clip_diversity_sample")
                    logger.info("CLIP 多样性采样: %d → %d 帧", len(refinery_items), len(sampled))
                else:
                    sampled = _stratified_sample_by_video(refinery_items, refinery_sample_rate)
            except Exception as e:
                logger.warning("CLIP 多样性采样失败，回退: %s", e)
                sampled = _stratified_sample_by_video(refinery_items, refinery_sample_rate)
        else:
            sampled = _stratified_sample_by_video(refinery_items, refinery_sample_rate)
        r_subdir = paths.get("batch_subdirs", {}).get("refinery", "refinery")
        for item in sampled:
            src_path = item["path"]
            filename = item["filename"]
            base, _ = os.path.splitext(filename)
            dest_name = f"{batch_id}_{filename}"
            if dest_name in seen:
                continue
            seen.add(dest_name)
            dest_path = os.path.join(images_dir, dest_name)
            txt_src = os.path.join(os.path.dirname(src_path), base + ".txt")
            try:
                shutil.copy2(src_path, dest_path)
                refinery_added += 1
            except OSError as e:
                logger.warning("拷贝 refinery 抽样失败 %s: %s", src_path, e)
            if os.path.isfile(txt_src):
                try:
                    shutil.copy2(txt_src, os.path.join(images_dir, f"{batch_id}_{base}.txt"))
                except OSError as e:
                    logger.warning("拷贝 refinery txt 失败: %s", e)
            existing.append({
                "path": dest_path,
                "relative_path": f"images/{dest_name}",
                "filename": filename,
                "subdir": r_subdir,
                "batch_id": batch_id,
            })
    if added > 0 or refinery_added > 0:
        file_tools.atomic_write_json(manifest_path, existing)
        if added > 0:
            logger.info("待标池: inspection 追加 %d 条 -> %s", added, manifest_path)
        if refinery_added > 0:
            logger.info("待标池: refinery 抽样 %d 条 (%.0f%%) -> %s", refinery_added, refinery_sample_rate * 100, manifest_path)
        return manifest_path
    return None
