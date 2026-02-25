#!/usr/bin/env python3
# scripts/sanity_check.py — 最简自检：配置加载、模块导入、无崩溃（无需测试数据）
"""
不依赖 storage/test/original 或真实视频，只验证：
1) 配置能加载
2) 核心模块能导入
3) 关键函数可调用（不执行完整流程）

用法: python scripts/sanity_check.py
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)


def main() -> int:
    print("🔍 Sanity check (no test data required)...")
    errs = []

    # 1. Config
    try:
        from config import config_loader
        config_loader.set_base_dir(BASE_DIR)
        cfg = config_loader.load_config()
        paths = cfg.get("paths", {})
        assert paths.get("raw_video"), "paths.raw_video missing"
        print("  ✓ config loaded")
    except Exception as e:
        errs.append(f"config: {e}")

    # 2. Core imports
    try:
        from core import pipeline, ingest, qc_engine, reviewer, archiver
        from engines import production_tools, vision_detector, labeling_export
        from engines import motion_filter, frame_io
        print("  ✓ core + engines imported")
    except Exception as e:
        errs.append(f"imports: {e}")

    # 3. ingest with empty dir
    try:
        from config import config_loader
        config_loader.set_base_dir(BASE_DIR)
        cfg = config_loader.load_config()
        paths = cfg.get("paths", {})
        raw = paths.get("raw_video", "")
        if raw and os.path.isdir(raw):
            from core import ingest
            videos = ingest.get_video_paths(cfg)
            print(f"  ✓ ingest.get_video_paths -> {len(videos)} videos")
        else:
            print("  ⚠ raw_video not a dir, skip ingest check")
    except Exception as e:
        errs.append(f"ingest: {e}")

    if errs:
        print("\n❌ Failures:")
        for e in errs:
            print(f"   - {e}")
        return 1
    print("\n✅ Sanity check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
