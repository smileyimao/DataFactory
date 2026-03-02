#!/usr/bin/env python3
# scripts/cvat_pull_annotations.py — 从本地 CVAT 拉取已标注 Task，转 YOLO 格式，触发 labeled_return
"""
人工在 CVAT 完成标注后，运行此脚本：
  1. 从本地 CVAT 下载标注 XML（CVAT for images 1.1）
  2. 解析 XML → YOLO .txt（每张图配对写出）
  3. 组装 import 目录（图片 + YOLO txt）
  4. 调用 labeled_return 流水线（IoU 对比 → 报警 → 并入 storage/training/）
  5. 血缘自动记录到 DB + MLflow

用法:
  python scripts/cvat_pull_annotations.py --task-id 1
  python scripts/cvat_pull_annotations.py --task-id 1 --no-merge   # 只对比，不并入
  python scripts/cvat_pull_annotations.py --task-id 1 --dry-run    # 只打印，不写文件
  python scripts/cvat_pull_annotations.py --list                   # 列出所有 Task 进度
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, SCRIPT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

try:
    import requests
except ImportError:
    requests = None

from cvat_api import _get_session, CVAT_URL

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


# ─── CVAT API ───────────────────────────────────────────────────────────────

def _list_tasks() -> List[dict]:
    """列出所有 Task（分页合并）。"""
    sess = _get_session()
    if not sess:
        return []
    results = []
    url = f"{CVAT_URL}/api/tasks?page_size=100"
    while url:
        r = sess.get(url, timeout=30)
        if r.status_code != 200:
            break
        data = r.json()
        results.extend(data.get("results", []))
        url = data.get("next")
    sess.close()
    return results


def _get_job_stats(task_id: int) -> dict:
    """返回 Task 下 jobs 的标注完成情况。"""
    sess = _get_session()
    if not sess:
        return {}
    r = sess.get(f"{CVAT_URL}/api/jobs?task_id={task_id}&page_size=100", timeout=30)
    sess.close()
    if r.status_code != 200:
        return {}
    jobs = r.json().get("results", [])
    done = sum(
        1 for j in jobs
        if j.get("stage") in ("acceptance", "validation")
        or j.get("state") == "completed"
    )
    return {"total": len(jobs), "done": done}


def _get_task_labels(task_id: int) -> List[str]:
    """
    返回 Task 的 label 名称列表，按 label id 升序排列。
    用 /api/labels?task_id= 覆盖任务自带 label 和继承自 Project 的 label。
    """
    sess = _get_session()
    if not sess:
        return []
    r = sess.get(f"{CVAT_URL}/api/labels?task_id={task_id}&page_size=200", timeout=30)
    sess.close()
    if r.status_code != 200:
        return []
    results = r.json().get("results", [])
    results_sorted = sorted(results, key=lambda x: x.get("id", 0))
    return [lbl["name"] for lbl in results_sorted]


def _download_annotations_zip(task_id: int, output_path: str) -> bool:
    """
    下载 Task 标注 zip（CVAT for images 1.1）。
    CVAT v2 新流程：
      1. POST /api/tasks/{id}/dataset/export?format=...&save_images=false → 202 + rq_id
      2. GET  /api/requests/{rq_id} 轮询，status=finished 时取 result_url
      3. GET  result_url → 下载 zip
    最多等 120 秒。
    """
    import urllib.parse

    sess = _get_session()
    if not sess:
        return False

    # Step 1：触发导出
    r = sess.post(
        f"{CVAT_URL}/api/tasks/{task_id}/dataset/export",
        params={"format": "CVAT for images 1.1", "save_images": "false"},
        timeout=30,
    )
    if r.status_code not in (200, 201, 202):
        print(f"    ⚠️  触发导出失败 HTTP {r.status_code}: {r.text[:200]}")
        sess.close()
        return False

    try:
        rq_id = r.json().get("rq_id", "")
    except Exception:
        rq_id = ""

    if not rq_id:
        print("    ⚠️  未获取到 rq_id")
        sess.close()
        return False

    # Step 2：轮询请求状态
    encoded = urllib.parse.quote(rq_id, safe="")
    result_url = ""
    for _ in range(60):
        time.sleep(2)
        r2 = sess.get(f"{CVAT_URL}/api/requests/{encoded}", timeout=10)
        if r2.status_code == 200:
            d = r2.json()
            status = d.get("status", "")
            if status == "finished":
                result_url = d.get("result_url", "")
                break
            if status == "failed":
                print(f"    ⚠️  导出任务失败: {d.get('message','')}")
                sess.close()
                return False

    if not result_url:
        print("    ⚠️  导出超时或未获取到 result_url")
        sess.close()
        return False

    # Step 3：下载 zip
    r3 = sess.get(result_url, timeout=120, allow_redirects=True)
    sess.close()
    if r3.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(r3.content)
        return True

    print(f"    ⚠️  下载失败 HTTP {r3.status_code}")
    return False


# ─── XML → YOLO ─────────────────────────────────────────────────────────────

def _parse_cvat_xml(
    xml_path: str,
    class_names: List[str],
) -> Dict[str, List[Tuple[int, float, float, float, float]]]:
    """
    解析 CVAT for images 1.1 XML。
    返回 {image_name: [(class_id, x_center, y_center, w, h), ...]}，归一化坐标。
    未知 label 跳过；坐标 clamp 到 [0, 1]。
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        print(f"    ❌ XML 解析失败: {e}")
        return {}

    name_to_id = {name: i for i, name in enumerate(class_names)}
    result: Dict[str, List] = {}

    for img_el in tree.getroot().findall("image"):
        img_name = img_el.get("name", "")
        if not img_name:
            continue
        width = float(img_el.get("width") or 1) or 1
        height = float(img_el.get("height") or 1) or 1

        boxes = []
        for box_el in img_el.findall("box"):
            label = box_el.get("label", "")
            if label not in name_to_id:
                continue
            try:
                xtl = float(box_el.get("xtl", 0))
                ytl = float(box_el.get("ytl", 0))
                xbr = float(box_el.get("xbr", 0))
                ybr = float(box_el.get("ybr", 0))
            except (ValueError, TypeError):
                continue

            x_c = max(0.0, min(1.0, (xtl + xbr) / 2 / width))
            y_c = max(0.0, min(1.0, (ytl + ybr) / 2 / height))
            w   = max(0.0, min(1.0, (xbr - xtl) / width))
            h   = max(0.0, min(1.0, (ybr - ytl) / height))

            if w > 0 and h > 0:
                boxes.append((name_to_id[label], x_c, y_c, w, h))

        result[img_name] = boxes

    return result


def _build_import_dir(
    annotation_map: Dict[str, List],
    images_dir: str,
    dest_dir: str,
) -> Tuple[int, int]:
    """
    将 for_labeling/images/ 中的图片 + CVAT 标注写到 dest_dir。
    返回 (成功匹配图片数, 未找到源图片数)。
    图片名先精确匹配，再 sanitize 兼容。
    """
    from engines import file_tools

    os.makedirs(dest_dir, exist_ok=True)
    matched = 0
    missing = 0

    for img_name, boxes in annotation_map.items():
        # 精确匹配
        src_img = os.path.join(images_dir, img_name)
        dest_name = img_name

        # sanitize 兼容：CVAT 存的是 sanitized 名，但 images_dir 里可能也是 sanitized
        if not os.path.isfile(src_img):
            sanitized = file_tools.sanitize_filename(img_name)
            src_img = os.path.join(images_dir, sanitized)
            dest_name = sanitized

        if not os.path.isfile(src_img):
            missing += 1
            continue

        # 拷贝图片
        shutil.copy2(src_img, os.path.join(dest_dir, dest_name))

        # 写 YOLO .txt（即使 boxes 为空，也写空文件——代表人工确认无目标）
        base, _ = os.path.splitext(dest_name)
        txt_path = os.path.join(dest_dir, base + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            for cid, x_c, y_c, w, h in boxes:
                f.write(f"{cid} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}\n")

        matched += 1

    return matched, missing


# ─── 主流程 ─────────────────────────────────────────────────────────────────

def pull_and_import(
    task_id: int,
    skip_merge: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    完整拉取流程：
      CVAT Task → 下载 XML → 解析 → YOLO txt → labeled_return 流水线
    返回 labeled_return.run_full_pipeline 的结果 dict，附加 task_id/class_names/annotated_images。
    """
    from config import config_loader
    from engines import labeled_return

    config_loader.set_base_dir(BASE_DIR)
    cfg, paths = config_loader.get_config_and_paths(BASE_DIR)

    # for_labeling 路径（get_config_and_paths 统一用 for_labeling 键）
    for_labeling_dir = paths.get("for_labeling", "")
    images_dir = os.path.join(for_labeling_dir, "images")

    if not os.path.isdir(images_dir):
        return {
            "ok": False,
            "error": f"for_labeling/images 不存在: {images_dir}\n"
                     "请先运行 python main.py --auto-cvat 完成 QC 并导出",
        }

    # 1. 获取 label 列表（决定 class_id 顺序）
    print(f"  获取 Task {task_id} 的 label 列表...")
    class_names = _get_task_labels(task_id)
    if not class_names:
        return {"ok": False, "error": "无法获取 Task labels，CVAT 未启动或 Task ID 不存在"}
    print(f"    Labels ({len(class_names)}): {class_names}")

    with tempfile.TemporaryDirectory(prefix="cvat_pull_") as tmp:
        ann_zip = os.path.join(tmp, "annotations.zip")

        # 2. 下载标注 zip
        print(f"  下载 Task {task_id} 标注（CVAT for images 1.1）...")
        if not _download_annotations_zip(task_id, ann_zip):
            return {
                "ok": False,
                "error": "下载标注失败。请确认 CVAT 正在运行，且 Task 已有标注数据",
            }
        print(f"    下载完成 ({os.path.getsize(ann_zip) // 1024} KB)")

        # 解压 XML
        with zipfile.ZipFile(ann_zip, "r") as zf:
            xml_files = [n for n in zf.namelist() if n.endswith(".xml")]
            if not xml_files:
                return {"ok": False, "error": "标注 zip 内无 XML 文件"}
            zf.extract(xml_files[0], tmp)
            ann_xml = os.path.join(tmp, xml_files[0])

        # 3. 解析 XML → YOLO 坐标映射
        annotation_map = _parse_cvat_xml(ann_xml, class_names)
        total_boxes = sum(len(v) for v in annotation_map.values())
        print(f"    解析: {len(annotation_map)} 张图，共 {total_boxes} 个框")

        # 4. 组装 import 目录（图片 + YOLO txt）
        import_src = os.path.join(tmp, "import_src")
        matched, missing = _build_import_dir(annotation_map, images_dir, import_src)
        print(f"    匹配: {matched} 张图组装完成（{missing} 张未找到源图片）")

        if matched == 0:
            return {
                "ok": False,
                "error": (
                    "没有图片匹配成功。\n"
                    "可能原因：for_labeling/images/ 内容与 Task 标注的图片名不一致，\n"
                    "请确认 Task 是由 export_for_cvat.py 生成的 zip 创建的。"
                ),
            }

        # 5. 触发 labeled_return 流水线
        print("  触发 labeled_return 流水线...")
        result = labeled_return.run_full_pipeline(
            cfg,
            source_dir=import_src,
            dry_run=dry_run,
            skip_merge=skip_merge,
        )

    result.update({
        "task_id": task_id,
        "class_names": class_names,
        "annotated_images": matched,
        "missing_images": missing,
    })
    return result


# ─── CLI ────────────────────────────────────────────────────────────────────

def cmd_list() -> int:
    """列出所有 Task，显示标注进度。"""
    tasks = _list_tasks()
    if not tasks:
        print("❌ 无法获取 Task 列表（CVAT 未启动或认证失败）")
        return 1

    print(f"\n  {'ID':<6} {'进度':<12} {'状态':<14} 名称")
    print("  " + "─" * 56)
    for t in tasks:
        tid = t.get("id", "?")
        name = t.get("name", "")
        status = t.get("status", "")
        if isinstance(tid, int):
            stats = _get_job_stats(tid)
            prog = f"{stats.get('done',0)}/{stats.get('total',0)} jobs"
        else:
            prog = ""
        print(f"  {str(tid):<6} {prog:<12} {status:<14} {name}")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从本地 CVAT 拉取标注，转 YOLO 格式，触发 labeled_return 流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python scripts/cvat_pull_annotations.py --list\n"
            "  python scripts/cvat_pull_annotations.py --task-id 1\n"
            "  python scripts/cvat_pull_annotations.py --task-id 1 --dry-run\n"
        ),
    )
    parser.add_argument("--task-id", type=int, default=None, metavar="ID",
                        help="CVAT Task ID（从 --list 获取）")
    parser.add_argument("--list", action="store_true",
                        help="列出所有 Task 及标注进度后退出")
    parser.add_argument("--no-merge", action="store_true",
                        help="只做 IoU 对比，不将标注并入 storage/training/")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印结果，不写任何文件、不发邮件、不并入")
    args = parser.parse_args()

    if not requests:
        print("❌ 缺少依赖: pip install requests")
        return 1

    print(f"\n📡 CVAT: {CVAT_URL}")

    if args.list:
        return cmd_list()

    if not args.task_id:
        parser.error("请指定 --task-id <ID>，或使用 --list 查看所有 Task")

    print(f"📥 拉取 Task {args.task_id} 标注\n")
    result = pull_and_import(
        task_id=args.task_id,
        skip_merge=args.no_merge,
        dry_run=args.dry_run,
    )

    if not result.get("ok"):
        print(f"\n❌ {result.get('error', '未知错误')}")
        return 1

    r = result
    print(f"\n{'─' * 44}")
    print(f"  回传批次:    {r.get('import_id', '')}")
    print(f"  Task ID:     {r.get('task_id')}")
    print(f"  标注图片:    {r.get('annotated_images', 0)} 张")
    if r.get("missing_images", 0):
        print(f"  未匹配图片:  {r['missing_images']} 张（源图片不在 for_labeling/images/）")
    print(f"  伪标签一致率: {r.get('consistency_rate', 0):.2%}  (门槛 {r.get('threshold', 0):.0%})  ← 差异监控，非质量评分")
    print(f"  差异条数:    {r.get('diff_count', 0)}")
    print(f"  结果:        {'✅ 达标' if r.get('passed') else '⚠️  未达标，已触发报警邮件'}")
    if r.get("merged_count", 0) > 0:
        print(f"  并入训练集:  {r['merged_count']} 个文件 → storage/training/")
    if r.get("batch_labeled_count", 0) > 0:
        print(f"  写回批次:    {r['batch_labeled_count']} 个文件 → archive/Batch_xxx/labeled/")
    if r.get("dry_run"):
        print("  [dry-run] 未写文件")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
