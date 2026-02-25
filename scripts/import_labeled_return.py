#!/usr/bin/env python3
# scripts/import_labeled_return.py — 标注回传接收、伪标签对比、门槛报警、达标并入训练集
"""
用法:
  python scripts/import_labeled_return.py --dir /path/to/returned_dir
  python scripts/import_labeled_return.py --zip /path/to/returned.zip
  python scripts/import_labeled_return.py --dir /path/to/returned_dir --no-merge   # 只对比不并入
  python scripts/import_labeled_return.py --dir /path --dry-run
"""
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)

from config import config_loader
from engines import labeled_return

config_loader.set_base_dir(BASE_DIR)


def main():
    parser = argparse.ArgumentParser(description="标注回传：接收目录或压缩包，与伪标签对比，达标并入训练集。")
    parser.add_argument("--dir", type=str, default=None, help="回传数据目录（图片+同名 .txt）")
    parser.add_argument("--zip", type=str, default=None, help="回传数据压缩包")
    parser.add_argument("--no-merge", action="store_true", help="仅对比与报警，不并入训练集")
    parser.add_argument("--dry-run", action="store_true", help="只做对比并打印结果，不写报告、不发邮件、不并入")
    args = parser.parse_args()

    if not args.dir and not args.zip:
        parser.error("请指定 --dir 或 --zip")
    if args.dir and args.zip:
        parser.error("请只指定 --dir 或 --zip 之一")

    cfg = config_loader.load_config()
    result = labeled_return.run_full_pipeline(
        cfg,
        source_dir=os.path.abspath(args.dir) if args.dir else None,
        zip_path=os.path.abspath(args.zip) if args.zip else None,
        dry_run=args.dry_run,
        skip_merge=args.no_merge,
    )

    if not result.get("ok"):
        print(f"❌ {result.get('error', '未知错误')}")
        return 1

    r = result
    print(f"\n📋 回传批次: {r['import_id']}")
    print(f"   一致率: {r['consistency_rate']:.2%}  (门槛 {r['threshold']:.0%})")
    print(f"   差异条数: {r['diff_count']}")
    print(f"   结果: {'✅ 达标' if r['passed'] else '⚠️ 未达标，已触发报警'}")
    if r.get("merged_count", 0) > 0:
        print(f"   已并入训练集: {r['merged_count']} 个文件")
    if r.get("batch_labeled_count", 0) > 0:
        print(f"   已写回批次 labeled: {r['batch_labeled_count']} 个文件")
    if args.dry_run:
        print("   [dry-run] 未写报告、未发邮件、未并入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
