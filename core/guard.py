# core/guard.py — 持续监控 raw 目录，新视频落地即凑批送厂
# Watchdog 事件监听 + 轮询兜底（macOS 上 Finder 复制、iCloud 同步等可能漏检）。
import os
import time
import threading
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config import config_loader
from utils import file_tools
from core import pipeline

logger = logging.getLogger(__name__)

# 轮询兜底间隔（秒），0 表示不轮询
POLL_INTERVAL_DEFAULT = 30


def _list_raw_media(cfg: dict) -> list:
    """扫描 raw 目录（递归），按 content_mode 返回图片或视频路径。"""
    from core import ingest
    return ingest.get_video_paths(cfg)


def startup_scan(cfg: dict = None) -> None:
    """开机扫描：将 raw_video 下存量视频作为一批送入工厂。cfg 未传则从 config_loader 加载。"""
    if cfg is None:
        cfg = config_loader.load_config()
    paths = _list_raw_media(cfg)
    if not paths:
        logger.info("开机自检: 未发现存量视频")
        return
    logger.info("开机自检: 发现 %d 个存量视频，作为一批送入工厂", len(paths))
    print(f"\n🧹 [开机大扫除] 发现 {len(paths)} 个存量视频，作为一批送入工厂...")
    try:
        pipeline.run_smart_factory(cfg=cfg, video_paths=paths)
    except Exception as e:
        logger.exception("开机大扫除批处理异常: %s", e)
        print(f"❌ [开机大扫除] 批处理异常: {e}")
    print("🧹 [开机大扫除] 存量处理完毕，启动实时监控。\n")


def _get_media_extensions(cfg: dict) -> tuple:
    """按 content_mode 返回对应扩展名。"""
    from config import config_loader
    mode = config_loader.get_content_mode(cfg)
    ig = cfg.get("ingest", {})
    if mode == "image":
        return tuple(ig.get("image_extensions", [".jpg", ".jpeg", ".png"]))
    return tuple(ig.get("video_extensions", [".mp4", ".mov", ".avi", ".mkv"]))


def _is_media(name: str, exts: tuple) -> bool:
    return any(name.lower().endswith(ext) for ext in exts)


def _handle_new_file(handler_self, path: str):
    if not path or not os.path.isfile(path):
        return
    name = os.path.basename(path)
    exts = _get_media_extensions(handler_self._cfg)
    if not _is_media(name, exts):
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

    def __init__(self, cfg: dict = None):
        self._cfg = cfg if cfg is not None else config_loader.load_config()
        self._batch_wait = self._cfg.get("ingest", {}).get("batch_wait_seconds", 8)
        self._watch_path = self._cfg.get("paths", {}).get("raw_video", "")
        self._timer = None
        self._lock = threading.Lock()
        self._processing = False
        self._pending_flush = False  # 产线加工期间有新视频触发 flush 时，本批结束后需再扫一次
        self._stable_interval = self._cfg.get("ingest", {}).get("file_stable_check_interval", 1)
        self._stable_min = self._cfg.get("ingest", {}).get("file_stable_min_seconds", 2)

    def _flush_batch(self):
        with self._lock:
            if self._processing:
                self._pending_flush = True
                logger.info("产线加工中，新物料已登记，本批结束后将自动再扫")
                return
            paths = _list_raw_media(self._cfg)
            if not paths:
                return
            self._processing = True
        try:
            print(f"\n📡 [保安报告] 本批共 {len(paths)} 个物料，送入工厂...")
            logger.info("批处理: 本批 %d 个文件送入工厂", len(paths))
            pipeline.run_smart_factory(cfg=self._cfg, video_paths=paths)
        finally:
            with self._lock:
                self._processing = False
                need_retry = self._pending_flush
                self._pending_flush = False
            if need_retry:
                print("\n📡 [保安报告] 产线加工期间有新物料写入，立即再扫 raw 目录...")
                logger.info("产线加工期间有新物料，立即再扫 raw 目录")
                self._flush_batch()
        print(f"\n{'=' * 50}\n🛡️  保安继续巡逻中...")

    def on_created(self, event):
        if event.is_directory:
            return
        _handle_new_file(self, event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        # 文件被移入 raw 或其子目录时触发
        dest = getattr(event, "dest_path", None)
        if not dest or not os.path.isfile(dest):
            return
        watch_abs = os.path.abspath(self._watch_path)
        dest_abs = os.path.abspath(dest)
        try:
            if os.path.commonpath([watch_abs, dest_abs]) == watch_abs:
                _handle_new_file(self, dest)
        except ValueError:
            pass


def _poll_loop(handler: "VideoFolderHandler", interval: float, stop_event: threading.Event) -> None:
    """轮询兜底：定期扫 raw 目录，Watchdog 漏检时仍能发现新视频。"""
    while not stop_event.wait(timeout=interval):
        try:
            handler._flush_batch()
        except Exception as e:
            logger.exception("轮询兜底异常: %s", e)


def run_guard(cfg: dict = None, stop_event: threading.Event = None) -> None:
    """
    初始化 DB、创建 raw 目录、执行开机扫描、启动 Watchdog + 轮询兜底。
    cfg 未传则从 config_loader 加载；stop_event 传入时主循环会检查并在 set 后退出（测试用）。
    """
    from engines import db_tools

    if cfg is None:
        cfg = config_loader.load_config()
    db_path = cfg.get("paths", {}).get("db_url", "")
    if db_path:
        if not db_tools.init_db(db_path):
            print("❌ 数据库初始化失败，请检查 DATABASE_URL 配置。")
            import sys
            sys.exit(1)
    watch_path = cfg.get("paths", {}).get("raw_video", "")
    if not os.path.exists(watch_path):
        os.makedirs(watch_path)
    config_loader.init_storage_from_config(cfg)
    startup_scan(cfg)
    print("🚀 [DataFactory 自动工厂启动]")
    print(f"📍 监控路径: {os.path.abspath(watch_path)}")
    print("🤖 运行模式: 批处理 → 先检测（质量+重复）→ 一封邮件 → 再逐项询问放行/丢弃")
    observer = Observer()
    handler = VideoFolderHandler(cfg)
    observer.schedule(handler, watch_path, recursive=True)
    observer.start()

    poll_interval = cfg.get("ingest", {}).get("poll_interval_seconds", POLL_INTERVAL_DEFAULT)
    poll_stop = threading.Event()
    poll_thread = None
    if poll_interval and poll_interval > 0:
        poll_thread = threading.Thread(
            target=_poll_loop,
            args=(handler, float(poll_interval), poll_stop),
            daemon=True,
            name="guard_poll",
        )
        poll_thread.start()
        logger.info("轮询兜底已启动，间隔 %s 秒", poll_interval)
        print(f"📡 轮询兜底: 每 {poll_interval}s 扫一次 raw（Watchdog 漏检时仍能发现）")

    try:
        while True:
            if stop_event and stop_event.is_set():
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        poll_stop.set()
        observer.stop()
        print("\n👋 保安已安全下班。")
    observer.join()
