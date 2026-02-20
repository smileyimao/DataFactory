import sqlite3
import hashlib
import os
import logging

logger = logging.getLogger(__name__)

# 数据库固定放在项目根目录，不随当前工作目录变化
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(_BASE_DIR, "factory_admin.db")

def init_db():
    """初始化档案馆：建立指纹表和生产记录表"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 建立量产记录表：不仅记ID，还要记指纹
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS production_history (
            batch_id TEXT PRIMARY KEY,
            fingerprint TEXT,
            pass_rate REAL,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_file_md5(file_path):
    """【指纹扫描仪】：算出文件的唯一身份证号"""
    if not os.path.exists(file_path):
        return ""
    hasher = hashlib.md5()
    file_size = os.path.getsize(file_path)
    try:
        with open(file_path, 'rb') as f:
            # 如果文件很大（>2MB），只读头尾，速度极快
            if file_size > 2 * 1024 * 1024:
                hasher.update(f.read(1024 * 1024)) # 读开头1MB
                f.seek(-1024 * 1024, 2)            # 跳到末尾
                hasher.update(f.read(1024 * 1024)) # 读末尾1MB
            else:
                hasher.update(f.read())            # 小文件全读
        return hasher.hexdigest()
    except Exception as e:
        print(f"❌ 指纹采集失败: {e}")
        return ""

def check_reproduce(md5):
    """【查账】：看看这个指纹之前是否量产成功过，返回 batch_id 或 None"""
    info = get_reproduce_info(md5)
    return info["batch_id"] if info else None


def get_reproduce_info(md5):
    """
    【查账详情】：若该指纹曾量产成功，返回批次与处理时间，供邮件正文使用。
    返回 None 或 {"batch_id": str, "created_at": str}，created_at 为可读时间。
    """
    if not md5:
        return None
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT batch_id, created_at FROM production_history WHERE fingerprint = ? AND status = 'SUCCESS'",
        (md5,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    batch_id, created_at = row
    logger.info("数据库查重命中: fingerprint 对应批次=%s 处理时间=%s", batch_id, created_at)
    # 将数据库时间转为可读格式（若已是 str 则尽量解析）
    try:
        if isinstance(created_at, str) and " " in created_at:
            created_at_str = created_at[:19].replace("T", " ")
        else:
            created_at_str = str(created_at)[:19] if created_at else "未知时间"
    except Exception:
        created_at_str = str(created_at) if created_at else "未知时间"
    return {"batch_id": batch_id, "created_at": created_at_str}

def record_production(batch_id, md5, pass_rate, status, created_at=None):
    """【登报】：把这次生产的结果记入档案。created_at 为多伦多本地时间字符串（YYYY-MM-DD HH:MM:SS），不传则用数据库当前时间。"""
    if created_at is None:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            created_at = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
        except ImportError:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO production_history (batch_id, fingerprint, pass_rate, status, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (batch_id, md5, pass_rate, status, created_at))
    conn.commit()
    conn.close()