#!/usr/bin/env python3
# scripts/count_vehicles_track.py — 用 YOLO track 统计唯一车辆数（car+truck）
"""
用法:
  python scripts/count_vehicles_track.py storage/test/original/video1.mp4
  python scripts/count_vehicles_track.py storage/test/original/*.mp4
  python scripts/count_vehicles_track.py storage/test/original/ --mlflow  # 写入 MLflow

COCO 类别: 2=car, 7=truck
"""
import argparse
import glob
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)

# COCO class IDs for vehicles
CAR_CLASS = 2
TRUCK_CLASS = 7
VEHICLE_CLASSES = (CAR_CLASS, TRUCK_CLASS)


def count_unique_vehicles(video_path: str, model_path: str = "yolov8s.pt") -> int:
    """对单个视频跑 track，返回唯一车辆数（car+truck）。"""
    from ultralytics import YOLO
    model = YOLO(model_path)
    seen_ids = set()
    results = model.track(video_path, persist=True, verbose=False, classes=VEHICLE_CLASSES)
    for r in results:
        if r.boxes is None or r.boxes.id is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            if cls_id in VEHICLE_CLASSES:
                tid = int(box.id[0])
                seen_ids.add(tid)
    return len(seen_ids)


def main():
    parser = argparse.ArgumentParser(description="YOLO track 统计唯一车辆数")
    parser.add_argument("paths", nargs="+", help="视频路径或目录")
    parser.add_argument("--model", default="yolov8s.pt", help="YOLO 模型路径")
    parser.add_argument("--mlflow", action="store_true", help="写入 MLflow")
    parser.add_argument("--run-name", default="", help="MLflow run 名称")
    args = parser.parse_args()

    # 展开路径
    video_paths = []
    for p in args.paths:
        if os.path.isfile(p):
            video_paths.append(p)
        elif os.path.isdir(p):
            for ext in (".mp4", ".mov", ".avi", ".mkv"):
                video_paths.extend(glob.glob(os.path.join(p, "*" + ext)))
        else:
            video_paths.extend(glob.glob(p))
    video_paths = sorted(set(video_paths))

    if not video_paths:
        print("❌ 未找到视频文件", file=sys.stderr)
        return 1

    # 处理模型路径：优先用 models/ 下的，否则用 ultralytics 自带
    model_path = args.model
    if not os.path.isabs(model_path):
        local = os.path.join(BASE_DIR, "models", os.path.basename(model_path))
        model_path = local if os.path.isfile(local) else args.model

    total = 0
    for vp in video_paths:
        n = count_unique_vehicles(vp, model_path)
        print(f"  {os.path.basename(vp)}: {n} 辆")
        total += n

    print(f"\n✅ 唯一车辆数合计: {total} 辆")

    if args.mlflow:
        from config import config_loader
        cfg, _ = config_loader.get_config_and_paths(BASE_DIR)
        mf = cfg.get("mlflow") or {}
        if mf.get("enabled"):
            try:
                import mlflow
                uri = mf.get("tracking_uri")
                if uri:
                    mlflow.set_tracking_uri(uri)
                mlflow.set_experiment(mf.get("experiment_name", "datafactory"))
                run_name = args.run_name or f"video_{len(video_paths)}files"
                with mlflow.start_run(run_name=run_name):
                    mlflow.log_param("model", os.path.basename(model_path))
                    mlflow.log_param("videos", ",".join(os.path.basename(v) for v in video_paths))
                    mlflow.log_metric("unique_vehicle_count", total)
                print("✅ 已写入 MLflow")
            except Exception as e:
                print(f"⚠️ MLflow 写入失败: {e}", file=sys.stderr)
        else:
            print("⚠️ 未启用 MLflow，跳过", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
