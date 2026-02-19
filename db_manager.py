import sqlite3
import hashlib
import os

DB_NAME = "factory_admin.db"

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
    """【查账】：看看这个指纹之前是否量产成功过"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT batch_id FROM production_history WHERE fingerprint = ? AND status = 'SUCCESS'", (md5,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def record_production(batch_id, md5, pass_rate, status):
    """【登报】：把这次生产的结果记入档案"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO production_history (batch_id, fingerprint, pass_rate, status)
        VALUES (?, ?, ?, ?)
    ''', (batch_id, md5, pass_rate, status))
    conn.commit()
    conn.close()