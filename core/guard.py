# core/guard.py — 持续监控 raw 目录，新视频落地即凑批送厂
# Watchdog 事件监听 + 轮询兜底（macOS 上 Finder 复制、iCloud 同步等可能漏检）。
import json
import os
import time
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
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


def _check_stale_markers(cfg: dict) -> None:
    """开机自检：检查 storage/in_progress/ 下是否有上次断电/崩溃遗留的未完成标记。
    发现残留标记时记录 CRITICAL 日志，提示运维参考 OPS-001 手册确认数据一致性。
    """
    import json
    marker_dir = os.path.join(config_loader.get_base_dir(), "storage", "in_progress")
    if not os.path.isdir(marker_dir):
        return
    stale = [f for f in os.listdir(marker_dir) if f.endswith(".json")]
    if not stale:
        return
    logger.critical(
        "⚡ 发现 %d 个未完成的 Batch 标记（可能由断电或崩溃引起）: %s — "
        "请参考 Knowledge/Observe/OPS-001-lineage-mismatch.md 确认归档与 DB 一致性",
        len(stale),
        [s.replace(".json", "") for s in stale],
    )


def startup_scan(cfg: dict = None) -> None:
    """开机扫描：将 raw_video 下存量视频作为一批送入工厂。cfg 未传则从 config_loader 加载。"""
    if cfg is None:
        cfg = config_loader.load_config()
    _check_stale_markers(cfg)
    paths = _list_raw_media(cfg)
    if not paths:
        logger.info("开机自检: 未发现存量视频")
        return
    logger.info("开机大扫除: 发现 %d 个存量视频，作为一批送入工厂", len(paths))
    try:
        pipeline.run_smart_factory(cfg=cfg, video_paths=paths)
    except Exception as e:
        logger.exception("开机大扫除批处理异常: %s", e)
    logger.info("开机大扫除: 存量处理完毕，启动实时监控")


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
    logger.info("保安报告: 监测到新物料 %s，等待写入稳定并凑批", name)
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

    def __init__(self, cfg: dict = None, auto_cvat: bool = False):
        self._cfg = cfg if cfg is not None else config_loader.load_config()
        self._auto_cvat = auto_cvat
        self._batch_wait = self._cfg.get("ingest", {}).get("batch_wait_seconds", 8)
        self._watch_path = self._cfg.get("paths", {}).get("raw_video", "")
        self._timer = None
        self._lock = threading.Lock()
        self._processing = False
        self._pending_flush = False  # 产线加工期间有新视频触发 flush 时，本批结束后需再扫一次
        self._stable_interval = self._cfg.get("ingest", {}).get("file_stable_check_interval", 1)
        self._stable_min = self._cfg.get("ingest", {}).get("file_stable_min_seconds", 2)

    def _flush_batch(self):
        while True:
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
                logger.info("批处理: 本批 %d 个文件送入工厂", len(paths))
                pipeline.run_smart_factory(cfg=self._cfg, video_paths=paths)
                if self._auto_cvat:
                    try:
                        from labeling import annotation_upload
                        cvat_url = annotation_upload.upload(self._cfg)
                        if cvat_url:
                            print(f"  [CVAT]    Task created: {cvat_url}", flush=True)
                        else:
                            print("  [CVAT]    Upload skipped (no frames or CVAT not configured)", flush=True)
                    except Exception as e:
                        logger.warning("CVAT 自动上传失败: %s", e)
            finally:
                with self._lock:
                    self._processing = False
                    need_retry = self._pending_flush
                    self._pending_flush = False
            if not need_retry:
                break
            logger.info("产线加工期间有新物料，立即再扫 raw 目录")
        logger.info("保安继续巡逻中")

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


def _start_health_server(port: int, start_time: float) -> None:
    """
    启动轻量 HTTP /health 端点（守护线程），供 Kubernetes liveness probe 或监控系统使用。
    GET /health → 200 JSON {"status": "ok", "uptime_sec": N}
    端口通过 ingest.health_port 配置，0 或未配置则不启动。
    """
    if not port:
        return

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                body = json.dumps(
                    {"status": "ok", "uptime_sec": round(time.time() - start_time, 1)},
                    ensure_ascii=False,
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):  # 静默 access log
            pass

    def _serve():
        try:
            srv = HTTPServer(("0.0.0.0", port), _Handler)
            srv.serve_forever()
        except Exception as e:
            logger.warning("健康检查端点启动失败 (port=%s): %s", port, e)

    t = threading.Thread(target=_serve, daemon=True, name="guard_health")
    t.start()
    logger.info("健康检查端点已启动: http://0.0.0.0:%s/health", port)


def _poll_loop(handler: "VideoFolderHandler", interval: float, stop_event: threading.Event) -> None:
    """轮询兜底：定期扫 raw 目录，Watchdog 漏检时仍能发现新视频。"""
    while not stop_event.wait(timeout=interval):
        try:
            handler._flush_batch()
        except Exception as e:
            logger.exception("轮询兜底异常: %s", e)


def run_guard(cfg: dict = None, stop_event: threading.Event = None, auto_cvat: bool = False) -> None:
    """
    初始化 DB、创建 raw 目录、执行开机扫描、启动 Watchdog + 轮询兜底。
    cfg 未传则从 config_loader 加载；stop_event 传入时主循环会检查并在 set 后退出（测试用）。
    """
    from db import db_tools

    if cfg is None:
        cfg = config_loader.load_config()
    db_path = cfg.get("paths", {}).get("db_url", "")
    if db_path:
        if not db_tools.init_db(db_path):
            logger.error("数据库初始化失败，请检查 DATABASE_URL 配置")
            import sys
            sys.exit(1)
    watch_path = cfg.get("paths", {}).get("raw_video", "")
    if not os.path.exists(watch_path):
        os.makedirs(watch_path)
    config_loader.init_storage_from_config(cfg)
    _guard_start_time = time.time()
    health_port = cfg.get("ingest", {}).get("health_port", 0)
    _start_health_server(health_port, _guard_start_time)
    startup_scan(cfg)
    logger.info("DataFactory 自动工厂启动 监控路径=%s", os.path.abspath(watch_path))
    observer = Observer()
    handler = VideoFolderHandler(cfg, auto_cvat=auto_cvat)
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
        logger.info("保安已安全下班")
    observer.join()
