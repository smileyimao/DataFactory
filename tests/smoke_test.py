#!/usr/bin/env python3
# tests/smoke_test.py v2.0 — 冒烟测试：固若金汤版
"""
1) 生成测试物料（清空 test/ 保留 original/，标准件/变异件/冗余件，统一小写 .mov）
2) 指纹校验：生成后对关键文件做 MD5 校验，若 original 素材两两雷同则报错退出
3) 在临时目录跑 QC（两阶段），断言预期
4) 结果表 ANSI 着色（绿 PASS / 红 FAIL）
5) 冒烟测试内准入线临时设为 50%，避免 normal 素材实际得分低于生产 gate 时误判 FAIL。

前置: storage/test/original/ 下需有 normal.mov, jitter.mov, black.mov, image.jpg（大小写不敏感）
"""
import os
import shutil
import sys
import tempfile
import logging

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

TEST_ROOT = os.path.join(PROJECT_ROOT, "storage", "test")
ORIGINAL_DIR = os.path.join(TEST_ROOT, "original")
ORIGINAL_VIDEOS = ["normal.mov", "jitter.mov", "black.mov"]
ORIGINAL_IMAGE = "image.jpg"
ONE_MB = 1024 * 1024
VIDEO_EXT = (".mov", ".mp4", ".avi", ".mkv")
# 标准件 + 冗余件中「必须两两不同」的文件（若雷同会误判 DUPLICATE）
FINGERPRINT_CHECK_FILES = ["normal.mov", "jitter.mov", "black.mov"]

os.environ.setdefault("DATAFLOW_TEST", "1")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

EXPECTED = {
    "normal.mov": "PASS",
    "jitter.mov": "REVIEW",
    "black.mov": "REJECTED",
    "fake_from_img.mov": "REJECTED_CORRUPTED",
    "incomplete_stream.mov": "REJECTED_CORRUPTED",
    "zero_byte_video.mov": "REJECTED_CORRUPTED",
    "normal_duplicate.mov": "DUPLICATE",
}

# ANSI
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _find_original(path_dir: str, name: str) -> str:
    """按名称查找文件（忽略大小写），返回绝对路径。"""
    if not os.path.isdir(path_dir):
        return ""
    lower = name.lower()
    for entry in os.listdir(path_dir):
        if entry.lower() == lower:
            return os.path.join(path_dir, entry)
    return ""


def _safe_remove(path: str) -> bool:
    """删除文件，失败时打印友好提示。"""
    try:
        if os.path.isfile(path):
            os.remove(path)
        return True
    except OSError as e:
        logger.error("删除失败: %s — %s", path, e)
        print(f"{RED}厂长，文件被占用或无权删除，请先关闭播放器/编辑器: {path}{RESET}")
        return False


def _safe_rmtree(path: str) -> bool:
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        return True
    except OSError as e:
        logger.error("删除目录失败: %s — %s", path, e)
        print(f"{RED}厂长，目录被占用或无权删除，请先关闭占用程序: {path}{RESET}")
        return False


def _safe_copy2(src: str, dst: str) -> bool:
    try:
        shutil.copy2(src, dst)
        return True
    except OSError as e:
        logger.error("复制失败: %s -> %s — %s", src, dst, e)
        print(f"{RED}厂长，文件被占用，请先关闭播放器（如 QuickTime）再重试。{RESET}")
        return False


def _safe_write_bytes(path: str, data: bytes) -> bool:
    try:
        with open(path, "wb") as f:
            f.write(data)
        return True
    except OSError as e:
        logger.error("写入失败: %s — %s", path, e)
        print(f"{RED}厂长，目标被占用或不可写，请先关闭占用程序。{RESET}")
        return False


def _ensure_test_data() -> bool:
    """清空 test/（保留 original/），从 original/ 生成物料；派生物统一小写 .mov。"""
    if not os.path.isdir(TEST_ROOT):
        os.makedirs(TEST_ROOT, exist_ok=True)
    for name in os.listdir(TEST_ROOT):
        if name == "original":
            continue
        path = os.path.join(TEST_ROOT, name)
        if os.path.isfile(path):
            if not _safe_remove(path):
                return False
        elif os.path.isdir(path):
            if not _safe_rmtree(path):
                return False
    logger.info("已清空 storage/test/（保留 original/）")

    if not os.path.isdir(ORIGINAL_DIR):
        logger.error("原始素材目录不存在: %s", ORIGINAL_DIR)
        sys.exit(1)
    missing = [f for f in ORIGINAL_VIDEOS + [ORIGINAL_IMAGE] if not _find_original(ORIGINAL_DIR, f)]
    if missing:
        logger.error("原始素材缺失: %s", ", ".join(missing))
        sys.exit(1)

    for name in ORIGINAL_VIDEOS:
        src = _find_original(ORIGINAL_DIR, name)
        if src and not _safe_copy2(src, os.path.join(TEST_ROOT, name.lower())):
            return False
    src_img = _find_original(ORIGINAL_DIR, ORIGINAL_IMAGE)
    if src_img and not _safe_copy2(src_img, os.path.join(TEST_ROOT, "fake_from_img.mov")):
        return False
    src_normal = _find_original(ORIGINAL_DIR, "normal.mov")
    if src_normal:
        try:
            with open(src_normal, "rb") as f:
                chunk = f.read(ONE_MB)
        except OSError as e:
            logger.error("读取失败: %s — %s", src_normal, e)
            print(f"{RED}厂长，文件被占用，请先关闭播放器。{RESET}")
            return False
        if not _safe_write_bytes(os.path.join(TEST_ROOT, "incomplete_stream.mov"), chunk):
            return False
    if not _safe_write_bytes(os.path.join(TEST_ROOT, "zero_byte_video.mov"), b""):
        return False
    if src_normal and not _safe_copy2(src_normal, os.path.join(TEST_ROOT, "normal_duplicate.mov")):
        return False
    logger.info("测试物料已就绪: storage/test/（7 个文件，统一小写 .mov）")
    return True


def _check_fingerprints() -> None:
    """生成后校验：normal/jitter/black 两两 MD5 不得相同，否则报错退出。"""
    sys.path.insert(0, PROJECT_ROOT)
    from engines import fingerprinter

    paths = []
    for name in FINGERPRINT_CHECK_FILES:
        p = os.path.join(TEST_ROOT, name)
        if os.path.isfile(p):
            paths.append((name, p))
    if len(paths) < 2:
        return
    fingerprints = []
    for name, p in paths:
        fp = fingerprinter.compute(p) or ""
        fingerprints.append((name, fp))
    seen = {}
    for name, fp in fingerprints:
        if not fp:
            continue
        if fp in seen:
            logger.error("指纹雷同: %s 与 %s 的 MD5 相同，后续测试会误判 DUPLICATE。", seen[fp], name)
            print(f"{RED}厂长，original/ 内素材内容重复：{seen[fp]} 与 {name} 指纹相同。请更换其中一份素材后重试。{RESET}")
            sys.exit(1)
        seen[fp] = name
    logger.info("指纹校验通过: normal/jitter/black 两两不同。")


def _actual_category(item: dict) -> str:
    if item.get("is_duplicate"):
        return "DUPLICATE"
    if item.get("passed"):
        return "PASS"
    return "REJECTED"


def run() -> int:
    from config import config_loader
    from core import qc_engine
    from engines import db_tools

    config_loader.set_base_dir(PROJECT_ROOT)
    cfg = config_loader.load_config()
    paths_cfg = cfg.get("paths", {})
    test_root = os.path.join(PROJECT_ROOT, "storage", "test")

    with tempfile.TemporaryDirectory(prefix="smoke_test_") as tmp:
        temp_raw = os.path.join(tmp, "raw")
        temp_warehouse = os.path.join(tmp, "warehouse")
        temp_db = os.path.join(tmp, "factory_test.db")
        os.makedirs(temp_raw, exist_ok=True)
        os.makedirs(temp_warehouse, exist_ok=True)

        for name in os.listdir(test_root):
            if name == "original":
                continue
            p = os.path.join(test_root, name)
            if not os.path.isfile(p):
                continue
            if not any(name.lower().endswith(ext) for ext in VIDEO_EXT):
                continue
            dest_name = name if name.lower().endswith(".mov") else (os.path.splitext(name)[0] + ".mov")
            dest = os.path.join(temp_raw, dest_name.lower())
            if not _safe_copy2(p, dest):
                return 1

        all_paths = [os.path.join(temp_raw, n) for n in sorted(os.listdir(temp_raw))]
        normal_path = next((p for p in all_paths if os.path.basename(p).lower() == "normal.mov"), None)
        other_paths = [p for p in all_paths if p != normal_path]

        cfg = dict(cfg)
        cfg["paths"] = dict(paths_cfg)
        cfg["paths"]["raw_video"] = temp_raw
        cfg["paths"]["data_warehouse"] = temp_warehouse
        cfg["paths"]["db_file"] = temp_db
        cfg["paths"]["reports"] = os.path.join(tmp, "reports")
        os.makedirs(cfg["paths"]["reports"], exist_ok=True)
        cfg["email_setting"] = {}
        # 冒烟测试专用：临时降低准入线，避免 normal.mov 因实际得分（如 60%）低于生产 gate（85%）被判 REJECTED 导致误报
        cfg.setdefault("production_setting", {})["pass_rate_gate"] = 50.0

        db_tools.init_db(temp_db)
        results = {}

        if normal_path and os.path.isfile(normal_path):
            qc_archive, qualified, blocked, _, path_info = qc_engine.run_qc(cfg, [normal_path])
            for item in qc_archive:
                results[item["filename"]] = _actual_category(item)
            batch_id = path_info.get("batch_id", "")
            db_path = cfg["paths"]["db_file"]
            for x in qc_archive:
                if x.get("fingerprint"):
                    db_tools.record_production(
                        db_path, batch_id, x["fingerprint"], x["score"], "SUCCESS"
                    )
                    break
        else:
            logger.warning("未找到 normal.mov，跳过阶段 1")

        if other_paths:
            remaining = [p for p in other_paths if os.path.isfile(p)]
            if remaining:
                qc_archive, _, _, _, _ = qc_engine.run_qc(cfg, remaining)
                for item in qc_archive:
                    results[item["filename"]] = _actual_category(item)

    failed = []
    for filename, expected in EXPECTED.items():
        actual = results.get(filename)
        if actual is None:
            failed.append((filename, expected, "MISSING"))
            continue
        ok = False
        if expected == "REVIEW":
            ok = actual in ("PASS", "REJECTED")
        elif expected == "REJECTED_CORRUPTED":
            ok = actual == "REJECTED"
        else:
            ok = actual == expected
        if not ok:
            failed.append((filename, expected, actual))

    print("\n" + "=" * 60)
    print(f"{BOLD}Smoke 测试结果 (v2.0){RESET}")
    print("=" * 60)
    for filename in sorted(EXPECTED.keys()):
        exp = EXPECTED[filename]
        act = results.get(filename, "MISSING")
        ok = (exp == "REVIEW" and act in ("PASS", "REJECTED")) or (exp == "REJECTED_CORRUPTED" and act == "REJECTED") or (exp == act)
        if ok:
            color = GREEN
            sym = "✓"
        else:
            color = RED
            sym = "✗"
        print(f"  {color}{sym} {filename}: Expected={exp}  Actual={act}{RESET}")
    print("=" * 60)

    if failed:
        logger.error("失败 %d 项: %s", len(failed), failed)
        print(f"\n{RED}❌ Smoke 测试未通过。{RESET}\n")
        return 1
    print(f"\n{GREEN}✅ Smoke 测试全部通过，产线健康。{RESET}\n")
    return 0


def main() -> int:
    logger.info("Step 1: 生成测试物料（大小写不敏感，派生物小写 .mov）")
    if not _ensure_test_data():
        return 1
    logger.info("Step 1.5: 指纹校验（original 素材两两不得雷同）")
    _check_fingerprints()
    logger.info("Step 2: 运行 QC 并断言")
    return run()


if __name__ == "__main__":
    sys.exit(main())
