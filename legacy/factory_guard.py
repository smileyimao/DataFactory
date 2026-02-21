# 执行引导
def boot_system():
    import os
    import sys
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['PYTHONUNBUFFERED'] = '1'
    _legacy_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(_legacy_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    if _legacy_dir not in sys.path:
        sys.path.append(_legacy_dir)
boot_system()

import os
_base = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_base)
from config.logging import setup_logging
setup_logging(_project_root)

import time
import threading
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from main_factory import run_smart_factory
from db_manager import init_db

logger = logging.getLogger(__name__)
VIDEO_EXT = ('.mp4', '.mov', '.avi', '.mkv')
BATCH_WAIT_SECONDS = 8  # 新文件落地后等待 N 秒再整批送厂，便于多文件一起检测、一封邮件


def _wait_file_stable(file_path, check_interval=1, min_stable_sec=2):
    """等待单文件写入稳定（大小不变）。"""
    last_size = -1
    stable_count = 0
    while True:
        try:
            size = os.path.getsize(file_path)
            if size == last_size and size > 0:
                stable_count += 1
                if stable_count >= min_stable_sec:
                    return
            else:
                stable_count = 0
            last_size = size
        except (FileNotFoundError, OSError):
            return
        time.sleep(check_interval)


def _list_video_paths(raw_video_dir):
    """返回 raw_video 下所有视频文件的绝对路径（排序）。"""
    raw_video_dir = os.path.abspath(raw_video_dir)
    if not os.path.isdir(raw_video_dir):
        return []
    paths = []
    for name in sorted(os.listdir(raw_video_dir)):
        if name.lower().endswith(VIDEO_EXT):
            p = os.path.join(raw_video_dir, name)
            if os.path.isfile(p):
                paths.append(os.path.abspath(p))
    return paths


def startup_scan(raw_video_dir, project_root):
    """
    开机大扫除：将 raw_video 内所有存量视频作为一批送入工厂。
    先检测（质量+重复）→ 一封汇总邮件 → 再逐项询问放行/丢弃。
    """
    raw_video_dir = os.path.abspath(raw_video_dir)
    project_root = os.path.abspath(project_root)
    logger.info("开机自检 startup_scan: raw_video_dir=%s project_root=%s", raw_video_dir, project_root)
    paths = _list_video_paths(raw_video_dir)
    if not paths:
        logger.info("开机自检: 未发现存量视频")
        return
    logger.info("开机自检: 发现 %d 个存量视频，作为一批送入工厂", len(paths))
    print(f"\n🧹 [开机大扫除] 发现 {len(paths)} 个存量视频，作为一批送入工厂（检测完成后统一发一封邮件）...")
    try:
        run_smart_factory(video_paths=paths)
    except Exception as e:
        logger.exception("开机大扫除批处理异常: %s", e)
        print(f"❌ [开机大扫除] 批处理异常: {e}")
    logger.info("开机自检: 存量处理完毕，启动实时监控")
    print("🧹 [开机大扫除] 存量处理完毕，启动实时监控。\n")


class VideoFolderHandler(FileSystemEventHandler):
    """
    批处理模式：有新文件落地 → 等该文件稳定 → 再等 BATCH_WAIT_SECONDS 秒（期间若有新文件会重置）→
    将当前 raw_video 下所有视频作为一批送入工厂。先检测（质量+重复），再统一发一封邮件，再逐项询问。
    """

    def __init__(self, project_root, watch_path):
        self.project_root = os.path.abspath(project_root)
        self.watch_path = os.path.abspath(watch_path)
        self._batch_timer = None
        self._lock = threading.Lock()
        self._processing = False

    def _flush_batch(self):
        with self._lock:
            if self._processing:
                return
            paths = _list_video_paths(self.watch_path)
            if not paths:
                return
            self._processing = True
        try:
            print(f"\n📡 [保安报告] 本批共 {len(paths)} 个物料，送入工厂（检测完成后统一发一封邮件，再逐项询问）。")
            logger.info("批处理: 本批 %d 个文件送入工厂", len(paths))
            run_smart_factory(video_paths=paths)
        finally:
            with self._lock:
                self._processing = False
        print(f"\n{'=' * 50}\n🛡️  保安继续巡逻中...")

    def on_created(self, event):
        if event.is_directory:
            return
        file_path = event.src_path
        file_name = os.path.basename(file_path)
        if not file_name.lower().endswith(VIDEO_EXT):
            return
        abs_path = os.path.abspath(file_path)
        print(f"\n📡 [保安报告]: 监测到新物料 -> {file_name}，等待写入稳定并凑批...")
        _wait_file_stable(abs_path)
        with self._lock:
            if self._batch_timer:
                self._batch_timer.cancel()
            self._batch_timer = threading.Timer(BATCH_WAIT_SECONDS, self._flush_batch)
            self._batch_timer.daemon = True
            self._batch_timer.start()


if __name__ == "__main__":
    init_db()
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    WATCH_PATH = os.path.join(BASE_DIR, "raw_video")
    if not os.path.exists(WATCH_PATH):
        os.makedirs(WATCH_PATH)

    event_handler = VideoFolderHandler(BASE_DIR, WATCH_PATH)
    observer = Observer()
    observer.schedule(event_handler, WATCH_PATH, recursive=False)

    startup_scan(WATCH_PATH, BASE_DIR)

    print("🚀 [DataFactory 自动工厂启动]")
    print(f"📍 监控路径: {os.path.abspath(WATCH_PATH)}")
    print("🤖 运行模式: 批处理 → 先检测（质量+重复）→ 一封邮件 → 再逐项询问放行/丢弃")
    print("📢 厂长提示: 往 raw_video 丢视频，凑批后统一检测、统一发邮件、再逐个问你。")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 保安已安全下班。")
    observer.join()
