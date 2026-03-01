#!/usr/bin/env python3
# scripts/export_for_labeling.py — 导出合格批次为待标注清单（数据清洗与标注管道扩展）
"""
扫描 storage/archive 下已归档批次，生成 manifest_for_labeling.json 到 storage/for_labeling/，
供 Label Studio / CVAT 等标注工具导入。为接入 ML 做准备（Roadmap v1 可选）。
用法:
  python scripts/export_for_labeling.py           # 导出全部批次（refinery + inspection）
  python scripts/export_for_labeling.py --last 5  # 仅最近 5 个批次
  python scripts/export_for_labeling.py --last 1 --inspection-only  # 仅导出 inspection（低置信）
  python scripts/export_for_labeling.py --last 1 --refinery-only    # 仅导出 refinery（高置信），分开标、分开验证
"""
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)

from config import config_loader
from engines import labeling_export


def main():
    parser = argparse.ArgumentParser(description="Export archive batches to labeling manifest.")
    parser.add_argument("--last", type=int, default=None, help="Only export last N batches (default: all).")
    parser.add_argument("--inspection-only", action="store_true", help="Only export inspection (low-confidence).")
    parser.add_argument("--refinery-only", action="store_true", help="Only export refinery (high-confidence), for separate labeling/validation.")
    args = parser.parse_args()
    if args.inspection_only and args.refinery_only:
        parser.error("--inspection-only 与 --refinery-only 不可同时指定")
    cfg, _ = config_loader.get_config_and_paths(BASE_DIR)
    out = labeling_export.run_export_from_config(
        cfg, max_batches=args.last,
        inspection_only=args.inspection_only, refinery_only=args.refinery_only,
    )
    if out:
        import json
        with open(out, encoding="utf-8") as f:
            n = len(json.load(f))
        print(f"✅ 待标注清单已写入: {out}（共 {n} 条）")
        if args.inspection_only and n == 0:
            print("   💡 inspection 为空，可去掉 --inspection-only 或加 --refinery-only 导出 refinery")
        if args.refinery_only and n == 0:
            print("   💡 refinery 为空，可去掉 --refinery-only 或加 --inspection-only 导出 inspection")
    else:
        path = cfg.get("paths", {}).get("labeling_export")
        archive = cfg.get("paths", {}).get("data_warehouse", "")
        if not path:
            print("未配置 paths.labeling_export，跳过导出。")
        elif not os.path.isdir(archive):
            print(f"归档目录不存在: {archive}")
        else:
            print("未找到 Batch_* 目录或导出目录未配置。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
