# Models

YOLO 及级联检测模型存放目录。路径在 `config/settings.yaml` 的 `vision.model_path`、`vision.cascade_light_model_path` 中配置。

**级联检测**：cascade 用 nano（yolov8n）初筛，main 用 small（yolov8s）精检，空画面不跑主模型。

**下载**：`python scripts/mlflow/download_models.py` 可下载 yolov8n、yolov8s 到此目录。
