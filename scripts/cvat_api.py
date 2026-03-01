#!/usr/bin/env python3
# scripts/cvat_api.py — 本地 CVAT API 封装，所有 CVAT 操作通过此文件
"""
配置从 .env 读取：
  CVAT_LOCAL_URL=http://localhost:8080
  CVAT_LOCAL_USERNAME=admin
  CVAT_LOCAL_PASSWORD=xxx

用法（作为模块）:
  from scripts.cvat_api import create_project, create_task, upload_annotations, get_task_url
"""
import os
import time
from typing import List, Optional

try:
    import requests
except ImportError:
    requests = None

# 从 .env 加载
try:
    from dotenv import load_dotenv
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_base, ".env"))
except ImportError:
    pass

CVAT_URL = os.environ.get("CVAT_LOCAL_URL", "http://localhost:8080").rstrip("/")
CVAT_USER = os.environ.get("CVAT_LOCAL_USERNAME", "admin")
CVAT_PASS = os.environ.get("CVAT_LOCAL_PASSWORD", "")


def _get_session() -> Optional["requests.Session"]:
    """获取带认证的 session。先 login 获取 token。"""
    if not requests:
        return None
    sess = requests.Session()
    r = sess.post(
        f"{CVAT_URL}/api/auth/login",
        json={"username": CVAT_USER, "password": CVAT_PASS},
        timeout=30,
    )
    if r.status_code != 200:
        return None
    data = r.json()
    key = data.get("key") or data.get("token")
    if not key:
        return None
    sess.headers["Authorization"] = f"Token {key}"
    return sess


def create_project(name: str, labels: Optional[List[dict]] = None) -> Optional[int]:
    """
    创建 Project。labels 格式 [{"name": "car", "type": "rectangle"}, ...]。
    返回 project_id，失败返回 None。
    """
    if not requests:
        return None
    sess = _get_session()
    if not sess:
        return None
    payload = {"name": name}
    if labels:
        payload["labels"] = labels
    r = sess.post(f"{CVAT_URL}/api/projects", json=payload, timeout=30)
    sess.close()
    if r.status_code not in (200, 201):
        return None
    data = r.json()
    return data.get("id")


def create_task(project_id: Optional[int], name: str) -> Optional[int]:
    """
    创建 Task。project_id 可为 None（无 Project）。
    返回 task_id，失败返回 None。
    """
    if not requests:
        return None
    sess = _get_session()
    if not sess:
        return None
    payload = {"name": name}
    if project_id is not None:
        payload["project_id"] = project_id
    r = sess.post(f"{CVAT_URL}/api/tasks", json=payload, timeout=30)
    sess.close()
    if r.status_code not in (200, 201):
        return None
    data = r.json()
    return data.get("id")


def upload_images_from_zip(task_id: int, zip_path: str) -> bool:
    """
    直接上传 for_cvat.zip 到 Task。更高效。
    返回是否成功。
    """
    if not requests or not os.path.isfile(zip_path):
        return False
    sess = _get_session()
    if not sess:
        return False
    with open(zip_path, "rb") as f:
        r = sess.post(
            f"{CVAT_URL}/api/tasks/{task_id}/data",
            files={"client_files": (os.path.basename(zip_path), f, "application/zip")},
            data={"image_quality": 75},
            timeout=600,
        )
    sess.close()
    if r.status_code not in (200, 201, 202):
        return False
    # 等待处理完成
    for _ in range(120):
        time.sleep(2)
        s = _get_session()
        if s:
            try:
                r2 = s.get(f"{CVAT_URL}/api/tasks/{task_id}/status", timeout=10)
                s.close()
                if r2.status_code == 200:
                    st = r2.json()
                    if st.get("state") == "Finished":
                        return True
                    if st.get("state") == "Failed":
                        return False
            except Exception:
                pass
    return True


def upload_annotations(task_id: int, xml_path: str, format_name: str = "CVAT for images 1.1") -> bool:
    """
    上传标注。xml_path 为 for_cvat_native.zip（含 annotations.xml）。
    返回是否成功。
    """
    if not requests or not os.path.isfile(xml_path):
        return False
    sess = _get_session()
    if not sess:
        return False
    with open(xml_path, "rb") as f:
        r = sess.post(
            f"{CVAT_URL}/api/tasks/{task_id}/annotations",
            params={"format": format_name},
            files={"annotation_file": (os.path.basename(xml_path), f, "application/zip")},
            timeout=300,
        )
    sess.close()
    return r.status_code in (200, 201, 202)


def get_task_url(task_id: int) -> str:
    """返回 Task 的 Web URL。"""
    return f"{CVAT_URL}/tasks/{task_id}"


def auto_cvat_upload(
    for_labeling_dir: str,
    for_cvat_zip: str,
    for_cvat_native_zip: str,
    task_name: str = "DataFactory",
    project_name: str = "DataFactory",
) -> Optional[str]:
    """
    全自动：创建 Project → Task → 上传图片 → 上传标注。
    返回 Task URL，失败返回 None。
    """
    labels = [
        {"name": n, "type": "rectangle"}
        for n in ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck"]
    ]
    pid = create_project(project_name, labels)
    tid = create_task(pid, task_name)
    if tid is None:
        return None
    if not upload_images_from_zip(tid, for_cvat_zip):
        return None
    if os.path.isfile(for_cvat_native_zip):
        upload_annotations(tid, for_cvat_native_zip)
    return get_task_url(tid)


if __name__ == "__main__":
    import sys
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fl = os.path.join(base, "storage", "for_labeling")
    z1 = os.path.join(fl, "for_cvat.zip")
    z2 = os.path.join(fl, "for_cvat_native.zip")
    url = auto_cvat_upload(fl, z1, z2)
    if url:
        print(f"✅ CVAT Task: {url}")
        sys.exit(0)
    print("❌ CVAT 上传失败，请检查 CVAT 是否运行、.env 中 CVAT_LOCAL_* 配置")
    sys.exit(1)
