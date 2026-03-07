#!/usr/bin/env python3
# tools.py — 运维 / 调试工具集（非 pipeline 入口）
# 用法：python tools.py --<命令> [选项]
#   --usage-report [--days N]     功能使用报告
#   --usage-reset  [FEATURE|all]  重置使用计数
#   --test         [--gate N]     全链路测试（临时环境，不污染真实数据）
#   --probe                       硬件检测与自动配置摘要
import argparse
import copy
import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

VIDEO_EXT = (".mov", ".mp4", ".avi", ".mkv")


# ─────────────────────────── --usage-report ────────────────────────────────

def cmd_usage_report(days: int) -> None:
    from utils.usage_tracker import report
    report(days=days)


# ─────────────────────────── --usage-reset ─────────────────────────────────

def cmd_usage_reset(target: str) -> None:
    from utils.usage_tracker import reset
    name = None if target == "all" else target
    reset(name)


# ─────────────────────────── --probe ───────────────────────────────────────

def cmd_probe() -> None:
    from utils.system_probe import detect_capabilities, auto_configure, print_system_info
    caps = detect_capabilities()
    config = auto_configure(caps)
    print_system_info(caps, config)


# ─────────────────────────── --test ────────────────────────────────────────

def run_full_pipeline_test(gate_val=None) -> None:
    """
    全链路测试核心逻辑：临时环境跑 pipeline，不污染真实 storage/DB。
    可被 pytest 直接 import 调用（不含 sys.exit），也被 cmd_test 包裹用于 CLI。
    失败时抛 RuntimeError。
    """
    from config import config_loader
    from utils import logging as log_config
    from core import pipeline
    from tests.helpers import seed_test

    config_loader.set_base_dir(BASE_DIR)
    cfg = config_loader.load_config()
    paths = cfg.get("paths", {})
    test_source = paths.get("test_source") or os.path.join(BASE_DIR, "storage", "test", "original")
    test_source = os.path.abspath(test_source)

    if not os.path.isdir(test_source):
        raise RuntimeError(f"测试源目录不存在: {test_source}")
    video_count = sum(
        1 for n in os.listdir(test_source)
        if os.path.isfile(os.path.join(test_source, n))
        and any(n.lower().endswith(ext) for ext in VIDEO_EXT)
    )
    if video_count == 0:
        raise RuntimeError("测试源无视频，请先在 storage/test/original/ 放入测试视频。")

    with tempfile.TemporaryDirectory(prefix="datafactory_test_") as tmp:
        temp_raw          = os.path.join(tmp, "raw")
        temp_archive      = os.path.join(tmp, "archive")
        temp_rejected     = os.path.join(tmp, "rejected")
        temp_redundant    = os.path.join(tmp, "redundant")
        temp_reports      = os.path.join(tmp, "reports")
        temp_for_labeling = os.path.join(tmp, "for_labeling")
        temp_labeled      = os.path.join(tmp, "labeled_return")
        temp_training     = os.path.join(tmp, "training")
        temp_golden       = os.path.join(tmp, "golden")
        temp_pending      = os.path.join(tmp, "pending_review")
        temp_quarantine   = os.path.join(tmp, "quarantine")
        temp_logs         = os.path.join(tmp, "logs")
        temp_db           = os.path.join(tmp, "factory_test.db")

        for d in (temp_raw, temp_archive, temp_rejected, temp_redundant, temp_reports,
                  temp_for_labeling, temp_labeled, temp_training, temp_golden,
                  temp_pending, temp_quarantine, temp_logs):
            os.makedirs(d, exist_ok=True)

        n = seed_test.seed_raw(test_source, temp_raw, clear_raw_first=True)
        if n == 0:
            raise RuntimeError("测试源无视频，请先在 storage/test/original/ 放入测试视频。")
        print(f"  Seeded {n} test videos -> temp raw\n", flush=True)

        test_cfg = copy.deepcopy(cfg)
        test_cfg["paths"] = dict(paths)
        test_cfg["paths"].update({
            "raw_video":        temp_raw,
            "data_warehouse":   temp_archive,
            "rejected_material": temp_rejected,
            "redundant_archives": temp_redundant,
            "reports":          temp_reports,
            "labeling_export":  temp_for_labeling,
            "labeled_return":   temp_labeled,
            "training":         temp_training,
            "golden":           temp_golden,
            "pending_review":   temp_pending,
            "quarantine":       temp_quarantine,
            "logs":             temp_logs,
            "db_file":          temp_db,
            "db_url":           temp_db,
        })

        test_cfg.setdefault("mlflow", {})["enabled"] = False
        test_cfg.setdefault("vision", {})["model_path"] = "models/yolov8s.pt"

        log_config.setup_logging(BASE_DIR, test_cfg, console=True)
        config_loader.init_storage_from_config(test_cfg)

        from utils import startup
        if test_cfg.get("startup_self_check", True):
            if not startup.run_startup_self_check(test_cfg):
                raise RuntimeError("开机自检失败")
        startup.run_rolling_cleanup(test_cfg)
        startup.run_disk_check(test_cfg)
        if test_cfg.get("startup_golden_run"):
            if not startup.run_golden_run(test_cfg):
                raise RuntimeError("Golden run 失败")

        from db import db_tools
        if not db_tools.init_db(temp_db):
            raise RuntimeError("数据库初始化失败")

        pipeline.run_smart_factory(cfg=test_cfg, gate_val=gate_val)
        print("\n  [OK] Test passed — temp environment cleaned up.\n", flush=True)


def cmd_test(gate_val=None) -> None:
    """CLI 入口：包裹 run_full_pipeline_test，失败时 sys.exit(1)。"""
    try:
        run_full_pipeline_test(gate_val=gate_val)
    except RuntimeError as e:
        print(f"  [FAIL] {e}")
        sys.exit(1)


# ─────────────────────────── CLI ───────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DataFactory 运维工具集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools.py --usage-report\n"
            "  python tools.py --usage-report --days 7\n"
            "  python tools.py --usage-reset clip_embedding\n"
            "  python tools.py --usage-reset all\n"
            "  python tools.py --probe\n"
            "  python tools.py --test\n"
            "  python tools.py --test --gate 80\n"
        ),
    )
    parser.add_argument("--usage-report", action="store_true",
                        help="打印功能使用报告")
    parser.add_argument("--days", type=int, default=30,
                        help="--usage-report 统计天数（默认 30）")
    parser.add_argument("--usage-reset", type=str, default="", metavar="FEATURE|all",
                        help="重置使用计数：传功能名重置单项，传 'all' 重置全部")
    parser.add_argument("--probe", action="store_true",
                        help="硬件检测：打印设备能力与自动配置建议")
    parser.add_argument("--test", action="store_true",
                        help="全链路测试：临时环境跑 pipeline，不污染真实数据")
    parser.add_argument("--gate", type=float, default=None,
                        help="配合 --test 使用，覆盖准入阈值 (%%)")
    args = parser.parse_args()

    if args.usage_report:
        cmd_usage_report(days=args.days)
    elif args.usage_reset:
        cmd_usage_reset(target=args.usage_reset)
    elif args.probe:
        cmd_probe()
    elif args.test:
        cmd_test(gate_val=args.gate)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
