# config/config_loader.py — 统一配置加载，路径解析为绝对路径
# 工业级：path decoupling，所有路径/目录名从配置读取，支持 env 覆盖
import os
import yaml
from typing import Any, Dict, List, Optional

_DEFAULT_BASE_DIR: Optional[str] = None

# 环境变量覆盖前缀（如 DATA_WAREHOUSE 覆盖 paths.data_warehouse）
_ENV_PREFIX = "DATAFACTORY_"


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

    # 解析 paths 为绝对路径；支持 env 覆盖（DATAFACTORY_RAW_VIDEO 等）
    paths = data.get("paths", {})
    _apply_env_overrides(paths)
    _path_resolve_skip = frozenset({"batch_subdirs", "batch_prefix", "batch_fails_suffix", "ensure_dirs", "dashboard_port"})
    for key in list(paths.keys()):
        if key in _path_resolve_skip:
            continue
        p = paths[key]
        if isinstance(p, str) and not os.path.isabs(p):
            paths[key] = os.path.join(base, p)
    # batch_subdirs 保持相对名（不解析为绝对路径），合并 YAML 与默认
    defaults = {"reports": "reports", "source": "source", "refinery": "refinery", "inspection": "inspection", "labeled": "labeled"}
    paths["batch_subdirs"] = {**defaults, **(paths.get("batch_subdirs") or {})}
    paths.setdefault("batch_prefix", "Batch_")
    paths.setdefault("batch_fails_suffix", "_Fails")
    paths.setdefault("ensure_dirs", [
        "raw_video", "data_warehouse", "rejected_material", "redundant_archives",
        "reports", "labeling_export", "labeled_return", "training", "golden",
        "test_source", "pending_review", "quarantine", "logs",
    ])
    data["paths"] = paths
    data["_base_dir"] = base
    data.setdefault("modality", "video")
    if "golden" not in data["paths"]:
        data["paths"]["golden"] = os.path.join(base, "storage", "golden")
    if "pending_review" not in data["paths"]:
        data["paths"]["pending_review"] = os.path.join(base, "storage", "pending_review")
    if "test_source" not in data["paths"]:
        data["paths"]["test_source"] = os.path.join(base, "storage", "test", "original")
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
    if mf.get("tracking_uri") is None:
        # 默认使用 db/mlflow.db，与 factory_admin.db 同目录，便于备份与部署
        mf["tracking_uri"] = "sqlite:///" + os.path.join(base, "db", "mlflow.db").replace("\\", "/")
    data.setdefault("production_setting", {})
    data["production_setting"].setdefault("human_review_flat", True)
    data["production_setting"].setdefault("approved_split_confidence_threshold", 0.6)
    data.setdefault("labeling_pool", {})
    data["labeling_pool"].setdefault("auto_update_after_batch", True)
    data.setdefault("retry", {"max_attempts": 3, "backoff_seconds": 1.0})
    ig = data.setdefault("ingest", {})
    ig.setdefault("pre_filter_enabled", True)
    ig.setdefault("dedup_at_ingest", True)
    ig.setdefault("decode_check_at_ingest", True)
    data.setdefault("timezone", "America/Toronto")
    data.setdefault("logging", {"max_bytes": 10 * 1024 * 1024, "backup_count": 5})
    ec = data.setdefault("email_setting", {})
    ec.setdefault("max_retries", 3)
    ec.setdefault("retry_delay_seconds", 5)
    return data


def _apply_env_overrides(paths: Dict[str, Any]) -> None:
    """环境变量覆盖 paths 中字符串值。DATAFACTORY_RAW_VIDEO -> paths.raw_video。"""
    for key in list(paths.keys()):
        if key.startswith("_") or key in ("batch_subdirs", "ensure_dirs", "batch_prefix", "batch_fails_suffix", "dashboard_port"):
            continue
        env_key = _ENV_PREFIX + key.upper().replace(".", "_")
        val = os.environ.get(env_key)
        if val is not None:
            paths[key] = val


def get_batch_paths(cfg: Dict[str, Any], batch_base: str) -> Dict[str, str]:
    """
    根据配置生成批次目录路径（path decoupling）。
    返回 qc_dir, source_archive_dir, fuel_dir, human_dir, mass_dir 等。
    """
    sub = cfg.get("paths", {}).get("batch_subdirs", {})
    return {
        "qc_dir": os.path.join(batch_base, sub.get("reports", "reports")),
        "source_archive_dir": os.path.join(batch_base, sub.get("source", "source")),
        "fuel_dir": os.path.join(batch_base, sub.get("refinery", "refinery")),
        "human_dir": os.path.join(batch_base, sub.get("inspection", "inspection")),
        "mass_dir": os.path.join(batch_base, sub.get("refinery", "refinery")),
    }


def get_batch_media_subdirs(cfg: Dict[str, Any]) -> tuple:
    """
    返回扫描媒体文件时需遍历的批次子目录名（含兼容旧版）。
    供 labeling_export.list_batch_media 使用。
    """
    sub = cfg.get("paths", {}).get("batch_subdirs", {})
    current = [sub.get("refinery", "refinery"), sub.get("inspection", "inspection"), sub.get("source", "source")]
    legacy = ("2_高置信_燃料", "3_待人工", "2_Mass_Production")
    return tuple(current) + legacy


def get_batch_prefix(cfg: Dict[str, Any]) -> str:
    """批次目录前缀，如 Batch_。"""
    return cfg.get("paths", {}).get("batch_prefix", "Batch_")


def get_batch_fails_suffix(cfg: Dict[str, Any]) -> str:
    """废片目录后缀，如 _Fails。"""
    return cfg.get("paths", {}).get("batch_fails_suffix", "_Fails")


def get_pending_queue_path(cfg: Dict[str, Any]) -> str:
    """待复核队列 JSON 文件路径。"""
    pending = cfg.get("paths", {}).get("pending_review", "")
    return os.path.join(pending, "queue.json")


def get_pending_thumbs_dir(cfg: Dict[str, Any]) -> str:
    """待复核队列缩略图目录。"""
    pending = cfg.get("paths", {}).get("pending_review", "")
    return os.path.join(pending, "thumbs")


def init_storage_structure(base_dir: Optional[str] = None) -> None:
    """
    启动时确保 storage/ 与 db/ 目录存在（兼容旧逻辑，无 config 时使用默认路径）。
    若 base_dir 未传则使用 get_base_dir()。
    """
    base = base_dir if base_dir is not None else get_base_dir()
    for sub in ("storage/raw", "storage/archive", "storage/rejected", "storage/redundant", "storage/test", "storage/test/original", "storage/reports", "storage/for_labeling", "storage/golden", "storage/pending_review", "storage/labeled_return", "storage/training", "db"):
        d = os.path.join(base, sub)
        os.makedirs(d, exist_ok=True)


def init_storage_from_config(cfg: Dict[str, Any]) -> None:
    """
    根据配置确保 paths 中目录存在（工业级：path decoupling）。
    应在 load_config 之后调用。
    """
    paths = cfg.get("paths", {})
    ensure_keys = paths.get("ensure_dirs", [])
    for key in ensure_keys:
        p = paths.get(key)
        if p and isinstance(p, str):
            os.makedirs(p, exist_ok=True)
    db_path = paths.get("db_file")
    if db_path:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)


def _default_config(base_dir: str) -> Dict[str, Any]:
    """无 YAML 时的默认配置（路径基于 base_dir）。"""
    return {
        "_base_dir": base_dir,
        "modality": "video",
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
            "pending_review": os.path.join(base_dir, "storage", "pending_review"),
            "quarantine": os.path.join(base_dir, "storage", "quarantine"),
            "logs": os.path.join(base_dir, "logs"),
            "db_file": os.path.join(base_dir, "db", "factory_admin.db"),
            "batch_prefix": "Batch_",
            "batch_fails_suffix": "_Fails",
            "batch_subdirs": {"reports": "reports", "source": "source", "refinery": "refinery", "inspection": "inspection", "labeled": "labeled"},
            "ensure_dirs": ["raw_video", "data_warehouse", "rejected_material", "redundant_archives", "reports", "labeling_export", "labeled_return", "training", "golden", "test_source", "pending_review", "quarantine", "logs"],
        },
        "ingest": {
            "batch_wait_seconds": 8,
            "video_extensions": [".mp4", ".mov", ".avi", ".mkv"],
            "pre_filter_enabled": True,
            "dedup_at_ingest": True,
            "decode_check_at_ingest": True,
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
        "mlflow": {
            "enabled": False,
            "experiment_name": "datafactory",
            "tracking_uri": "sqlite:///" + os.path.join(base_dir, "db", "mlflow.db").replace("\\", "/"),
        },
    }


def get_paths(cfg: Dict[str, Any]) -> Dict[str, str]:
    """从已加载配置中取出 paths（绝对路径）。"""
    return cfg.get("paths", {})


def validate_config(cfg: Dict[str, Any]) -> List[str]:
    """
    校验配置完整性与范围，返回错误列表（空表示通过）。
    P1：校验 min<max、gate∈[0,100]、双门槛一致性。
    """
    errs = []
    paths = cfg.get("paths", {})
    required = ["raw_video", "data_warehouse", "db_file", "rejected_material", "redundant_archives"]
    for k in required:
        if not paths.get(k):
            errs.append(f"paths.{k} 未配置")
    sub = paths.get("batch_subdirs", {})
    for k in ("reports", "source", "refinery", "inspection"):
        if not sub.get(k):
            errs.append(f"paths.batch_subdirs.{k} 未配置")

    # 质检阈值范围
    qt = cfg.get("quality_thresholds", {})
    min_br, max_br = qt.get("min_brightness"), qt.get("max_brightness")
    if min_br is not None and max_br is not None and float(min_br) >= float(max_br):
        errs.append("quality_thresholds: min_brightness 应小于 max_brightness")
    min_ct, max_ct = qt.get("min_contrast"), qt.get("max_contrast")
    if min_ct is not None and max_ct is not None and float(min_ct) >= float(max_ct):
        errs.append("quality_thresholds: min_contrast 应小于 max_contrast")

    # 准入线范围
    ps = cfg.get("production_setting", {})
    gate = ps.get("pass_rate_gate")
    if gate is not None and (float(gate) < 0 or float(gate) > 100):
        errs.append("production_setting.pass_rate_gate 应在 [0, 100]")

    # 双门槛一致性
    dh, dl = ps.get("dual_gate_high"), ps.get("dual_gate_low")
    if dh is not None and dl is not None and float(dh) <= float(dl):
        errs.append("production_setting: dual_gate_high 应大于 dual_gate_low")

    return errs


def get_quality_thresholds(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """从已加载配置中取出 quality_thresholds 与 production_setting 的合并（供质检使用）。"""
    out = {}
    out.update(cfg.get("quality_thresholds", {}))
    out.update(cfg.get("production_setting", {}))
    return out
