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


def _print_pipeline_report(stats: dict, input_name: str, cvat_url: str = "") -> None:
    """打印 Pipeline 统计报告。"""
    total = stats.get("total", 0) or 1
    with_pseudo = stats.get("with_pseudo", 0)
    refinery = stats.get("refinery", 0)
    inspection = stats.get("inspection", 0)
    pct = int(with_pseudo / total * 100) if total else 0
    refinery_pct = int(refinery / total * 100) if total else 0
    inspection_pct = int(inspection / total * 100) if total else 0
    print(f"\n=== DataFactory Pipeline 报告 ===")
    print(f"输入视频：{input_name}")
    print(f"总关键帧：{total}")
    print(f"自动标注：{with_pseudo}（{pct}%）")
    print(f"refinery（高置信）：{refinery}（{refinery_pct}%）   # 伪标签可直接用")
    print(f"inspection（待人工）：{inspection}（{inspection_pct}%） # 需人工标注或复核")
    print("─" * 40)
    print(f"人工工作量节省：约{pct}%")
    if cvat_url:
        print(f"CVAT Task：{cvat_url}")
    print()


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
    parser.add_argument("--input", type=str, default="", help="指定单个视频路径，仅处理此文件")
    parser.add_argument("--auto-cvat", action="store_true", help="pipeline 结束后自动创建 CVAT Task 并上传图片与伪标签")
    parser.add_argument("--no-cvat", action="store_true", help="强制跳过标注平台上传（覆盖 CVAT_LOCAL_URL 自动触发）")
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

    db_url = cfg.get("paths", {}).get("db_url")
    if not db_url:
        print("❌ DATABASE_URL 未设置，请在 .env 中配置 DATABASE_URL=postgresql://...")
        sys.exit(1)
    from engines import db_tools
    if not db_tools.init_db(db_url):
        print("❌ 数据库初始化失败，请检查 DATABASE_URL 配置与 PostgreSQL 是否运行。")
        sys.exit(1)

    video_paths = None
    input_name = "storage/raw"
    if args.input:
        p = os.path.abspath(os.path.expanduser(args.input))
        if not os.path.isfile(p):
            print(f"❌ 文件不存在: {args.input}")
            sys.exit(1)
        video_paths = [p]
        input_name = os.path.basename(p)

    if args.guard:
        from core import guard
        guard.run_guard()
    else:
        pipeline.run_smart_factory(gate_val=args.gate, video_paths=video_paths)

        # 统计报告
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
            from engines import annotation_upload
            cvat_url = annotation_upload.upload(cfg, task_name=stats.get("batch_id", "DataFactory"))

        _print_pipeline_report(stats, input_name, cvat_url)
        if not args.auto_cvat:
            print("\n💡 提示：要持续监控 storage/raw 目录，请使用: python main.py --guard")


if __name__ == "__main__":
    main()
