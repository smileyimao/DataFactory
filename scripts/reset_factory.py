#!/usr/bin/env python3
# scripts/reset_factory.py — 一键清理 storage 子目录，便于测试/重置
"""
清理 storage 下指定子目录。默认仅 dry-run。
用法:
  python scripts/reset_factory.py                    # 默认 --target test，仅 dry-run
  python scripts/reset_factory.py --execute          # 真正清空 storage/test
  python scripts/reset_factory.py --execute --target raw
  python scripts/reset_factory.py --execute --target archive --confirm-dangerous  # 清空成品库，需二次确认

危险目标（archive/rejected/redundant/db）会删除批次/废片/冗余/指纹历史，必须同时加 --confirm-dangerous 才会执行，防止上线误触。
  python scripts/reset_factory.py --execute --target db --confirm-dangerous  # 清空 MD5 历史（factory_admin.db），下次跑同批视频不再判重复
"""
import argparse
import os
import sys

# 清空会删除“真实数据”的目标，必须加 --confirm-dangerous 才执行
DANGEROUS_TARGETS = {"archive", "rejected", "redundant", "db"}

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
    parser = argparse.ArgumentParser(
        description="Reset factory: clear storage subdirs. Dangerous targets (archive/rejected/redundant) require --confirm-dangerous."
    )
    parser.add_argument("--dry-run", action="store_true", default=True, help="Only print what would be done (default).")
    parser.add_argument("--execute", action="store_true", help="Actually delete files (disables dry-run).")
    parser.add_argument(
        "--target",
        choices=["test", "raw", "reports", "archive", "rejected", "redundant", "db"],
        default="test",
        help="Which to clear: storage subdir (test/raw/reports/archive/rejected/redundant) or db (MD5 history). archive/rejected/redundant/db require --confirm-dangerous.",
    )
    parser.add_argument(
        "--confirm-dangerous",
        action="store_true",
        help="Required when --target is archive, rejected or redundant (deletes batch/fail/redundant data).",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    # 目标 db：删除 db/factory_admin.db（MD5/指纹历史），下次 main 会重建空表
    if args.target == "db":
        db_dir = os.path.join(BASE_DIR, "db")
        db_file = os.path.join(db_dir, "factory_admin.db")
        if args.target in DANGEROUS_TARGETS and not args.confirm_dangerous:
            if args.execute:
                print(
                    "Refusing to clear db (MD5 history) without --confirm-dangerous.",
                    file=sys.stderr,
                )
                print("Example: python scripts/reset_factory.py --execute --target db --confirm-dangerous", file=sys.stderr)
                return 1
            print("[DRY-RUN] Target db is dangerous; use --confirm-dangerous with --execute to actually clear.", file=sys.stderr)
        if not os.path.isfile(db_file):
            print(f"DB file does not exist: {db_file}")
            return 0
        if dry_run:
            print(f"[DRY-RUN] Would remove: {db_file}")
            return 0
        try:
            os.remove(db_file)
            print(f"Removed: {db_file}")
        except OSError as e:
            print(f"Failed to remove {db_file}: {e}", file=sys.stderr)
            return 1
        return 0

    _, storage, _ = _ensure_storage_subdirs()
    target_dir = os.path.join(storage, args.target)
    if not os.path.isdir(target_dir):
        print(f"Directory does not exist: {target_dir}")
        return 0

    # 危险目标：未加 --confirm-dangerous 且要真正执行时，拒绝并退出
    if args.target in DANGEROUS_TARGETS and not args.confirm_dangerous:
        if args.execute:
            print(
                f"Refusing to clear storage/{args.target} without --confirm-dangerous (this deletes batch/production-like data).",
                file=sys.stderr,
            )
            print("Example: python scripts/reset_factory.py --execute --target archive --confirm-dangerous", file=sys.stderr)
            return 1
        # dry-run 时只提示，仍可执行 dry-run
        print(f"[DRY-RUN] Target storage/{args.target} is dangerous; use --confirm-dangerous with --execute to actually clear.", file=sys.stderr)

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
