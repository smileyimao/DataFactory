#!/usr/bin/env python3
# scripts/cvat_upload_annotations.py — 通过 CVAT API 将标注上传到指定 Task
"""
用法:
  python scripts/cvat_upload_annotations.py <task_id>
  python scripts/cvat_upload_annotations.py 2054061 --zip storage/for_labeling/for_cvat_native.zip

格式：CVAT for images 1.1（原生格式，与 CVAT 导出一致）
需在 .env 配置 CVAT_URL、CVAT_TOKEN
"""
import argparse
import os
import sys

try:
    import requests
except ImportError:
    requests = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)

FORMATS = {
    "cvat": ("CVAT 1.1", "storage/for_labeling/for_cvat_native.zip"),
}


def _upload_via_sdk(url: str, token: str, task_id: int, zip_path: str, format_name: str) -> bool:
    """使用 cvat_sdk 上传（推荐，云版兼容性好）"""
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass
    try:
        from cvat_sdk.core.client import Client, Config, AccessTokenCredentials
    except ImportError:
        return False

    base = url if "://" in url else f"https://{url}"
    with Client(base, config=Config(verify_ssl=False)) as client:
        client.login(AccessTokenCredentials(token))
        task = client.tasks.retrieve(task_id)
        task.import_annotations(format_name=format_name, filename=zip_path)
    return True


def _list_formats(url: str, token: str) -> int:
    """获取并打印 CVAT 支持的标注格式（用于确认 format_name）"""
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass
    try:
        from cvat_sdk.core.client import Client, Config, AccessTokenCredentials
    except ImportError:
        pass
    else:
        base = url if "://" in url else f"https://{url}"
        with Client(base, config=Config(verify_ssl=False)) as client:
            client.login(AccessTokenCredentials(token))
            data, _ = client.api_client.server_api.retrieve_annotation_formats()
            names = []
            for fmt in getattr(data, "importers", []) or []:
                n = getattr(fmt, "name", None) or (fmt.get("name") if isinstance(fmt, dict) else str(fmt))
                if n:
                    names.append(n)
            return _print_formats(names)

    if requests:
        r = requests.get(
            f"{url.rstrip('/')}/api/server/annotation/formats",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"❌ 获取格式列表失败: {r.status_code} {r.text[:200]}")
            return 1
        data = r.json()
        names = []
        imp = data.get("importers", data.get("import", data if isinstance(data, list) else []))
        for fmt in imp or []:
            n = fmt.get("name", fmt) if isinstance(fmt, dict) else getattr(fmt, "name", str(fmt))
            if isinstance(n, str):
                names.append(n)
        return _print_formats(names)

    print("请安装 cvat-sdk 或 requests")
    return 1


def _print_formats(names: list[str]) -> int:
    print("CVAT 支持的导入格式（CVAT 相关）：")
    for n in sorted(names):
        if "cvat" in n.lower() or "images" in n.lower():
            print(f"  → {n}")
    print("\n全部导入格式：")
    for n in sorted(names):
        print(f"  {n}")
    return 0


def _upload_via_requests(url: str, token: str, task_id: int, zip_path: str, format_name: str) -> tuple[int, str]:
    """使用 requests 直接调用 REST API"""
    headers = {"Authorization": f"Bearer {token}"}
    api_url = f"{url.rstrip('/')}/api/tasks/{task_id}/annotations/"
    params = {"format": format_name}
    with open(zip_path, "rb") as f:
        r = requests.post(
            api_url,
            params=params,
            headers=headers,
            files={"annotation_file": (os.path.basename(zip_path), f, "application/zip")},
            timeout=120,
        )
    return r.status_code, (r.text or "")[:500]


def main():
    # macOS 上 python.org 安装的 Python 可能缺少根证书，尽早设置 certifi
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BASE_DIR, ".env"))
    except ImportError:
        pass

    url = os.environ.get("CVAT_URL", "").rstrip("/")
    token = os.environ.get("CVAT_TOKEN", "")
    if not url or not token:
        print("请设置 CVAT_URL 和 CVAT_TOKEN（.env）")
        return 1

    parser = argparse.ArgumentParser(description="通过 CVAT API 上传标注到指定 Task")
    parser.add_argument("task_id", type=int, nargs="?", default=None, help="Task ID（URL 中 /tasks/ 后的数字）")
    parser.add_argument("--format", type=str, choices=list(FORMATS), default="cvat", help="CVAT 原生格式")
    parser.add_argument("--zip", type=str, default="", help="zip 路径（默认按 --format 选择）")
    parser.add_argument("--list-formats", action="store_true", help="列出 CVAT 支持的标注格式名称后退出")
    args = parser.parse_args()

    if args.list_formats:
        return _list_formats(url, token)

    if args.task_id is None:
        parser.error("请提供 task_id，或使用 --list-formats 查看支持的格式")

    fmt_name, default_zip = FORMATS[args.format]
    zip_path = args.zip or default_zip
    zip_path = zip_path if os.path.isabs(zip_path) else os.path.join(BASE_DIR, zip_path)
    if not os.path.isfile(zip_path):
        print(f"❌ 文件不存在: {zip_path}")
        return 1

    # 优先用 cvat_sdk（云版 app.cvat.ai 常对 REST 返回 405，SDK 能正确处理）
    if _upload_via_sdk(url, token, args.task_id, zip_path, fmt_name):
        print("✅ 标注上传已提交（cvat_sdk）")
        return 0

    # 回退到 requests
    if requests is None:
        print("请安装: pip install requests 或 pip install cvat-sdk")
        return 1
    code, text = _upload_via_requests(url, token, args.task_id, zip_path, fmt_name)
    if code in (200, 201, 202):
        print(f"✅ 标注上传已提交 (status={code})")
        return 0
    print(f"❌ 失败: {code}")
    print(text)
    print("\n提示: 若为 405，可安装 cvat-sdk 后重试: pip install cvat-sdk")
    return 1


if __name__ == "__main__":
    sys.exit(main())
