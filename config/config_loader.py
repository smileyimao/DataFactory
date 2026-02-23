# config/config_loader.py — 统一配置加载，路径解析为绝对路径
import os
import yaml
from typing import Any, Dict, Optional

_DEFAULT_BASE_DIR: Optional[str] = None


def set_base_dir(path: str) -> None:
    """设置项目根目录，用于解析相对路径。"""
    global _DEFAULT_BASE_DIR
    _DEFAULT_BASE_DIR = os.path.abspath(path)


def get_base_dir() -> str:
    """获取当前设定的项目根目录；未设置时使用调用方文件所在目录的上一级（项目根）。"""
    if _DEFAULT_BASE_DIR:
        return _DEFAULT_BASE_DIR
    # 默认：config/ 的父目录为项目根
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载 settings.yaml，将 paths 中的相对路径解析为绝对路径（基于 get_base_dir()）。
    若 config_path 未传，则使用 get_base_dir()/config/settings.yaml。
    返回合并后的扁平配置（含 paths、ingest、quality_thresholds、production_setting、review、email_setting）。
    """
    base = get_base_dir()
    if config_path is None:
        config_path = os.path.join(base, "config", "settings.yaml")
    if not os.path.exists(config_path):
        return _default_config(base)

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # 解析 paths 为绝对路径
    paths = data.get("paths", {})
    for key in list(paths.keys()):
        p = paths[key]
        if isinstance(p, str) and not os.path.isabs(p):
            paths[key] = os.path.join(base, p)
    data["paths"] = paths
    data["_base_dir"] = base
    if "golden" not in data["paths"]:
        data["paths"]["golden"] = os.path.join(base, "storage", "golden")
    # 开机自检与滚动清零、黄金库默认值（YAML 可覆盖）
    if "startup_self_check" not in data:
        data["startup_self_check"] = True
    if "startup_golden_run" not in data:
        data["startup_golden_run"] = False
    data.setdefault("rolling_cleanup", {
        "logs_retention_days": 30,
        "reports_retention_days": 30,
        "archive_retention_days": 0,
    })
    rc = data["rolling_cleanup"]
    rc.setdefault("logs_retention_days", 30)
    rc.setdefault("reports_retention_days", 30)
    rc.setdefault("archive_retention_days", 0)
    # v2.0 vision：推理参数未配置时使用工业默认值（不在 vision_detector 中硬编码）
    data.setdefault("vision", {})
    v = data["vision"]
    v.setdefault("enabled", False)
    v.setdefault("model_path", "")
    v.setdefault("sample_seconds", 10)
    v.setdefault("use_i_frame_only", False)
    v.setdefault("motion_threshold", 0.0)
    v.setdefault("cascade_light_model_path", "")
    v.setdefault("cascade_light_conf", 0.2)
    v.setdefault("conf", 0.25)
    v.setdefault("iou", 0.45)
    v.setdefault("classes", None)
    v.setdefault("device", None)
    v.setdefault("max_det", 300)
    v.setdefault("imgsz", 640)
    v.setdefault("half", False)
    v.setdefault("verbose", False)
    # M2 版本映射
    data.setdefault("version_mapping", {})
    vm = data["version_mapping"]
    vm.setdefault("algorithm_version", "rules_v1")
    vm.setdefault("vision_model_version", "")
    data.setdefault("mlflow", {})
    mf = data["mlflow"]
    mf.setdefault("enabled", False)
    mf.setdefault("experiment_name", "datafactory")
    mf.setdefault("tracking_uri", None)
    data.setdefault("production_setting", {})
    data["production_setting"].setdefault("human_review_flat", True)
    data.setdefault("labeling_pool", {})
    data["labeling_pool"].setdefault("auto_update_after_batch", True)
    return data


def init_storage_structure(base_dir: Optional[str] = None) -> None:
    """
    启动时确保 storage/ 与 db/ 目录存在，避免运行时路径缺失。
    若 base_dir 未传则使用 get_base_dir()。
    """
    base = base_dir if base_dir is not None else get_base_dir()
    for sub in ("storage/raw", "storage/archive", "storage/rejected", "storage/redundant", "storage/test", "storage/reports", "storage/for_labeling", "storage/golden", "storage/pending_review", "storage/labeled_return", "storage/training", "db"):
        d = os.path.join(base, sub)
        os.makedirs(d, exist_ok=True)


def _default_config(base_dir: str) -> Dict[str, Any]:
    """无 YAML 时的默认配置（路径基于 base_dir）。"""
    return {
        "_base_dir": base_dir,
        "paths": {
            "raw_video": os.path.join(base_dir, "storage", "raw"),
            "data_warehouse": os.path.join(base_dir, "storage", "archive"),
            "rejected_material": os.path.join(base_dir, "storage", "rejected"),
            "redundant_archives": os.path.join(base_dir, "storage", "redundant"),
            "reports": os.path.join(base_dir, "storage", "reports"),
            "labeling_export": os.path.join(base_dir, "storage", "for_labeling"),
            "labeled_return": os.path.join(base_dir, "storage", "labeled_return"),
            "training": os.path.join(base_dir, "storage", "training"),
            "golden": os.path.join(base_dir, "storage", "golden"),
            "logs": os.path.join(base_dir, "logs"),
            "db_file": os.path.join(base_dir, "db", "factory_admin.db"),
        },
        "ingest": {
            "batch_wait_seconds": 8,
            "video_extensions": [".mp4", ".mov", ".avi", ".mkv"],
        },
        "quality_thresholds": {
            "min_brightness": 55.0,
            "max_brightness": 225.0,
            "min_blur_score": 20.0,
            "max_jitter": 35.0,
            "min_contrast": 15.0,
            "max_contrast": 100.0,
        },
        "production_setting": {
            "qc_sample_seconds": 10,
            "pass_rate_gate": 85.0,
            "dual_gate_high": None,
            "dual_gate_low": None,
            "save_normal": True,
            "save_warning": True,
            "save_only_screened": False,
            "confidence_tiered_output": True,
            "human_review_flat": True,
        },
        "review": {"mode": "terminal", "timeout_seconds": 600, "valid_inputs": ["y", "n", "all", "none"]},
        "labeled_return": {"consistency_threshold": 0.95, "alert_via_email": True},
        "email_setting": {},
        "startup_self_check": True,
        "rolling_cleanup": {
            "logs_retention_days": 30,
            "reports_retention_days": 30,
            "archive_retention_days": 0,
        },
        "vision": {
            "enabled": False,
            "model_path": "",
            "sample_seconds": 10,
            "conf": 0.25,
            "iou": 0.45,
            "classes": None,
            "device": None,
            "max_det": 300,
            "imgsz": 640,
            "half": False,
            "verbose": False,
        },
        "version_mapping": {
            "algorithm_version": "rules_v1",
            "vision_model_version": "",
        },
        "mlflow": {"enabled": False, "experiment_name": "datafactory", "tracking_uri": None},
    }


def get_paths(cfg: Dict[str, Any]) -> Dict[str, str]:
    """从已加载配置中取出 paths（绝对路径）。"""
    return cfg.get("paths", {})


def get_quality_thresholds(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """从已加载配置中取出 quality_thresholds 与 production_setting 的合并（供质检使用）。"""
    out = {}
    out.update(cfg.get("quality_thresholds", {}))
    out.update(cfg.get("production_setting", {}))
    return out
