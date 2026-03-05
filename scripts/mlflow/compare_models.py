#!/usr/bin/env python3
# scripts/mlflow/compare_models.py — 新旧模型对比：在相同数据上跑两个模型，比较检测结果，写入 MLflow/DB
"""
用法:
  python scripts/mlflow/compare_models.py --new yolov8s.pt --baseline yolov8n.pt --data storage/for_labeling/images
  python scripts/mlflow/compare_models.py --new path/to/new.pt --baseline config  # baseline 用 config 中的 vision.model_path
"""
import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def _load_model(path: str):
    """加载 YOLO 模型。"""
    from ultralytics import YOLO
    return YOLO(path)


def _run_on_images(model, image_paths: list, conf: float = 0.25) -> dict:
    """对图片列表跑推理，返回 {path: n_detections} 及每图检测框列表。"""
    if not image_paths:
        return {"by_path": {}, "total_det": 0}
    import cv2
    params = {"conf": conf, "verbose": False}
    by_path = {}
    total = 0
    for p in image_paths:
        if not os.path.isfile(p):
            continue
        img = cv2.imread(p)
        if img is None:
            continue
        try:
            results = model.predict(img, **params)
        except Exception:
            by_path[p] = {"n": 0, "boxes": []}
            continue
        r = results[0] if results else None
        n = len(r.boxes) if (r and hasattr(r, "boxes") and r.boxes is not None) else 0
        boxes = []
        if r and hasattr(r, "boxes") and r.boxes is not None:
            try:
                xyxy = r.boxes.xyxy.cpu().numpy()
                cls = r.boxes.cls.cpu().numpy()
                confs = r.boxes.conf.cpu().numpy()
                for i in range(len(cls)):
                    boxes.append({
                        "class_id": int(cls[i]),
                        "conf": float(confs[i]),
                        "xyxy": xyxy[i].tolist(),
                    })
            except Exception:
                pass
        by_path[p] = {"n": n, "boxes": boxes}
        total += n
    return {"by_path": by_path, "total_det": total}


def _compute_iou(box1: list, box2: list) -> float:
    """计算两个 xyxy 框的 IoU。"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def _match_boxes(boxes_a: list, boxes_b: list, iou_thresh: float = 0.5) -> int:
    """按 IoU 匹配两边的框，返回匹配数。"""
    used_b = set()
    matched = 0
    for ba in boxes_a:
        best_iou, best_j = 0.0, -1
        for j, bb in enumerate(boxes_b):
            if j in used_b:
                continue
            if ba.get("class_id") != bb.get("class_id"):
                continue
            iou = _compute_iou(ba.get("xyxy", []), bb.get("xyxy", []))
            if iou >= iou_thresh and iou > best_iou:
                best_iou, best_j = iou, j
        if best_j >= 0:
            used_b.add(best_j)
            matched += 1
    return matched


def compare_models(
    new_model_path: str,
    baseline_model_path: str,
    data_dir: str,
    conf: float = 0.25,
    iou_thresh: float = 0.5,
) -> dict:
    """对比新旧模型，返回指标。"""
    image_paths = []
    for name in sorted(os.listdir(data_dir)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXT:
            continue
        image_paths.append(os.path.join(data_dir, name))
    if not image_paths:
        return {"error": "未找到图片", "n_images": 0}

    new_model = _load_model(new_model_path)
    baseline_model = _load_model(baseline_model_path)

    new_res = _run_on_images(new_model, image_paths, conf=conf)
    base_res = _run_on_images(baseline_model, image_paths, conf=conf)

    n_images = len(image_paths)
    total_new = new_res["total_det"]
    total_base = base_res["total_det"]
    matched = 0
    for p in image_paths:
        na = new_res["by_path"].get(p, {}).get("boxes", [])
        nb = base_res["by_path"].get(p, {}).get("boxes", [])
        matched += _match_boxes(na, nb, iou_thresh)

    # 模型间一致率：2*matched / (n_new + n_base)，衡量两模型检测框重叠程度
    n_new = sum(r["n"] for r in new_res["by_path"].values())
    n_base = sum(r["n"] for r in base_res["by_path"].values())
    denom = n_new + n_base
    consistency = (2 * matched / denom) if denom > 0 else 1.0

    return {
        "n_images": n_images,
        "n_detections_new": total_new,
        "n_detections_baseline": total_base,
        "detection_diff": total_new - total_base,
        "matched_boxes": matched,
        "consistency_rate": round(consistency, 4),
        "new_model_path": new_model_path,
        "baseline_model_path": baseline_model_path,
        "data_dir": data_dir,
    }


def main():
    parser = argparse.ArgumentParser(description="新旧模型对比：在相同数据上跑两个模型，比较检测结果。")
    parser.add_argument("--new", required=True, help="新模型路径 (.pt)")
    parser.add_argument("--baseline", required=True, help="基线模型路径，或 'config' 使用 config vision.model_path")
    parser.add_argument("--data", default=None, help="图片目录，默认 storage/for_labeling/images")
    parser.add_argument("--conf", type=float, default=0.25, help="置信度阈值")
    parser.add_argument("--iou", type=float, default=0.5, help="IoU 匹配阈值")
    parser.add_argument("--no-mlflow", action="store_true", help="不写入 MLflow")
    args = parser.parse_args()

    from config import config_loader
    cfg, paths = config_loader.get_config_and_paths(BASE_DIR)

    baseline_path = args.baseline
    if baseline_path.lower() == "config":
        baseline_path = (cfg.get("vision") or {}).get("model_path", "")
        if not baseline_path:
            print("❌ config 中 vision.model_path 未配置")
            sys.exit(1)

    data_dir = args.data
    if not data_dir:
        fl = paths.get("for_labeling", "")
        if fl:
            data_dir = os.path.join(fl, "images")
    if not data_dir or not os.path.isdir(data_dir):
        print(f"❌ 数据目录不存在: {data_dir}")
        sys.exit(1)

    metrics = compare_models(
        args.new, baseline_path, data_dir,
        conf=args.conf, iou_thresh=args.iou,
    )
    if metrics.get("error"):
        print(f"❌ {metrics['error']}")
        sys.exit(1)

    print("📊 模型对比结果:")
    for k, v in metrics.items():
        print(f"   {k}: {v}")

    if not args.no_mlflow and cfg.get("mlflow", {}).get("enabled"):
        try:
            import mlflow
            mf = cfg.get("mlflow", {})
            if mf.get("tracking_uri"):
                mlflow.set_tracking_uri(mf["tracking_uri"])
            mlflow.set_experiment(mf.get("experiment_name", "datafactory"))
            with mlflow.start_run(run_name="model_compare"):
                mlflow.log_params({
                    "new_model": metrics["new_model_path"],
                    "baseline_model": metrics["baseline_model_path"],
                    "data_dir": metrics["data_dir"],
                })
                mlflow.log_metrics({
                    "n_images": metrics["n_images"],
                    "n_detections_new": metrics["n_detections_new"],
                    "n_detections_baseline": metrics["n_detections_baseline"],
                    "detection_diff": metrics["detection_diff"],
                    "matched_boxes": metrics["matched_boxes"],
                    "consistency_rate": metrics["consistency_rate"],
                })
            print("✅ 已写入 MLflow")
        except Exception as e:
            print(f"⚠️ MLflow 写入失败: {e}")

    db_url = paths.get("db_url", "")
    if db_url:
        try:
            from engines import db_connection
            conn = db_connection.connect(db_url)
            cur = conn.cursor()
            ph = db_connection.ph(db_url)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS model_comparison (
                    id SERIAL PRIMARY KEY,
                    new_model TEXT,
                    baseline_model TEXT,
                    data_dir TEXT,
                    n_images INTEGER,
                    n_det_new INTEGER,
                    n_det_baseline INTEGER,
                    consistency_rate REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute(
                f"INSERT INTO model_comparison (new_model, baseline_model, data_dir, n_images, n_det_new, n_det_baseline, consistency_rate) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph})",
                (
                    metrics["new_model_path"],
                    metrics["baseline_model_path"],
                    metrics["data_dir"],
                    metrics["n_images"],
                    metrics["n_detections_new"],
                    metrics["n_detections_baseline"],
                    metrics["consistency_rate"],
                ),
            )
            conn.commit()
            conn.close()
            print("✅ 已写入 DB model_comparison")
        except Exception as e:
            print(f"⚠️ DB 写入失败: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
