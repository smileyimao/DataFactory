#!/usr/bin/env python3
# scripts/reset_factory.py — 一键清理 storage 子目录，便于测试/重置
"""
清理 storage / db，便于测试/重置。默认仅 dry-run。
用法:
  python scripts/reset_factory.py   # dry-run（默认 --target for-test）
  python scripts/reset_factory.py --execute --target db --confirm-dangerous  # 清空 MD5 历史（factory_admin.db），下次跑同批视频不再判重复
  python scripts/reset_factory.py --execute --target for-test --confirm-dangerous  # 测试用：清空 archive + redundant + rejected + reports + db，便于反复用同一批视频测试
"""
import argparse
import os
import sys

DANGEROUS_TARGETS = {"db"}  # 需 --confirm-dangerous 才执行

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
        description="Reset factory: clear db or storage (for-test). Requires --confirm-dangerous when --execute."
    )
    parser.add_argument("--dry-run", action="store_true", default=True, help="Only print what would be done (default).")
    parser.add_argument("--execute", action="store_true", help="Actually delete files (disables dry-run).")
    parser.add_argument(
        "--target",
        choices=["db", "for-test"],
        default="for-test",
        help="db = MD5 history; for-test = archive+redundant+rejected+reports+db. Requires --confirm-dangerous with --execute.",
    )
    parser.add_argument(
        "--confirm-dangerous",
        action="store_true",
        help="Required when --execute (deletes data).",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    # 目标 for-test：一次清空 archive + redundant + rejected + reports + db，便于反复用同一批视频测试
    if args.target == "for-test":
        if args.execute and not args.confirm_dangerous:
            print("Refusing to run for-test without --confirm-dangerous.", file=sys.stderr)
            print("Example: python scripts/reset_factory.py --execute --target for-test --confirm-dangerous", file=sys.stderr)
            return 1
        _, storage, _ = _ensure_storage_subdirs()
        targets = [
            ("archive", os.path.join(storage, "archive")),
            ("redundant", os.path.join(storage, "redundant")),
            ("rejected", os.path.join(storage, "rejected")),
            ("reports", os.path.join(storage, "reports")),
        ]
        for name, dir_path in targets:
            if os.path.isdir(dir_path):
                if args.execute:
                    n = clear_dir(dir_path, dry_run=False)
                    print(f"Cleared {n} item(s) under storage/{name}.")
                else:
                    n = len(_list_files_and_dirs(dir_path))
                    print(f"[DRY-RUN] Would clear {n} item(s) under storage/{name}.")
            else:
                if not args.execute:
                    print(f"[DRY-RUN] Would clear 0 item(s) under storage/{name} (dir missing).")
        # db
        db_dir = os.path.join(BASE_DIR, "db")
        db_file = os.path.join(db_dir, "factory_admin.db")
        if os.path.isfile(db_file):
            if args.execute:
                try:
                    os.remove(db_file)
                    print("Removed: db/factory_admin.db (MD5 history cleared).")
                except OSError as e:
                    print(f"Failed to remove {db_file}: {e}", file=sys.stderr)
                    return 1
            else:
                print("[DRY-RUN] Would remove: db/factory_admin.db")
        else:
            if not args.execute:
                print("[DRY-RUN] db/factory_admin.db does not exist.")
        if not args.execute:
            print("[DRY-RUN] Use --execute --confirm-dangerous to actually clear.")
        return 0

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

    # 仅支持 db / for-test，不会走到这里
    print(f"Unknown target: {args.target}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
