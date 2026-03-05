#!/usr/bin/env python3
# scripts/mlflow/register_model.py — v3 将训练产出的 .pt 注册到 MLflow Model Registry
"""
将本地 .pt 模型注册到 MLflow Model Registry，便于 config 使用 models:/name/version。
用法:
  python scripts/mlflow/register_model.py path/to/model.pt --name vehicle_detector --version 1
  python scripts/mlflow/register_model.py path/to/model.pt --name vehicle_detector  # 自动递增版本
"""
import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def main():
    parser = argparse.ArgumentParser(description="注册 YOLO 模型到 MLflow Model Registry")
    parser.add_argument("model_path", help="本地 .pt 模型路径")
    parser.add_argument("--name", default="vehicle_detector", help="Registry 中的模型名称")
    parser.add_argument("--version", type=int, default=None, help="版本号，不指定则自动递增")
    parser.add_argument("--stage", choices=["Staging", "Production", "None"], default="None")
    args = parser.parse_args()

    path = os.path.abspath(args.model_path)
    if not os.path.isfile(path) or not path.endswith(".pt"):
        print("❌ 请指定有效的 .pt 模型路径")
        sys.exit(1)

    try:
        import mlflow
        from config import config_loader
        cfg, _ = config_loader.get_config_and_paths(BASE_DIR)
        tracking_uri = (cfg.get("mlflow") or {}).get("tracking_uri")
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(cfg.get("mlflow", {}).get("experiment_name", "datafactory"))

        with mlflow.start_run(run_name=f"register_{os.path.basename(path)}"):
            mlflow.log_artifact(local_path=path, artifact_path="model")
            run_id = mlflow.active_run().info.run_id
            model_uri = f"runs:/{run_id}/model"
            result = mlflow.register_model(model_uri=model_uri, name=args.name)
            version = result.version
            if args.stage != "None":
                client = mlflow.tracking.MlflowClient()
                client.transition_model_version_stage(args.name, str(version), args.stage)
            print(f"✅ 已注册: models:/{args.name}/{version}")
            if args.stage != "None":
                print(f"   阶段: {args.stage}")
    except ImportError:
        print("❌ 请安装 mlflow: pip install mlflow")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 注册失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
