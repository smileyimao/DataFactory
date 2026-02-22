#!/usr/bin/env python3
# scripts/reset_config.py — 将 config/settings.yaml 恢复为仓库默认配置
"""
把当前配置恢复为 config/settings.default.yaml 的内容，方便新手改乱后一键还原。
用法:
  python scripts/reset_config.py              # 先备份当前 settings.yaml，再恢复默认
  python scripts/reset_config.py --no-backup  # 不备份，直接覆盖
  python scripts/reset_config.py --dry-run    # 只打印将要做的操作，不写文件
"""
import argparse
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_YAML = os.path.join(BASE_DIR, "config", "settings.default.yaml")
SETTINGS_YAML = os.path.join(BASE_DIR, "config", "settings.yaml")
BACKUP_SUFFIX = ".bak"


def main():
    parser = argparse.ArgumentParser(
        description="Restore config/settings.yaml to factory default (from settings.default.yaml)."
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not backup current settings.yaml before overwriting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be done, do not write files.",
    )
    args = parser.parse_args()

    if not os.path.isfile(DEFAULT_YAML):
        print(f"Default config not found: {DEFAULT_YAML}", file=sys.stderr)
        return 1

    if os.path.isfile(SETTINGS_YAML):
        if args.dry_run:
            print(f"[dry-run] Would backup: {SETTINGS_YAML} -> {SETTINGS_YAML}{BACKUP_SUFFIX}")
            print(f"[dry-run] Would copy:   {DEFAULT_YAML} -> {SETTINGS_YAML}")
            return 0
        if not args.no_backup:
            bak = SETTINGS_YAML + BACKUP_SUFFIX
            shutil.copy2(SETTINGS_YAML, bak)
            print(f"Backed up: {SETTINGS_YAML} -> {bak}")
    else:
        if args.dry_run:
            print(f"[dry-run] Would copy: {DEFAULT_YAML} -> {SETTINGS_YAML}")
            return 0

    if not args.dry_run:
        shutil.copy2(DEFAULT_YAML, SETTINGS_YAML)
        print(f"Restored: {DEFAULT_YAML} -> {SETTINGS_YAML}")
    print("Config reset to factory default (raw_video=storage/raw, vision.enabled=false).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
