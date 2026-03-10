# config/config_loader.py — 统一配置加载，路径解析为绝对路径
# 工业级：path decoupling，所有路径/目录名从配置读取，支持 env 覆盖
import os
import threading
import yaml
from typing import Any, Dict, List, Optional, Tuple

from utils import file_tools

_DEFAULT_BASE_DIR: Optional[str] = None
_base_dir_lock = threading.Lock()  # 保护 _DEFAULT_BASE_DIR 并发读写
_probe_printed = False             # 确保启动打印只输出一次

# 环境变量覆盖前缀（如 DATA_WAREHOUSE 覆盖 paths.data_warehouse）
_ENV_PREFIX = "DATAFACTORY_"


def set_base_dir(path: str) -> None:
    """设置项目根目录，用于解析相对路径。线程安全。"""
    global _DEFAULT_BASE_DIR
    with _base_dir_lock:
        _DEFAULT_BASE_DIR = os.path.abspath(path)


def get_config_and_paths(base_dir: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    加载配置并解析常用路径。供 scripts 统一使用。
    返回 (cfg, paths)，paths 含 for_labeling、db_url 等绝对路径。

    db_url priority: DATABASE_URL env var (required for production).
    """
    if base_dir is None:
        base_dir = get_base_dir()
    set_base_dir(base_dir)
    cfg = load_config()
    p = cfg.get("paths", {})
    for_labeling = p.get("labeling_export", "")
    if not for_labeling:
        for_labeling = os.path.join(base_dir, "storage", "for_labeling")
    elif not os.path.isabs(for_labeling):
        for_labeling = os.path.join(base_dir, for_labeling)
    # Resolve db_url: DATABASE_URL env var → 回退到本地 SQLite
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        db_url = os.path.join(get_base_dir(), "storage", "factory_admin.db")
    # Also inject into cfg["paths"] so callers that use cfg directly get db_url too
    cfg["paths"]["db_url"] = db_url
    return cfg, {"for_labeling": for_labeling, "db_url": db_url}


def get_base_dir() -> str:
    """获取当前设定的项目根目录；未设置时使用调用方文件所在目录的上一级（项目根）。线程安全。"""
    with _base_dir_lock:
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
        "quarantine", "reports", "labeling_export", "labeled_return", "training",
        "train_runs", "golden", "test_source", "pending_review", "logs",
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
        mf["tracking_uri"] = os.environ.get("MLFLOW_BACKEND_URI", "")
    data.setdefault("production_setting", {})
    data["production_setting"].setdefault("human_review_flat", True)
    data["production_setting"].setdefault("approved_split_confidence_threshold", 0.6)
    data.setdefault("labeling_pool", {})
    data["labeling_pool"].setdefault("auto_update_after_batch", True)
    data.setdefault("retry", {"max_attempts": 3, "backoff_seconds": 1.0})
    ig = data.setdefault("ingest", {})
    ig.setdefault("image_mode", "auto")  # auto=根据 raw 目录自动判定，true/false=强制
    ig.setdefault("image_extensions", [".jpg", ".jpeg", ".png"])
    ig.setdefault("pre_filter_enabled", True)
    ig.setdefault("dedup_at_ingest", True)
    ig.setdefault("decode_check_at_ingest", True)
    data.setdefault("timezone", "America/Toronto")
    data.setdefault("logging", {"max_bytes": 10 * 1024 * 1024, "backup_count": 5})
    ec = data.setdefault("email_setting", {})
    ec.setdefault("max_retries", 3)
    ec.setdefault("retry_delay_seconds", 5)
    # Inject db_url from DATABASE_URL env var → 回退到本地 SQLite
    _db_url = os.environ.get("DATABASE_URL", "").strip()
    if not _db_url:
        _db_url = os.path.join(get_base_dir(), "storage", "factory_admin.db")
    data["paths"]["db_url"] = _db_url
    # P2-10: env override for quality_thresholds 和 production_setting
    # 放在所有 setdefault 之后，确保即使 YAML 未配置某节也能被 env 覆盖
    _apply_section_env_overrides(data.get("quality_thresholds", {}), "QT")
    _apply_section_env_overrides(data.get("production_setting", {}), "PS")

    # ── 硬件自动检测与 foundation_models 配置覆盖 ────────────────────────
    global _probe_printed
    fm = data.setdefault("foundation_models", {})
    if not fm.get("override", False):
        try:
            from utils.system_probe import detect_capabilities, auto_configure, print_system_info
            caps = detect_capabilities()
            auto_cfg = auto_configure(caps)
            # 只覆盖 auto_configure 返回的键，不清除 YAML 中其他手动项
            for k, v in auto_cfg.items():
                fm[k] = v
            if not _probe_printed:
                print_system_info(caps, fm)
                _probe_printed = True
        except Exception as e:
            logger.debug("system_probe 跳过: %s", e)

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


def _apply_section_env_overrides(section: Dict[str, Any], section_prefix: str) -> None:
    """
    对 quality_thresholds / production_setting 等扁平节应用 env 覆盖，自动保留原始类型。
    命名规则：DATAFACTORY_{SECTION_PREFIX}__{KEY}（双下划线分隔节与键）。
    示例：
      DATAFACTORY_QT__MIN_BRIGHTNESS=50   → quality_thresholds.min_brightness = 50.0
      DATAFACTORY_PS__PASS_RATE_GATE=90   → production_setting.pass_rate_gate  = 90.0
    """
    for key in list(section.keys()):
        orig = section[key]
        # 只覆盖标量（字符串 / 数字 / 布尔 / None）；嵌套 dict/list 跳过
        if isinstance(orig, (dict, list)):
            continue
        env_key = _ENV_PREFIX + section_prefix + "__" + key.upper().replace(".", "_")
        val = os.environ.get(env_key)
        if val is None:
            continue
        # 按原始类型强制转换
        if isinstance(orig, bool):
            section[key] = val.lower() in ("true", "1", "yes")
        elif isinstance(orig, int):
            try:
                section[key] = int(val)
            except ValueError:
                section[key] = val
        elif isinstance(orig, float):
            try:
                section[key] = float(val)
            except ValueError:
                section[key] = val
        else:
            section[key] = val


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


def _default_config(base_dir: str) -> Dict[str, Any]:
    """无 YAML 时的默认配置（路径基于 base_dir）。"""
    return {
        "_base_dir": base_dir,
        "modality": "video",
        "paths": {
            "raw_video": os.path.join(base_dir, "storage", "raw"),
            "data_warehouse": os.path.join(base_dir, "storage", "archive"),
            "rejected_material": os.path.join(base_dir, "storage", "rejected", "qc_fail"),
            "redundant_archives": os.path.join(base_dir, "storage", "rejected", "duplicate"),
            "quarantine": os.path.join(base_dir, "storage", "rejected", "quarantine"),
            "reports": os.path.join(base_dir, "storage", "reports"),
            "labeling_export": os.path.join(base_dir, "storage", "for_labeling"),
            "labeled_return": os.path.join(base_dir, "storage", "labeled_return"),
            "training": os.path.join(base_dir, "storage", "training", "dataset"),
            "train_runs": os.path.join(base_dir, "storage", "training", "runs"),
            "golden": os.path.join(base_dir, "storage", "golden"),
            "pending_review": os.path.join(base_dir, "storage", "pending_review"),
            "logs": os.path.join(base_dir, "logs"),
            "db_url": (os.environ.get("DATABASE_URL", "").strip()
                       or os.path.join(base_dir, "storage", "factory_admin.db")),
            "batch_prefix": "Batch_",
            "batch_fails_suffix": "_Fails",
            "batch_subdirs": {"reports": "reports", "source": "source", "refinery": "refinery", "inspection": "inspection", "labeled": "labeled"},
            "ensure_dirs": ["raw_video", "data_warehouse", "rejected_material", "redundant_archives", "quarantine", "reports", "labeling_export", "labeled_return", "training", "train_runs", "golden", "test_source", "pending_review", "logs"],
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
        "labeled_return": {"consistency_threshold": 0.95, "alert_via_email": True, "skip_empty_labels": True},
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
            "tracking_uri": os.environ.get("MLFLOW_BACKEND_URI", ""),
        },
    }


def validate_config(cfg: Dict[str, Any]) -> List[str]:
    """
    校验配置完整性与范围，返回错误列表（空表示通过）。
    P1：校验 min<max、gate∈[0,100]、双门槛一致性。
    """
    errs = []
    paths = cfg.get("paths", {})
    required = ["raw_video", "data_warehouse", "db_url", "rejected_material", "redundant_archives"]
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


def get_content_mode(cfg: Dict[str, Any]) -> str:
    """
    解析 content 通路：true/image → image，false/video → video，both → 混合，auto/未配置 → 根据 raw 目录自动判定。
    供 ingest、modality_handlers 等统一使用。
    """
    ingest_cfg = cfg.get("ingest", {})
    mode = ingest_cfg.get("image_mode", "auto")
    if mode is True or (isinstance(mode, str) and str(mode).lower() in ("true", "1")):
        return "image"
    if mode is False or (isinstance(mode, str) and str(mode).lower() in ("false", "0")):
        return "video"
    if isinstance(mode, str) and str(mode).lower() in ("both", "mixed"):
        return "both"
    # auto 或未配置：根据 raw 目录内容自动判定
    raw_dir = cfg.get("paths", {}).get("raw_video", "")
    img_exts = tuple(ingest_cfg.get("image_extensions", [".jpg", ".jpeg", ".png"]))
    vid_exts = tuple(ingest_cfg.get("video_extensions", [".mp4", ".mov", ".avi", ".mkv"]))
    return file_tools.detect_content_mode(raw_dir, img_exts, vid_exts)


def get_quality_thresholds(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """从已加载配置中取出 quality_thresholds 与 production_setting 的合并（供质检使用）。"""
    out = {}
    out.update(cfg.get("quality_thresholds", {}))
    out.update(cfg.get("production_setting", {}))
    return out
