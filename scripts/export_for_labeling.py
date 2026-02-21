#!/usr/bin/env python3
# scripts/export_for_labeling.py — 导出合格批次为待标注清单（数据清洗与标注管道扩展）
"""
扫描 storage/archive 下已归档批次，生成 manifest_for_labeling.json 到 storage/for_labeling/，
供 Label Studio / CVAT 等标注工具导入。为接入 ML 做准备（Roadmap v1 可选）。
用法:
  python scripts/export_for_labeling.py           # 导出全部批次
  python scripts/export_for_labeling.py --last 5  # 仅最近 5 个批次
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
    args = parser.parse_args()
    config_loader.set_base_dir(BASE_DIR)
    cfg = config_loader.load_config()
    out = labeling_export.run_export_from_config(cfg, max_batches=args.last)
    if out:
        print(f"✅ 待标注清单已写入: {out}")
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
