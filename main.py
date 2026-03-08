# main.py — 工厂总开关：单次运行或 Guard 模式
import os
import sys
import argparse

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 敏感信息从 .env 加载
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 避免 matplotlib 弹窗
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp")


def _collect_batch_stats(archive_dir: str, batch_prefix: str = "Batch_") -> dict:
    """从最新批次统计：总帧数、有伪标签数、refinery、inspection。"""
    out = {"total": 0, "with_pseudo": 0, "refinery": 0, "inspection": 0, "batch_id": ""}
    if not os.path.isdir(archive_dir):
        return out
    batch_dirs = sorted(
        [d for d in os.listdir(archive_dir)
         if os.path.isdir(os.path.join(archive_dir, d)) and d.startswith(batch_prefix)],
        reverse=True,
    )
    if not batch_dirs:
        return out
    out["batch_id"] = batch_dirs[0]
    batch_path = os.path.join(archive_dir, batch_dirs[0])
    for sub in ("refinery", "inspection"):
        sub_path = os.path.join(batch_path, sub)
        if not os.path.isdir(sub_path):
            continue
        for root, _, files in os.walk(sub_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in IMAGE_EXT:
                    out["total"] += 1
                    if sub == "refinery":
                        out["refinery"] += 1
                    else:
                        out["inspection"] += 1
                    base = os.path.splitext(f)[0]
                    txt_path = os.path.join(root, base + ".txt")
                    if os.path.isfile(txt_path):
                        out["with_pseudo"] += 1
    return out


_VERSION = "3.9"

_W = 56  # fixed-width ruler

_DASHBOARDS = {
    "Review":   ("http://127.0.0.1:8765", "python -m dashboard.app"),
    "Sentinel": ("http://127.0.0.1:8766", "python dashboard/sentinel.py --source archive"),
    "HQ":       ("http://127.0.0.1:8767", "python dashboard/hq.py"),
}


def _print_banner() -> None:
    print(f"\n{'━' * _W}")
    print(f"  DataFactory v{_VERSION}")
    print(f"  Industrial Video QC Pipeline")
    print(f"{'━' * _W}")


def _print_dashboards() -> None:
    cvat = os.environ.get("CVAT_LOCAL_URL", "")
    print(f"\n{'─' * _W}")
    print("  Dashboards")
    print(f"{'─' * _W}")
    for name, (url, cmd) in _DASHBOARDS.items():
        print(f"  {name:<10} {url:<28} {cmd}")
    if cvat:
        print(f"  {'CVAT':<10} {cvat}")
    print(f"{'─' * _W}\n")


def _print_pipeline_report(stats: dict, input_name: str, cvat_url: str = "", elapsed_sec: float = 0) -> None:
    total = stats.get("total", 0) or 1
    with_pseudo = stats.get("with_pseudo", 0)
    refinery = stats.get("refinery", 0)
    inspection = stats.get("inspection", 0)
    pct = int(with_pseudo / total * 100) if total else 0

    mins, secs = divmod(int(elapsed_sec), 60)
    time_str = f"{mins}m {secs}s" if mins else f"{secs}s"

    print(f"\n{'━' * _W}")
    print(f"  Batch complete — {time_str}")
    print(f"{'─' * _W}")
    print(f"  Input    {input_name}")
    print(f"  Frames   {total} total | {refinery} refinery | {inspection} inspection")
    print(f"  Pseudo   {with_pseudo} ({pct}% auto-labeled)")
    if cvat_url:
        print(f"  CVAT     {cvat_url}")
    print(f"{'━' * _W}")
    _print_dashboards()



def main():
    import time as _time
    from config import config_loader
    from utils import logging as log_config
    from core import pipeline

    parser = argparse.ArgumentParser(description="DataFactory — Industrial Video QC Pipeline")
    parser.add_argument("--gate", type=float, default=None, help="准入阈值 (%%)")
    parser.add_argument("--guard", action="store_true", help="Guard 模式：持续监控 raw_video 并自动送厂")
    parser.add_argument("--input", type=str, default="", help="指定单个视频路径")
    parser.add_argument("--auto-cvat", action="store_true", help="自动上传标注到 CVAT")
    parser.add_argument("--no-cvat", action="store_true", help="跳过 CVAT 上传")
    args = parser.parse_args()

    _print_banner()

    config_loader.set_base_dir(BASE_DIR)
    cfg = config_loader.load_config()
    log_config.setup_logging(BASE_DIR, cfg, console=True)
    config_loader.init_storage_from_config(cfg)

    from utils import startup
    if cfg.get("startup_self_check", True):
        if not startup.run_startup_self_check(cfg):
            sys.exit(1)
    startup.run_rolling_cleanup(cfg)
    startup.run_disk_check(cfg)
    if cfg.get("startup_golden_run"):
        if not startup.run_golden_run(cfg):
            sys.exit(1)

    db_url = cfg.get("paths", {}).get("db_url")
    if not db_url:
        print("  [ERROR] DATABASE_URL 未设置，请在 .env 中配置\n")
        sys.exit(1)
    from db import db_tools
    if not db_tools.init_db(db_url):
        print("  [ERROR] 数据库初始化失败，请检查 PostgreSQL 是否运行\n")
        sys.exit(1)

    video_paths = None
    input_name = "storage/raw"
    if args.input:
        p = os.path.abspath(os.path.expanduser(args.input))
        if not os.path.isfile(p):
            print(f"  [ERROR] 文件不存在: {args.input}\n")
            sys.exit(1)
        video_paths = [p]
        input_name = os.path.basename(p)

    if args.guard:
        print(f"  Mode     Guard (watching storage/raw)\n")
        _print_dashboards()
        from core import guard
        guard.run_guard()
    else:
        print(f"  Mode     Single-run\n")
        t0 = _time.monotonic()
        pipeline.run_smart_factory(gate_val=args.gate, video_paths=video_paths)
        elapsed = _time.monotonic() - t0

        archive = cfg.get("paths", {}).get("data_warehouse", "")
        if not archive:
            archive = os.path.join(BASE_DIR, "storage", "archive")
        if not os.path.isabs(archive):
            archive = os.path.join(BASE_DIR, archive)
        batch_prefix = config_loader.get_batch_prefix(cfg)
        stats = _collect_batch_stats(archive, batch_prefix)

        cvat_url = ""
        cvat_configured = bool(os.environ.get("CVAT_LOCAL_URL"))
        should_upload = (args.auto_cvat or cvat_configured) and not args.no_cvat
        if should_upload and stats.get("total", 0) > 0:
            from labeling import annotation_upload
            cvat_url = annotation_upload.upload(cfg, task_name=stats.get("batch_id", "DataFactory"))

        _print_pipeline_report(stats, input_name, cvat_url, elapsed)


if __name__ == "__main__":
    main()
