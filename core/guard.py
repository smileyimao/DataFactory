# core/guard.py — 持续监控 storage/raw，新视频落地即凑批送厂
# Watchdog 对 raw 目录做事件监听（创建/移入），非轮询；有新文件即触发等待稳定 + 凑批延时后送厂。
import os
import time
import threading
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config import config_loader
from engines import file_tools
from core import pipeline

logger = logging.getLogger(__name__)


def _list_videos(cfg: dict) -> list:
    paths = cfg.get("paths", {})
    raw = paths.get("raw_video", "")
    exts = tuple(cfg.get("ingest", {}).get("video_extensions", [".mp4", ".mov", ".avi", ".mkv"]))
    return file_tools.list_video_paths(raw, exts)


def startup_scan() -> None:
    """开机扫描：将 raw_video 下存量视频作为一批送入工厂。"""
    cfg = config_loader.load_config()
    paths = _list_videos(cfg)
    if not paths:
        logger.info("开机自检: 未发现存量视频")
        return
    logger.info("开机自检: 发现 %d 个存量视频，作为一批送入工厂", len(paths))
    print(f"\n🧹 [开机大扫除] 发现 {len(paths)} 个存量视频，作为一批送入工厂...")
    try:
        pipeline.run_smart_factory(video_paths=paths)
    except Exception as e:
        logger.exception("开机大扫除批处理异常: %s", e)
        print(f"❌ [开机大扫除] 批处理异常: {e}")
    print("🧹 [开机大扫除] 存量处理完毕，启动实时监控。\n")


def _is_video(name: str, exts: list) -> bool:
    return any(name.lower().endswith(ext) for ext in exts)


def _handle_new_file(handler_self, path: str):
    if not path or not os.path.isfile(path):
        return
    name = os.path.basename(path)
    exts = handler_self._cfg.get("ingest", {}).get("video_extensions", [".mp4", ".mov", ".avi", ".mkv"])
    if not _is_video(name, exts):
        return
    abs_path = os.path.abspath(path)
    print(f"\n📡 [保安报告]: 监测到新物料 -> {name}，等待写入稳定并凑批...")
    file_tools.wait_file_stable(abs_path, handler_self._stable_interval, handler_self._stable_min)
    with handler_self._lock:
        if handler_self._timer:
            handler_self._timer.cancel()
        handler_self._timer = threading.Timer(handler_self._batch_wait, handler_self._flush_batch)
        handler_self._timer.daemon = True
        handler_self._timer.start()


class VideoFolderHandler(FileSystemEventHandler):
    """
    持续监控 raw 目录：新文件创建或移入 -> 等写入稳定 -> 再等 batch_wait_seconds（期间新文件会重置计时）
    -> 将当前 raw 下全部视频送厂。Watchdog 由 OS 事件驱动，新视频产生即触发，无需轮询。
    """

    def __init__(self):
        self._cfg = config_loader.load_config()
        self._batch_wait = self._cfg.get("ingest", {}).get("batch_wait_seconds", 8)
        self._watch_path = self._cfg.get("paths", {}).get("raw_video", "")
        self._timer = None
        self._lock = threading.Lock()
        self._processing = False
        self._stable_interval = self._cfg.get("ingest", {}).get("file_stable_check_interval", 1)
        self._stable_min = self._cfg.get("ingest", {}).get("file_stable_min_seconds", 2)

    def _flush_batch(self):
        with self._lock:
            if self._processing:
                return
            paths = _list_videos(self._cfg)
            if not paths:
                return
            self._processing = True
        try:
            print(f"\n📡 [保安报告] 本批共 {len(paths)} 个物料，送入工厂...")
            logger.info("批处理: 本批 %d 个文件送入工厂", len(paths))
            pipeline.run_smart_factory(video_paths=paths)
        finally:
            with self._lock:
                self._processing = False
        print(f"\n{'=' * 50}\n🛡️  保安继续巡逻中...")

    def on_created(self, event):
        if event.is_directory:
            return
        _handle_new_file(self, event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        # 文件被移入 raw 时，dest_path 在监控目录内
        dest = getattr(event, "dest_path", None)
        if dest and os.path.dirname(os.path.abspath(dest)) == os.path.abspath(self._watch_path):
            _handle_new_file(self, dest)


def run_guard() -> None:
    """初始化 DB、创建 raw 目录、执行开机扫描、启动 Watchdog 持续监控 raw（新文件创建/移入即触发）。"""
    from engines import db_tools
    cfg = config_loader.load_config()
    db_path = cfg.get("paths", {}).get("db_file", "")
    if db_path:
        db_tools.init_db(db_path)
    watch_path = cfg.get("paths", {}).get("raw_video", "")
    if not os.path.exists(watch_path):
        os.makedirs(watch_path)
    startup_scan()
    print("🚀 [DataFactory 自动工厂启动]")
    print(f"📍 监控路径: {os.path.abspath(watch_path)}")
    print("🤖 运行模式: 批处理 → 先检测（质量+重复）→ 一封邮件 → 再逐项询问放行/丢弃")
    observer = Observer()
    handler = VideoFolderHandler()
    observer.schedule(handler, watch_path, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 保安已安全下班。")
    observer.join()
