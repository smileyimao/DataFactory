# dashboard/app.py — 厂长中控台：Web 复核界面
"""
启动: python -m dashboard.app  或  uvicorn dashboard.app:app --host 0.0.0.0 --port 8765
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.chdir(BASE_DIR)

from config import config_loader
config_loader.set_base_dir(BASE_DIR)

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import pending_queue

app = FastAPI(title="DataFactory 厂长中控台", version="1.0")

QUEUE_DIR = os.path.join(BASE_DIR, "storage", "pending_review")
THUMBS_DIR = os.path.join(QUEUE_DIR, "thumbs")


@app.get("/", response_class=HTMLResponse)
def index():
    """中控台首页。"""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.isfile(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>厂长中控台</h1><p>static/index.html 未找到</p>"


@app.get("/api/pending")
def get_pending():
    """获取待复核列表。"""
    items = pending_queue.get_all(BASE_DIR)
    return {"items": items, "count": len(items)}


@app.post("/api/pending/{item_id}/approve")
def approve_one(item_id: str):
    """单项放行。"""
    ok, err = pending_queue.apply_decision(BASE_DIR, item_id, "approve")
    if not ok:
        raise HTTPException(status_code=404, detail=err or "操作失败")
    return {"ok": True}


@app.post("/api/pending/{item_id}/reject")
def reject_one(item_id: str):
    """单项拒绝。"""
    ok, err = pending_queue.apply_decision(BASE_DIR, item_id, "reject")
    if not ok:
        raise HTTPException(status_code=404, detail=err or "操作失败")
    return {"ok": True}


class BatchBody(BaseModel):
    ids: list[str]


@app.post("/api/pending/batch/approve")
def batch_approve(body: BatchBody):
    """批量放行。"""
    ok_count, failed = pending_queue.apply_batch_decision(BASE_DIR, body.ids, "approve")
    return {"ok_count": ok_count, "failed": failed}


@app.post("/api/pending/batch/reject")
def batch_reject(body: BatchBody):
    """批量拒绝。"""
    ok_count, failed = pending_queue.apply_batch_decision(BASE_DIR, body.ids, "reject")
    return {"ok_count": ok_count, "failed": failed}


@app.get("/thumbs/{filename}")
def get_thumbnail(filename: str):
    """缩略图静态文件。"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.abspath(os.path.join(THUMBS_DIR, filename))
    thumbs_abs = os.path.abspath(THUMBS_DIR)
    if not os.path.isfile(path) or not (path.startswith(thumbs_abs + os.sep) or path == thumbs_abs):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")


def main():
    import uvicorn
    cfg = config_loader.load_config()
    port = cfg.get("paths", {}).get("dashboard_port") or os.environ.get("DASHBOARD_PORT", "8765")
    port = int(port)
    print(f"🏭 厂长中控台: http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
