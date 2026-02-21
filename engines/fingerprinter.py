# engines/fingerprinter.py — MD5 指纹，只干活不决策
import hashlib
import os


def compute(file_path: str) -> str:
    """计算文件 MD5，大文件头尾采样。返回空字符串表示失败。"""
    if not os.path.exists(file_path):
        return ""
    hasher = hashlib.md5()
    file_size = os.path.getsize(file_path)
    try:
        with open(file_path, "rb") as f:
            if file_size > 2 * 1024 * 1024:
                hasher.update(f.read(1024 * 1024))
                f.seek(-1024 * 1024, 2)
                hasher.update(f.read(1024 * 1024))
            else:
                hasher.update(f.read())
        return hasher.hexdigest()
    except Exception:
        return ""
