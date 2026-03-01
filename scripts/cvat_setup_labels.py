#!/usr/bin/env python3
# scripts/cvat_setup_labels.py — 通过 CVAT API 创建 Project 并添加 27 个 label，或输出手动添加清单
"""
用法:
  python scripts/cvat_setup_labels.py --print     # 仅打印 27 个 label，供手动复制
  python scripts/cvat_setup_labels.py             # 通过 API 创建（需 CVAT_URL + CVAT_TOKEN）

  API 方式需在 .env 配置: CVAT_URL, CVAT_TOKEN
  获取 Token: CVAT 登录 → 右上角头像 → Auth Token → Generate
"""
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BASE_DIR)

LABELS = [
    "0", "1", "2", "3", "4", "5", "6", "7", "777D", "8", "9",
    "A", "G", "H", "I", "L", "N", "O", "S", "T", "U",
    "company", "dumping_soil", "empty_load", "full_load", "mining_truck", "tail_number",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", help="仅打印 label 列表，供 CVAT 手动添加")
    parser.add_argument("--project-id", type=int, default=0, help="已有 Project 的 ID，往其中添加 27 个 label（项目数已满时用）")
    args = parser.parse_args()

    if args.print:
        print("在 CVAT Project 的 Labels 中按顺序添加以下 27 个（点 Add label 逐个添加）：")
        print()
        for i, n in enumerate(LABELS):
            print(f"  {i+1}. {n}")
        print()
        print("顺序必须一致，否则 YOLO class_id 会错位。")
        return 0

    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BASE_DIR, ".env"))
    except ImportError:
        pass

    url = os.environ.get("CVAT_URL", "").rstrip("/")
    token = os.environ.get("CVAT_TOKEN", "")
    if not url or not token:
        print("请设置 CVAT_URL 和 CVAT_TOKEN，或使用 --print 查看手动添加清单")
        return 1

    try:
        import requests
    except ImportError:
        print("请安装: pip install requests")
        return 1

    headers = {"Authorization": f"Bearer {token}"}

    if args.project_id:
        r = requests.patch(
            f"{url}/api/projects/{args.project_id}",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "labels": [
                    {"name": n, "type": "rectangle", "attributes": []}
                    for n in LABELS
                ]
            },
            timeout=30,
        )
        if r.status_code in (200, 201):
            print(f"✅ 已向 Project {args.project_id} 添加 27 个 label")
            print(f"   → {url}/projects/{args.project_id}")
            return 0
        print(f"❌ 失败: {r.status_code} {r.text[:400]}")
        return 1

    r = requests.post(
        f"{url}/api/projects",
        headers=headers,
        json={"name": "Mining Truck QC", "labels": [{"name": n} for n in LABELS]},
        timeout=30,
    )
    if r.status_code in (200, 201):
        pid = r.json().get("id")
        print(f"✅ Project 已创建: Mining Truck QC (id={pid})")
        print(f"   → {url}/projects/{pid}")
        return 0
    if r.status_code == 403 and "maximum" in (r.text or "").lower():
        print("❌ 项目数已达上限。请用已有 Project：")
        print("   1. 打开 CVAT Projects 页面，找到要用的 Project，记下 URL 中的 id（如 /projects/372531）")
        print("   2. 运行: python scripts/cvat_setup_labels.py --project-id 372531")
        return 1
    print(f"❌ 失败: {r.status_code}")
    print((r.text or "")[:600])
    if r.status_code == 401:
        print("\n提示: 401 多为 token 无效，请到 CVAT Profile → Auth Token 重新 Generate，更新 .env 的 CVAT_TOKEN")
    return 1


if __name__ == "__main__":
    sys.exit(main())
