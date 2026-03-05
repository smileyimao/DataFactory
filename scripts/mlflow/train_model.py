#!/usr/bin/env python3
# scripts/mlflow/train_model.py — 从 storage/training/ 训练 YOLO，注册到 MLflow Model Registry
"""
labeled_return 并入数据后，运行此脚本完成完整闭环：

  storage/training/ → YOLO 数据集 → ultralytics 训练 → best.pt
    → MLflow (params/metrics/artifact) → Model Registry → models:/name/version
    → DB model_train 血缘 (可用 query_lineage.py --train-id 查询)

用法:
  python scripts/mlflow/train_model.py                           # 用全部 training 数据
  python scripts/mlflow/train_model.py --epochs 100              # 指定轮数
  python scripts/mlflow/train_model.py --model yolov8m.pt        # 指定基础模型
  python scripts/mlflow/train_model.py --import-id Import_xxx    # 只用指定标注批次
  python scripts/mlflow/train_model.py --dry-run                 # 统计数据集，不实际训练

训练完成后更新 config/settings.yaml:
  vision:
    model_path: "models:/vehicle_detector/1"   # 使用 Registry URI
"""
import os
# Must be set before any torch/ultralytics import so MPS ops fall back to CPU
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import argparse
import json
import random
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}

# COCO-8 默认（与 export_for_cvat_native.py 保持一致）
_COCO8 = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck"]


# ─── 数据集准备 ──────────────────────────────────────────────────────────────

def _collect_samples(
    training_dir: str,
    import_id_filter: Optional[str] = None,
) -> Tuple[List[Tuple[str, str]], List[str]]:
    """
    扫描 training_dir/Import_xxx/ 收集有效 (image, label) 对。
    image 和 .txt 必须同时存在。
    返回 (samples, import_ids)。
    """
    samples: List[Tuple[str, str]] = []
    import_ids: List[str] = []

    if not os.path.isdir(training_dir):
        return samples, import_ids

    for subdir in sorted(os.listdir(training_dir)):
        if not subdir.startswith("Import_"):
            continue
        if import_id_filter and subdir != import_id_filter:
            continue
        subdir_path = os.path.join(training_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue

        found_in_batch = 0
        for name in sorted(os.listdir(subdir_path)):
            if os.path.splitext(name)[1].lower() not in IMAGE_EXT:
                continue
            img_path = os.path.join(subdir_path, name)
            txt_path = os.path.join(subdir_path, os.path.splitext(name)[0] + ".txt")
            if os.path.isfile(img_path) and os.path.isfile(txt_path):
                samples.append((img_path, txt_path))
                found_in_batch += 1

        if found_in_batch > 0:
            import_ids.append(subdir)

    return samples, import_ids


def _read_classes(for_labeling_dir: str, cli_classes: Optional[str]) -> List[str]:
    """
    类别名称解析优先级：
    1. CLI --classes 参数（逗号分隔）
    2. for_labeling/classes.txt（YOLO 标准格式）
    3. COCO-8 默认
    """
    if cli_classes:
        return [c.strip() for c in cli_classes.split(",") if c.strip()]

    classes_txt = os.path.join(for_labeling_dir, "classes.txt")
    if os.path.isfile(classes_txt):
        with open(classes_txt, encoding="utf-8") as f:
            names = [line.strip() for line in f if line.strip()]
        if names:
            return names

    return list(_COCO8)


def _detect_device() -> str:
    """自动选择：MPS（Apple Silicon）→ CUDA → CPU。"""
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "0"
    except ImportError:
        pass
    return "cpu"


def _build_yolo_dataset(
    samples: List[Tuple[str, str]],
    class_names: List[str],
    dataset_dir: str,
    val_ratio: float = 0.2,
    seed: int = 42,
) -> Tuple[str, int, int]:
    """
    在 dataset_dir/ 构建标准 YOLO 目录结构：
      images/{train,val}/  labels/{train,val}/  data.yaml
    返回 (data_yaml 路径, n_train, n_val)。
    """
    random.seed(seed)
    shuffled = list(samples)
    random.shuffle(shuffled)

    n_val = max(1, round(len(shuffled) * val_ratio))
    val_set = shuffled[:n_val]
    train_set = shuffled[n_val:]

    for split in ("train", "val"):
        os.makedirs(os.path.join(dataset_dir, "images", split), exist_ok=True)
        os.makedirs(os.path.join(dataset_dir, "labels", split), exist_ok=True)

    def _copy(split_samples: List[Tuple[str, str]], split: str) -> None:
        for img_path, txt_path in split_samples:
            name = os.path.basename(img_path)
            stem = os.path.splitext(name)[0]
            shutil.copy2(img_path, os.path.join(dataset_dir, "images", split, name))
            shutil.copy2(txt_path, os.path.join(dataset_dir, "labels", split, stem + ".txt"))

    _copy(train_set, "train")
    _copy(val_set, "val")

    data_yaml = os.path.join(dataset_dir, "data.yaml")
    with open(data_yaml, "w", encoding="utf-8") as f:
        f.write(f"path: {dataset_dir}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(class_names)}\n")
        f.write(f"names: {json.dumps(class_names, ensure_ascii=False)}\n")

    return data_yaml, len(train_set), len(val_set)


# ─── 指标提取 ────────────────────────────────────────────────────────────────

def _extract_metrics(results) -> Dict[str, float]:
    """从 ultralytics 训练结果提取验证指标，兼容不同字段名。"""
    rd = getattr(results, "results_dict", None) or {}
    def _get(*keys: str) -> float:
        for k in keys:
            v = rd.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return 0.0

    return {
        "map50":     _get("metrics/mAP50(B)",    "metrics/mAP50"),
        "map50_95":  _get("metrics/mAP50-95(B)", "metrics/mAP50-95"),
        "precision": _get("metrics/precision(B)", "metrics/precision"),
        "recall":    _get("metrics/recall(B)",    "metrics/recall"),
    }


# ─── MLflow ──────────────────────────────────────────────────────────────────

def _setup_mlflow(cfg: dict) -> None:
    import mlflow
    ml = cfg.get("mlflow") or {}
    uri = ml.get("tracking_uri") or os.environ.get("MLFLOW_BACKEND_URI", "")
    if not uri:
        raise RuntimeError("MLflow tracking_uri 未配置，请设置 MLFLOW_BACKEND_URI 或在 settings.yaml 中配置 mlflow.tracking_uri")
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(ml.get("experiment_name", "datafactory"))


def _log_and_register(
    run_name: str,
    params: dict,
    metrics: dict,
    best_pt: str,
    model_name: str,
    tags: dict,
) -> Tuple[str, str]:
    """
    MLflow: log params → log metrics → log tags → log model → register.
    用 pyfunc wrapper 包装 .pt，使 register_model 可接受标准 MLflow model 格式。
    返回 (mlflow_run_id, registry_uri)。
    """
    import mlflow
    import mlflow.pyfunc

    # 最小 pyfunc wrapper，让 MLflow 能把 .pt 注册为 Model
    class _YOLOModel(mlflow.pyfunc.PythonModel):
        def predict(self, context, model_input, params=None):
            return model_input

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        for k, v in tags.items():
            mlflow.set_tag(k, str(v))

        # 以 pyfunc 格式记录，.pt 作为附属 artifact
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=_YOLOModel(),
            artifacts={"yolo_weights": best_pt},
        )
        run_id = run.info.run_id

    result = mlflow.register_model(
        model_uri=f"runs:/{run_id}/model",
        name=model_name,
    )
    registry_uri = f"models:/{model_name}/{result.version}"
    return run_id, registry_uri


# ─── DB 血缘 ─────────────────────────────────────────────────────────────────

def _record_model_train(
    db_url: str,
    run_id: str,
    model_name: str,
    registry_uri: str,
    base_model: str,
    training_dir: str,
    import_ids: List[str],
    dataset_size: int,
    epochs: int,
    metrics: Dict[str, float],
    mlflow_run_id: str,
) -> bool:
    """写入 model_train 血缘，表不存在时自动创建。失败返回 False。"""
    from engines import db_connection
    try:
        conn = db_connection.connect(db_url)
        cur = conn.cursor()
        # Ensure table exists (init_db may not have been called for this run)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS model_train (
                run_id       TEXT PRIMARY KEY,
                model_name   TEXT,
                registry_uri TEXT,
                base_model   TEXT,
                training_dir TEXT,
                import_ids   TEXT,
                dataset_size INTEGER,
                epochs       INTEGER,
                map50        REAL,
                map50_95     REAL,
                precision    REAL,
                recall       REAL,
                mlflow_run_id TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        sql = db_connection.upsert_sql(
            "model_train",
            "run_id",
            [
                "run_id", "model_name", "registry_uri", "base_model", "training_dir",
                "import_ids", "dataset_size", "epochs", "map50", "map50_95",
                "precision", "recall", "mlflow_run_id",
            ],
            db_url,
        )
        cur.execute(sql, (
            run_id, model_name, registry_uri, base_model, training_dir,
            json.dumps(import_ids), dataset_size, epochs,
            metrics.get("map50", 0), metrics.get("map50_95", 0),
            metrics.get("precision", 0), metrics.get("recall", 0),
            mlflow_run_id,
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  ⚠️  DB 写入失败: {e}")
        return False


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 storage/training/ 训练 YOLO，注册到 MLflow Model Registry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python scripts/mlflow/train_model.py\n"
            "  python scripts/mlflow/train_model.py --epochs 100 --model yolov8m.pt\n"
            "  python scripts/mlflow/train_model.py --import-id Import_20260228_120000\n"
            "  python scripts/mlflow/train_model.py --dry-run\n"
        ),
    )
    parser.add_argument("--epochs",     type=int,   default=50,
                        help="训练轮数（默认 50）")
    parser.add_argument("--imgsz",      type=int,   default=640,
                        help="输入图像尺寸（默认 640）")
    parser.add_argument("--batch",      type=int,   default=8,
                        help="Batch size（默认 8，CPU 友好）")
    parser.add_argument("--model",      type=str,   default="",
                        help="基础模型路径或名称（默认读 config vision.model_path）")
    parser.add_argument("--name",       type=str,   default="vehicle_detector",
                        help="MLflow Model Registry 模型名称（默认 vehicle_detector）")
    parser.add_argument("--classes",    type=str,   default="",
                        help="类别名，逗号分隔（默认读 for_labeling/classes.txt 或 COCO-8）")
    parser.add_argument("--import-id",  type=str,   default="",
                        help="只使用指定 Import_xxx 批次的数据")
    parser.add_argument("--val-ratio",  type=float, default=0.2,
                        help="验证集比例（默认 0.2）")
    parser.add_argument("--dry-run",    action="store_true",
                        help="统计数据集后退出，不实际训练")
    args = parser.parse_args()

    from config import config_loader
    config_loader.set_base_dir(BASE_DIR)
    cfg, paths = config_loader.get_config_and_paths(BASE_DIR)

    # 路径
    cfg_paths     = cfg.get("paths", {})
    training_dir  = cfg_paths.get("training", os.path.join(BASE_DIR, "storage", "training"))
    if not os.path.isabs(training_dir):
        training_dir = os.path.join(BASE_DIR, training_dir)
    for_labeling_dir = paths.get("for_labeling", os.path.join(BASE_DIR, "storage", "for_labeling"))
    db_url = paths.get("db_url", "")

    # 基础模型
    base_model = args.model or (cfg.get("vision") or {}).get("model_path", "") or "yolov8s.pt"
    if not os.path.isabs(base_model) and not base_model.startswith("models:/"):
        candidate = os.path.join(BASE_DIR, base_model)
        if os.path.isfile(candidate):
            base_model = candidate

    # 类别
    class_names = _read_classes(for_labeling_dir, args.classes or None)

    # 收集样本
    print(f"\n  扫描: {training_dir}")
    samples, import_ids = _collect_samples(
        training_dir, args.import_id.strip() or None
    )

    # 统计摘要
    n_val   = max(1, round(len(samples) * args.val_ratio))
    n_train = max(0, len(samples) - n_val)

    print(f"  样本:      {len(samples)} 对（train {n_train} / val {n_val}）")
    print(f"  批次:      {import_ids or '（无）'}")
    print(f"  类别({len(class_names)}): {class_names}")
    print(f"  基础模型:  {base_model}")
    print(f"  设备:      {_detect_device()}")

    if not samples:
        print("\n❌ 没有找到训练数据（image + label 对）。")
        print("   请先完成：main.py --auto-cvat → CVAT 标注 → cvat_pull_annotations.py")
        return 1

    if len(samples) < 10:
        print(f"\n⚠️  样本数量较少（{len(samples)}），建议积累更多标注后再训练")

    if args.dry_run:
        print("\n  [dry-run] 未实际训练。")
        return 0

    # ── 构建运行目录 ────────────────────────────────────────────────────────
    run_ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id  = f"TrainRun_{run_ts}"
    run_dir = os.path.join(BASE_DIR, "storage", "train_runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    print(f"\n  Run ID:    {run_id}")
    print(f"  Run 目录:  {run_dir}")

    # ── 构建 YOLO 数据集 ────────────────────────────────────────────────────
    print(f"\n  构建 YOLO 数据集...")
    dataset_dir = os.path.join(run_dir, "dataset")
    data_yaml, n_train, n_val = _build_yolo_dataset(
        samples, class_names, dataset_dir, val_ratio=args.val_ratio
    )
    print(f"    train: {n_train}  val: {n_val}")
    print(f"    data.yaml: {data_yaml}")

    # ── 训练 ────────────────────────────────────────────────────────────────
    print(f"\n  启动训练 (epochs={args.epochs}, imgsz={args.imgsz}, batch={args.batch})...")
    t0 = time.time()

    try:
        from ultralytics import YOLO
        device = _detect_device()

        # 禁用 ultralytics 自动 MLflow（我们自己记录）
        try:
            from ultralytics import settings as ult_settings
            ult_settings.update({"mlflow": False})
        except Exception:
            pass

        model = YOLO(base_model)
        results = model.train(
            data=data_yaml,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=device,
            project=run_dir,
            name="train",
            exist_ok=True,
        )
    except KeyboardInterrupt:
        print("\n⚠️  训练被中断")
        return 1
    except Exception as e:
        print(f"\n❌ 训练失败: {e}")
        return 1

    elapsed = time.time() - t0

    # 找 best.pt
    best_pt = Path(results.save_dir) / "weights" / "best.pt"
    if not best_pt.is_file():
        print(f"\n❌ 未找到 best.pt，save_dir={results.save_dir}")
        return 1

    # ── 指标 ────────────────────────────────────────────────────────────────
    metrics = _extract_metrics(results)
    print(f"\n  训练完成 ({elapsed / 60:.1f} min)")
    print(f"  mAP50:     {metrics['map50']:.4f}")
    print(f"  mAP50-95:  {metrics['map50_95']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")

    # ── MLflow 记录 + 注册 ──────────────────────────────────────────────────
    mlflow_run_id = ""
    registry_uri  = ""
    try:
        import mlflow  # noqa: F401 — confirm available
        _setup_mlflow(cfg)

        params = {
            "base_model": os.path.basename(str(base_model)),
            "epochs":     args.epochs,
            "imgsz":      args.imgsz,
            "batch":      args.batch,
            "device":     _detect_device(),
            "nc":         len(class_names),
            "classes":    ",".join(class_names),
            "n_train":    n_train,
            "n_val":      n_val,
            "val_ratio":  args.val_ratio,
        }
        tags = {
            "training.run_id":    run_id,
            "training.dir":       training_dir,
            "training.import_ids": ",".join(import_ids),
        }
        print(f"\n  MLflow 记录 + 注册模型 '{args.name}'...")
        mlflow_run_id, registry_uri = _log_and_register(
            run_name=run_id,
            params=params,
            metrics={k: round(v, 6) for k, v in metrics.items()
                     } | {"elapsed_min": round(elapsed / 60, 2)},
            best_pt=str(best_pt),
            model_name=args.name,
            tags=tags,
        )
        print(f"    MLflow run: {mlflow_run_id}")
        print(f"    Registry:   {registry_uri}")

    except ImportError:
        print("  ⚠️  mlflow 未安装，跳过注册（pip install mlflow）")
    except Exception as e:
        print(f"  ⚠️  MLflow 记录失败: {e}")

    # ── DB 血缘 ─────────────────────────────────────────────────────────────
    if db_url:
        ok = _record_model_train(
            db_url=db_url,
            run_id=run_id,
            model_name=args.name,
            registry_uri=registry_uri,
            base_model=os.path.basename(str(base_model)),
            training_dir=training_dir,
            import_ids=import_ids,
            dataset_size=len(samples),
            epochs=args.epochs,
            metrics=metrics,
            mlflow_run_id=mlflow_run_id,
        )
        if ok:
            print(f"  DB 血缘已写入（run_id={run_id}）")

    # ── 完成汇报 ────────────────────────────────────────────────────────────
    print(f"\n{'─' * 44}")
    print(f"  Run ID:    {run_id}")
    print(f"  best.pt:   {best_pt}")
    if registry_uri:
        print(f"\n  要将新模型接入 pipeline，更新 config/settings.yaml:")
        print(f"    vision:")
        print(f"      model_path: \"{registry_uri}\"")
        print(f"\n  查询完整血缘:")
        print(f"    python scripts/query_lineage.py --train-id {run_id}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
