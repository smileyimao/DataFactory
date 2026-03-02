# engines/labeled_return.py — 标注回传接收、伪标签对比、门槛报警、训练集并入
"""
标注团队回传 → 落盘 labeled_return → 与伪标签对比 → 低于门槛报警 → 达标并入 training。
"""
import json
import os
import shutil
import zipfile
import logging
from datetime import datetime
from core import time_utils
from typing import Any, Dict, List, Optional, Tuple

from engines import file_tools

logger = logging.getLogger(__name__)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
YOLO_LINE_LEN = 5  # class_id x_center y_center w h（第 6 列 conf 可选，对比时忽略）


def _toronto_now() -> str:
    return time_utils.now_toronto().strftime("%Y%m%d_%H%M%S")


def parse_yolo_txt(txt_path: str) -> List[Tuple[int, float, float, float, float]]:
    """解析 YOLO .txt，返回 [(class_id, x_center, y_center, w, h), ...]，归一化坐标。支持 6 列（含 conf），第 6 列忽略。"""
    out = []
    if not os.path.isfile(txt_path):
        return out
    with open(txt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < YOLO_LINE_LEN:
                continue
            try:
                cid = int(parts[0])
                x, y, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                out.append((cid, x, y, w, h))
            except (ValueError, IndexError):
                continue
    return out


def _box_iou_norm(
    a: Tuple[int, float, float, float, float],
    b: Tuple[int, float, float, float, float],
) -> float:
    """归一化坐标下两框 IoU，class 不同返回 0。"""
    cid_a, xa, ya, wa, ha = a
    cid_b, xb, yb, wb, hb = b
    if cid_a != cid_b:
        return 0.0
    x1 = max(xa - wa / 2, xb - wb / 2)
    y1 = max(ya - ha / 2, yb - hb / 2)
    x2 = min(xa + wa / 2, xb + wb / 2)
    y2 = min(ya + ha / 2, yb + hb / 2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area_a = wa * ha
    area_b = wb * hb
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _match_pairs(
    returned: List[Tuple[int, float, float, float, float]],
    pseudo: List[Tuple[int, float, float, float, float]],
    iou_thresh: float = 0.5,
) -> int:
    """贪心匹配：按 IoU 配对，返回匹配对数。"""
    used_pseudo = [False] * len(pseudo)
    matched = 0
    for ra in returned:
        best_iou, best_j = 0.0, -1
        for j, pb in enumerate(pseudo):
            if used_pseudo[j]:
                continue
            iou = _box_iou_norm(ra, pb)
            if iou >= iou_thresh and iou > best_iou:
                best_iou, best_j = iou, j
        if best_j >= 0:
            used_pseudo[best_j] = True
            matched += 1
    return matched


def compare_one_image(
    returned_boxes: List[Tuple[int, float, float, float, float]],
    pseudo_boxes: List[Tuple[int, float, float, float, float]],
    iou_thresh: float = 0.5,
) -> Tuple[int, int, int]:
    """返回 (匹配数, 回传框数, 伪标签框数)。伪标签一致率可用 2*matched/(n_returned+n_pseudo)。"""
    matched = _match_pairs(returned_boxes, pseudo_boxes, iou_thresh)
    return matched, len(returned_boxes), len(pseudo_boxes)


def load_export_manifest(for_labeling_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    读取 manifest_for_labeling.json，建立 export_filename -> 条目的映射。
    export_filename 即 for_labeling/images 下的文件名（batch_id_xxx.jpg）。
    """
    manifest_path = os.path.join(for_labeling_dir, "manifest_for_labeling.json")
    if not os.path.isfile(manifest_path):
        return {}
    with open(manifest_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    # 导出时命名规则: batch_id_filename；CVAT 导出可能用 sanitized（空格→下划线）
    out = {}
    for it in items:
        batch_id = it.get("batch_id", "")
        filename = it.get("filename", "")
        if not batch_id or not filename:
            continue
        export_name = f"{batch_id}_{filename}"
        out[export_name] = it
        base, ext = os.path.splitext(filename)
        out[f"{batch_id}_{base}.txt"] = it  # txt 用同一 source 路径推算
        # 支持 CVAT 导出的 sanitized 文件名（export_for_cvat 将空格替换为下划线）
        safe_export = file_tools.sanitize_filename(export_name)
        if safe_export != export_name:
            out[safe_export] = it
            out[file_tools.sanitize_filename(f"{batch_id}_{base}.txt")] = it
    return out


def _collect_batch_ids_from_manifest(manifest_map: Dict[str, Dict[str, Any]], import_dir: str) -> List[str]:
    """从 manifest 与 import_dir 内文件收集涉及的 batch_id 列表（去重）。"""
    seen: set = set()
    for name in os.listdir(import_dir):
        entry = manifest_map.get(name) or manifest_map.get(os.path.splitext(name)[0] + ".txt")
        if entry:
            bid = (entry.get("batch_id") or "").strip()
            if bid:
                seen.add(bid)
    return sorted(seen)


def get_pseudo_txt_path(manifest_entry: Dict[str, Any]) -> str:
    """由 manifest 条目的 path（archive 内图片路径）得到对应伪标签 .txt 路径。"""
    path = manifest_entry.get("path", "")
    if not path:
        return ""
    base, _ = os.path.splitext(path)
    return base + ".txt"


def import_from_directory(
    source_dir: str,
    base_dir: str,
    return_dir: str,
) -> Tuple[str, List[str]]:
    """
    将 source_dir 内图片+同名 .txt 拷贝到 return_dir/Import_YYYYMMDD_HHMMSS/。
    返回 (import_id, 拷贝的 export 文件名列表)。
    """
    import_id = "Import_" + _toronto_now()
    dest = os.path.join(return_dir, import_id)
    os.makedirs(dest, exist_ok=True)
    copied = []
    for name in sorted(os.listdir(source_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXT:
            src_path = os.path.join(source_dir, name)
            if not os.path.isfile(src_path):
                continue
            shutil.copy2(src_path, os.path.join(dest, name))
            copied.append(name)
            base, _ = os.path.splitext(name)
            txt_name = base + ".txt"
            txt_src = os.path.join(source_dir, txt_name)
            if os.path.isfile(txt_src):
                shutil.copy2(txt_src, os.path.join(dest, txt_name))
    logger.info("回传导入: %s, 共 %d 个媒体文件", import_id, len(copied))
    return import_id, copied


def import_from_zip(
    zip_path: str,
    base_dir: str,
    return_dir: str,
) -> Tuple[str, List[str]]:
    """解压到临时目录后调用 import_from_directory。"""
    import_id = "Import_" + _toronto_now()
    dest = os.path.join(return_dir, import_id)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    copied = []
    for name in sorted(os.listdir(dest)):
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXT:
            copied.append(name)
    logger.info("回传导入(zip): %s, 共 %d 个媒体文件", import_id, len(copied))
    return import_id, copied


def run_comparison(
    import_dir: str,
    manifest_map: Dict[str, Dict[str, Any]],
    archive_base: str,
    base_dir: str = "",
    iou_thresh: float = 0.5,
    filename_filter=None,
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    对 import_dir 内每张图，找到对应伪标签，计算伪标签一致率（与伪标签的差异程度）。
    返回 (整体伪标签一致率, 每图差异明细 diff_report)。
    伪标签一致率 = 2 * 总匹配数 / (总回传框数 + 总伪标签框数)，无框时该图算 1.0。
    注意：该指标衡量与伪标签的差异，用于触发差异复核，不反映人工标注质量。
    filename_filter: 若指定则只对集合内的文件名做对比（用于 refinery 抽检）。
    """
    total_matched = 0
    total_returned = 0
    total_pseudo = 0
    diff_report = []
    for name in sorted(os.listdir(import_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXT:
            continue
        if filename_filter is not None and name not in filename_filter:
            continue
        base, _ = os.path.splitext(name)
        txt_name = base + ".txt"
        returned_txt = os.path.join(import_dir, txt_name)
        entry = manifest_map.get(name) or manifest_map.get(txt_name)
        if not entry:
            diff_report.append({"file": name, "error": "manifest 中无对应项"})
            continue
        pseudo_txt = get_pseudo_txt_path(entry)
        if not pseudo_txt:
            diff_report.append({"file": name, "error": "无法推算伪标签路径"})
            continue
        # manifest 的 path 为 export 时的源路径（绝对或相对），伪标签为同目录同名 .txt
        if not os.path.isfile(pseudo_txt):
            if not os.path.isabs(pseudo_txt):
                for root in (base_dir, archive_base):
                    if root:
                        candidate = os.path.normpath(os.path.join(root, pseudo_txt))
                        if os.path.isfile(candidate):
                            pseudo_txt = candidate
                            break
        if not os.path.isfile(pseudo_txt):
            diff_report.append({"file": name, "error": "伪标签文件不存在"})
            continue
        ret_boxes = parse_yolo_txt(returned_txt)
        pse_boxes = parse_yolo_txt(pseudo_txt)
        matched, nr, np = compare_one_image(ret_boxes, pse_boxes, iou_thresh)
        total_matched += matched
        total_returned += nr
        total_pseudo += np
        if nr + np > 0:
            rate = 2.0 * matched / (nr + np)
            if rate < 1.0:
                diff_report.append({"file": name, "returned": nr, "pseudo": np, "matched": matched, "rate": round(rate, 4)})
    if total_returned + total_pseudo == 0:
        consistency_rate = 1.0
    else:
        consistency_rate = 2.0 * total_matched / (total_returned + total_pseudo)
    return consistency_rate, diff_report


def send_alert(
    cfg: dict,
    import_id: str,
    consistency_rate: float,
    threshold: float,
    diff_report: List[Dict[str, Any]],
) -> None:
    """伪标签一致率低于门槛时发邮件，提示人工标注与伪标签差异较大，需人工复核（使用 email_setting）。"""
    from . import notifier
    email_cfg = cfg.get("email_setting", {})
    if not email_cfg or not cfg.get("labeled_return", {}).get("alert_via_email", True):
        return
    subject = f"【标注回传报警】伪标签一致率 {consistency_rate:.2%} 低于 {threshold:.0%} - {import_id}"
    body = (
        f"厂长您好，\n\n"
        f"标注回传批次 {import_id} 与伪标签对比结果：伪标签一致率 {consistency_rate:.2%}，低于设定门槛 {threshold:.0%}。\n"
        f"说明：该指标衡量人工标注与模型伪标签的差异程度，差异大可能是标注员修正了模型错误（正常），也可能是标注偏差，请人工判断。\n"
        f"请对差异部分再次复核。\n\n"
        f"差异明细（前 20 条）：\n"
    )
    for i, row in enumerate(diff_report[:20]):
        body += f"  - {row.get('file', '')}: {row}\n"
    if len(diff_report) > 20:
        body += f"  ... 共 {len(diff_report)} 条\n"
    body += "\n本邮件由 DataFactory 自动生成。"
    try:
        notifier.send_mail(email_cfg, subject, body)
        logger.info("已发送标注回传报警邮件")
    except Exception as e:
        logger.warning("发送报警邮件失败: %s", e)


def send_refinery_alert(
    cfg: dict,
    import_id: str,
    consistency_rate: float,
    threshold: float,
    diff_report: List[Dict[str, Any]],
    sample_count: int,
) -> None:
    """Refinery 抽检一致率低时发邮件，给出 approved_split_confidence_threshold 调整建议。"""
    from . import notifier
    email_cfg = cfg.get("email_setting", {})
    if not email_cfg or not cfg.get("labeled_return", {}).get("alert_via_email", True):
        return
    ps = cfg.get("production_setting", {})
    current_thr = float(ps.get("approved_split_confidence_threshold", 0.60))
    suggested = round(min(current_thr + 0.05, 0.95), 2)
    top_pct = ps.get("refinery_top_pct", 30)

    subject = f"【Refinery 抽检报警】伪标签一致率 {consistency_rate:.2%}（抽检 {sample_count} 帧）- {import_id}"
    body = (
        f"厂长您好，\n\n"
        f"Refinery 抽检批次 {import_id} 结果：\n"
        f"  抽检帧数：{sample_count}\n"
        f"  伪标签一致率：{consistency_rate:.2%}（门槛 {threshold:.0%}）\n\n"
        f"⚠️ 模型在高置信区间仍有较高错误率，当前 refinery 阈值可能过低。\n\n"
        f"建议操作（二选一）：\n"
        f"  1. 提高置信门槛：将 production_setting.approved_split_confidence_threshold\n"
        f"     从当前 {current_thr:.2f} 提高到 {suggested:.2f}\n"
        f"  2. 缩小 refinery 范围：将 production_setting.refinery_top_pct\n"
        f"     从当前 {top_pct} 降低（减少进入 refinery 的帧比例）\n\n"
        f"差异明细（前 20 条）：\n"
    )
    for row in diff_report[:20]:
        body += (
            f"  - {row.get('file', '')}: "
            f"returned={row.get('returned', 0)} pseudo={row.get('pseudo', 0)} "
            f"matched={row.get('matched', 0)} rate={row.get('rate', 0):.2%}\n"
        )
    if len(diff_report) > 20:
        body += f"  ... 共 {len(diff_report)} 条\n"
    body += "\n本邮件由 DataFactory 自动生成。"
    try:
        notifier.send_mail(email_cfg, subject, body)
        logger.info("已发送 refinery 抽检报警邮件")
    except Exception as e:
        logger.warning("发送 refinery 抽检报警邮件失败: %s", e)


def merge_to_training(
    import_dir: str,
    training_dir: str,
    import_id: str,
    cfg: Optional[dict] = None,
) -> int:
    """将 import_dir 内图片+txt 并入 training_dir/import_id/，返回文件数。使用 retry 防静默失败。
    若 labeled_return.skip_empty_labels 为 true，则跳过 .txt 为空的图（未标的变化不大相似帧）。"""
    from engines import retry_utils
    retry_cfg = (cfg or {}).get("retry", {})
    max_attempts = retry_cfg.get("max_attempts", 3)
    backoff = retry_cfg.get("backoff_seconds", 1.0)
    skip_empty = (cfg or {}).get("labeled_return", {}).get("skip_empty_labels", False)
    dest = os.path.join(training_dir, import_id)
    os.makedirs(dest, exist_ok=True)
    count = 0
    skipped_empty = 0
    for name in sorted(os.listdir(import_dir)):
        path = os.path.join(import_dir, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXT and ext != ".txt":
            continue
        if skip_empty and ext in IMAGE_EXT:
            base, _ = os.path.splitext(name)
            txt_path = os.path.join(import_dir, base + ".txt")
            if not os.path.isfile(txt_path) or not parse_yolo_txt(txt_path):
                skipped_empty += 1
                continue
        if skip_empty and ext == ".txt":
            if not parse_yolo_txt(path):
                continue
        dest_path = os.path.join(dest, name)
        if retry_utils.safe_copy_with_retry(path, dest_path, max_attempts, backoff):
            count += 1
    if skipped_empty > 0:
        logger.info("训练集并入: %s -> %s, %d 个文件（跳过 %d 张无标注图）", import_id, dest, count, skipped_empty)
    else:
        logger.info("训练集并入: %s -> %s, %d 个文件", import_id, dest, count)
    return count


def copy_to_batch_labeled(
    import_dir: str,
    manifest_map: Dict[str, Dict[str, Any]],
    archive_base: str,
    labeled_subdir: str = "labeled",
    cfg: Optional[dict] = None,
) -> int:
    """
    将达标标注按 batch_id 写回 archive/Batch_xxx/labeled/，保持批次血缘。
    使用 retry 防磁盘满/权限不足时静默失败；失败时打 warning 并计入 metrics。
    若 labeled_return.skip_empty_labels 为 true，跳过无标注的图。
    返回写入 batch labeled 的文件数。
    """
    from engines import retry_utils
    if not archive_base or not os.path.isdir(archive_base):
        return 0
    retry_cfg = (cfg or {}).get("retry", {})
    max_attempts = retry_cfg.get("max_attempts", 3)
    backoff = retry_cfg.get("backoff_seconds", 1.0)
    skip_empty = (cfg or {}).get("labeled_return", {}).get("skip_empty_labels", False)
    count = 0
    for name in sorted(os.listdir(import_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXT and ext != ".txt":
            continue
        if skip_empty and ext in IMAGE_EXT:
            base, _ = os.path.splitext(name)
            txt_path = os.path.join(import_dir, base + ".txt")
            if not os.path.isfile(txt_path) or not parse_yolo_txt(txt_path):
                continue
        if skip_empty and ext == ".txt":
            if not parse_yolo_txt(os.path.join(import_dir, name)):
                continue
        entry = manifest_map.get(name)
        if not entry:
            base, _ = os.path.splitext(name)
            entry = manifest_map.get(base + ".txt")
        if not entry:
            continue
        batch_id = entry.get("batch_id", "").strip()
        if not batch_id:
            continue
        batch_dir = os.path.join(archive_base, batch_id)
        labeled_dir = os.path.join(batch_dir, labeled_subdir)
        if not os.path.isdir(batch_dir):
            continue
        try:
            os.makedirs(labeled_dir, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.warning("创建 labeled 目录失败 %s: %s", labeled_dir, e)
            continue
        src = os.path.join(import_dir, name)
        if os.path.isfile(src):
            dest_path = os.path.join(labeled_dir, name)
            if retry_utils.safe_copy_with_retry(src, dest_path, max_attempts, backoff):
                count += 1
            # 失败时 safe_copy_with_retry 已打 warning，不静默
    if count > 0:
        logger.info("标注回写批次 labeled: %d 个文件 -> archive/Batch_xxx/%s/", count, labeled_subdir)
    return count


def run_full_pipeline(
    cfg: dict,
    source_dir: Optional[str] = None,
    zip_path: Optional[str] = None,
    dry_run: bool = False,
    skip_merge: bool = False,
) -> Dict[str, Any]:
    """
    回传接收 → 对比 → 报警（若低于门槛）→ 达标则并入训练集。
    source_dir 或 zip_path 二选一。返回摘要。
    """
    from config import config_loader
    base_dir = config_loader.get_base_dir()
    paths = cfg.get("paths", {})
    return_dir = paths.get("labeled_return", "")
    training_dir = paths.get("training", "")
    for_labeling_dir = paths.get("labeling_export", "")
    lr_cfg = cfg.get("labeled_return", {})
    threshold = float(lr_cfg.get("consistency_threshold", 0.95))
    archive_base = paths.get("data_warehouse", "")

    if not os.path.isdir(return_dir):
        os.makedirs(return_dir, exist_ok=True)

    if zip_path and os.path.isfile(zip_path):
        import_id, file_list = import_from_zip(zip_path, base_dir, return_dir)
    elif source_dir and os.path.isdir(source_dir):
        import_id, file_list = import_from_directory(source_dir, base_dir, return_dir)
    else:
        return {"ok": False, "error": "请指定 --dir 或 --zip"}

    import_dir = os.path.join(return_dir, import_id)
    manifest_map = load_export_manifest(for_labeling_dir)
    if not manifest_map:
        return {"ok": False, "error": "未找到 manifest_for_labeling.json，请先运行 export_for_labeling"}

    consistency_rate, diff_report = run_comparison(
        import_dir, manifest_map, archive_base, base_dir=base_dir, iou_thresh=0.5
    )
    passed = consistency_rate >= threshold

    # 写差异报告到 import 目录
    report_path = os.path.join(import_dir, "comparison_report.json")
    if not dry_run:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({
                "import_id": import_id,
                "consistency_rate": consistency_rate,
                "threshold": threshold,
                "passed": passed,
                "diff_count": len(diff_report),
                "diff_report": diff_report,
            }, f, indent=2, ensure_ascii=False)

    if not passed and not dry_run:
        send_alert(cfg, import_id, consistency_rate, threshold, diff_report)

    # Refinery 抽检：对抽样帧单独计算 IoU，低于门槛时发专项报警
    refinery_names = {
        name for name, entry in manifest_map.items()
        if entry.get("subdir") == "refinery"
    }
    refinery_rate = None
    refinery_sample_count = 0
    if refinery_names and not dry_run:
        refinery_returned = {
            f for f in os.listdir(import_dir)
            if os.path.splitext(f)[1].lower() in IMAGE_EXT and f in refinery_names
        }
        if refinery_returned:
            refinery_rate, refinery_diff = run_comparison(
                import_dir, manifest_map, archive_base,
                base_dir=base_dir, iou_thresh=0.5,
                filename_filter=refinery_returned,
            )
            refinery_sample_count = len(refinery_returned)
            print(f"   🔍 Refinery 抽检: {refinery_sample_count} 帧, 一致率 {refinery_rate:.2%}")
            if refinery_rate < threshold:
                send_refinery_alert(cfg, import_id, refinery_rate, threshold, refinery_diff, refinery_sample_count)

    merged_count = 0
    batch_labeled_count = 0
    if passed and not dry_run:
        if not skip_merge and training_dir:
            merged_count = merge_to_training(import_dir, training_dir, import_id, cfg)
        # 按 batch_id 写回 archive/Batch_xxx/labeled/，保持批次血缘
        labeled_subdir = paths.get("batch_subdirs", {}).get("labeled", "labeled")
        batch_labeled_count = copy_to_batch_labeled(
            import_dir, manifest_map, archive_base, labeled_subdir, cfg
        )
        # v3 血缘：记录 label_import 关联
        batch_ids = _collect_batch_ids_from_manifest(manifest_map, import_dir)
        if batch_ids and training_dir:
            from engines import db_tools
            db_path = paths.get("db_url", "")
            if db_path:
                db_tools.record_label_import(
                    db_path,
                    import_id,
                    batch_ids,
                    os.path.join(training_dir, import_id),
                    consistency_rate,
                    merged_count,
                )

    return {
        "ok": True,
        "import_id": import_id,
        "consistency_rate": consistency_rate,
        "threshold": threshold,
        "passed": passed,
        "diff_count": len(diff_report),
        "merged_count": merged_count,
        "batch_labeled_count": batch_labeled_count,
        "dry_run": dry_run,
        "refinery_rate": refinery_rate,
        "refinery_sample_count": refinery_sample_count,
    }
