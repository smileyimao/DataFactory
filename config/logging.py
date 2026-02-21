# config/logging.py — 应用日志配置（多伦多时区、按日文件）
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

LOGS_DIR = "logs"


class TorontoFormatter(logging.Formatter):
    """日志时间使用 America/Toronto 时区。"""

    def formatTime(self, record, datefmt=None):
        ct = datetime.fromtimestamp(record.created, tz=ZoneInfo("America/Toronto"))
        if datefmt:
            return ct.strftime(datefmt)
        return ct.strftime("%Y-%m-%d %H:%M:%S")


def setup_logging(base_dir: str) -> None:
    """
    在 base_dir 下创建 logs/，配置文件日志：INFO 及以上写入 logs/factory_[日期].log。
    格式：[时间] [级别] [模块] - 消息内容。
    """
    base_dir = os.path.abspath(base_dir)
    log_dir = os.path.join(base_dir, LOGS_DIR)
    os.makedirs(log_dir, exist_ok=True)
    date_str = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"factory_{date_str}.log")

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    log_file_abs = os.path.abspath(log_file)
    for h in root.handlers:
        if getattr(h, "baseFilename", None) == log_file_abs:
            return
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(TorontoFormatter("[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s"))
    root.addHandler(fh)
