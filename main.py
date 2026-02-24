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


def main():
    from config import config_loader
    from config import logging as log_config
    from core import pipeline

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

    parser = argparse.ArgumentParser(description="DataFactory 集中质检复核")
    parser.add_argument("--gate", type=float, default=None, help="准入阈值 (%)")
    parser.add_argument("--guard", action="store_true", help="启动 Guard 模式：监控 raw_video，凑批后自动送厂")
    args = parser.parse_args()

    if args.guard:
        from core import guard
        guard.run_guard()
    else:
        pipeline.run_smart_factory(gate_val=args.gate)
        print("\n💡 提示：要持续监控 storage/raw 目录，请使用: python main.py --guard")


if __name__ == "__main__":
    main()
