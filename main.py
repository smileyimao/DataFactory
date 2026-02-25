# main.py — 工厂总开关：单次运行或 Guard 模式
import copy
import os
import sys
import tempfile
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

VIDEO_EXT = (".mov", ".mp4", ".avi", ".mkv")


def _run_test_mode(gate_val=None):
    """测试模式：临时环境跑全链路，邮件照发，不污染真实 storage/DB。"""
    from config import config_loader
    from config import logging as log_config
    from core import pipeline
    from core import seed_test

    config_loader.set_base_dir(BASE_DIR)
    cfg = config_loader.load_config()
    paths = cfg.get("paths", {})
    test_source = paths.get("test_source") or os.path.join(BASE_DIR, "storage", "test", "original")
    test_source = os.path.abspath(test_source)

    if not os.path.isdir(test_source):
        print("❌ 测试源目录不存在:", test_source)
        sys.exit(1)
    video_count = sum(
        1 for n in os.listdir(test_source)
        if os.path.isfile(os.path.join(test_source, n))
        and any(n.lower().endswith(ext) for ext in VIDEO_EXT)
    )
    if video_count == 0:
        print("❌ 测试源无视频，请先在 storage/test/original/ 放入测试视频。")
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="datafactory_test_") as tmp:
        temp_raw = os.path.join(tmp, "raw")
        temp_archive = os.path.join(tmp, "archive")
        temp_rejected = os.path.join(tmp, "rejected")
        temp_redundant = os.path.join(tmp, "redundant")
        temp_reports = os.path.join(tmp, "reports")
        temp_for_labeling = os.path.join(tmp, "for_labeling")
        temp_labeled_return = os.path.join(tmp, "labeled_return")
        temp_training = os.path.join(tmp, "training")
        temp_golden = os.path.join(tmp, "golden")
        temp_pending = os.path.join(tmp, "pending_review")
        temp_quarantine = os.path.join(tmp, "quarantine")
        temp_logs = os.path.join(tmp, "logs")
        temp_db = os.path.join(tmp, "factory_test.db")

        for d in (temp_raw, temp_archive, temp_rejected, temp_redundant, temp_reports,
                  temp_for_labeling, temp_labeled_return, temp_training, temp_golden,
                  temp_pending, temp_quarantine, temp_logs):
            os.makedirs(d, exist_ok=True)

        n = seed_test.seed_raw(test_source, temp_raw, clear_raw_first=True)
        if n == 0:
            print("❌ 测试源无视频，请先在 storage/test/original/ 放入测试视频。")
            sys.exit(1)
        print(f"✅ 已复制 {n} 个测试视频到临时 raw，开始 pipeline（临时环境，邮件照发）...\n")

        test_cfg = copy.deepcopy(cfg)
        test_cfg["paths"] = dict(paths)
        test_cfg["paths"]["raw_video"] = temp_raw
        test_cfg["paths"]["data_warehouse"] = temp_archive
        test_cfg["paths"]["rejected_material"] = temp_rejected
        test_cfg["paths"]["redundant_archives"] = temp_redundant
        test_cfg["paths"]["reports"] = temp_reports
        test_cfg["paths"]["labeling_export"] = temp_for_labeling
        test_cfg["paths"]["labeled_return"] = temp_labeled_return
        test_cfg["paths"]["training"] = temp_training
        test_cfg["paths"]["golden"] = temp_golden
        test_cfg["paths"]["pending_review"] = temp_pending
        test_cfg["paths"]["quarantine"] = temp_quarantine
        test_cfg["paths"]["logs"] = temp_logs
        test_cfg["paths"]["db_file"] = temp_db

        log_config.setup_logging(BASE_DIR, test_cfg)
        config_loader.init_storage_from_config(test_cfg)

        from config import startup
        if test_cfg.get("startup_self_check", True):
            if not startup.run_startup_self_check(test_cfg):
                sys.exit(1)
        startup.run_rolling_cleanup(test_cfg)
        if test_cfg.get("startup_golden_run"):
            if not startup.run_golden_run(test_cfg):
                sys.exit(1)

        from engines import db_tools
        if not db_tools.init_db(temp_db):
            print("❌ 数据库初始化失败。")
            sys.exit(1)

        pipeline.run_smart_factory(cfg=test_cfg, gate_val=gate_val)
        print("\n✅ 测试完成，临时环境已自动清理，未污染真实 storage/DB。")


def main():
    from config import config_loader
    from config import logging as log_config
    from core import pipeline

    parser = argparse.ArgumentParser(description="DataFactory 集中质检复核")
    parser.add_argument("--gate", type=float, default=None, help="准入阈值 (%%)")
    parser.add_argument("--guard", action="store_true", help="启动 Guard 模式：监控 raw_video，凑批后自动送厂")
    parser.add_argument("--test", action="store_true", help="测试模式：临时环境跑全链路，邮件照发，不污染真实数据")
    args = parser.parse_args()

    if args.test:
        _run_test_mode(gate_val=args.gate)
        return

    config_loader.set_base_dir(BASE_DIR)
    cfg = config_loader.load_config()
    log_config.setup_logging(BASE_DIR, cfg)
    config_loader.init_storage_from_config(cfg)

    from config import startup
    if cfg.get("startup_self_check", True):
        if not startup.run_startup_self_check(cfg):
            sys.exit(1)
    startup.run_rolling_cleanup(cfg)
    if cfg.get("startup_golden_run"):
        if not startup.run_golden_run(cfg):
            sys.exit(1)

    db_path = cfg.get("paths", {}).get("db_file")
    if db_path:
        from engines import db_tools
        if not db_tools.init_db(db_path):
            print("❌ 数据库初始化失败，请检查 db_file 路径与权限。")
            sys.exit(1)

    if args.guard:
        from core import guard
        guard.run_guard()
    else:
        pipeline.run_smart_factory(gate_val=args.gate)
        print("\n💡 提示：要持续监控 storage/raw 目录，请使用: python main.py --guard")


if __name__ == "__main__":
    main()
