#!/usr/bin/env python3
# scripts/reset_factory.py — 一键清理测试环境（预留）
"""
清理 storage/test、可选清理 storage/raw 等，便于测试环境重置。
用法:
  python scripts/reset_factory.py              # 仅清理 storage/test，默认 --dry-run
  python scripts/reset_factory.py --execute    # 真正执行清理
  python scripts/reset_factory.py --execute --target raw  # 额外清空 storage/raw
"""
import argparse
import os
import sys

# 项目根 = 脚本所在目录的上一级
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)


def _ensure_storage_subdirs():
    """返回 (base_dir, storage_dir) 及子目录列表。"""
    storage = os.path.join(BASE_DIR, "storage")
    subdirs = ["raw", "archive", "rejected", "redundant", "test", "reports"]
    return BASE_DIR, storage, subdirs


def _list_files_and_dirs(path: str):
    """递归列出 path 下所有文件与目录（相对 path）。"""
    out = []
    for root, dirs, files in os.walk(path, topdown=True):
        rel = os.path.relpath(root, path)
        if rel == ".":
            rel = ""
        for d in dirs:
            out.append(os.path.join(rel, d) + "/")
        for f in files:
            out.append(os.path.join(rel, f))
    return sorted(out)


def clear_dir(dir_path: str, dry_run: bool) -> int:
    """清空目录内容（保留目录本身）。返回删除条目数。"""
    if not os.path.isdir(dir_path):
        return 0
    count = 0
    for name in os.listdir(dir_path):
        p = os.path.join(dir_path, name)
        if dry_run:
            count += 1
            continue
        if os.path.isdir(p):
            import shutil
            shutil.rmtree(p)
            count += 1
        else:
            os.remove(p)
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Reset factory test environment (clear storage subdirs).")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Only print what would be done (default).")
    parser.add_argument("--execute", action="store_true", help="Actually delete files (disables dry-run).")
    parser.add_argument("--target", choices=["test", "raw", "reports"], default="test",
                        help="Which storage subdir to clear (default: test).")
    args = parser.parse_args()
    dry_run = not args.execute

    _, storage, subdirs = _ensure_storage_subdirs()
    target_dir = os.path.join(storage, args.target)
    if not os.path.isdir(target_dir):
        print(f"Directory does not exist: {target_dir}")
        return 0

    items = _list_files_and_dirs(target_dir)
    if not items:
        print(f"Already empty: {target_dir}")
        return 0

    if dry_run:
        print(f"[DRY-RUN] Would remove {len(items)} item(s) under {target_dir}:")
        for x in items[:20]:
            print(f"  {x}")
        if len(items) > 20:
            print(f"  ... and {len(items) - 20} more")
        return 0

    n = clear_dir(target_dir, dry_run=False)
    print(f"Cleared {n} item(s) under {target_dir}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
