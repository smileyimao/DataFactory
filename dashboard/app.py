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
_CFG = config_loader.load_config()

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import pending_queue

app = FastAPI(title="DataFactory 厂长中控台", version="1.0")

THUMBS_DIR = config_loader.get_pending_thumbs_dir(_CFG)


@app.get("/api/metrics")
def get_metrics():
    """P2 简单 counters 快照，便于监控与告警。"""
    from engines import metrics
    return {"counters": metrics.get_all()}


@app.get("/api/health")
def health_check():
    """P0 健康检查：DB 连通性、关键目录可写、配置完整性。"""
    from config import config_loader
    checks = {}
    paths = _CFG.get("paths", {})
    db_path = paths.get("db_file")
    if db_path:
        try:
            import sqlite3
            conn = sqlite3.connect(db_path, timeout=5)
            conn.execute("SELECT 1")
            conn.close()
            checks["db"] = "ok"
        except Exception as e:
            checks["db"] = f"error: {e}"
    else:
        checks["db"] = "not_configured"
    for key in ("data_warehouse", "rejected_material", "pending_review"):
        p = paths.get(key)
        if p:
            try:
                os.makedirs(p, exist_ok=True)
                probe = os.path.join(p, ".health_probe")
                with open(probe, "w") as f:
                    f.write("")
                os.remove(probe)
                checks[key] = "ok"
            except OSError as e:
                checks[key] = f"error: {e}"
        else:
            checks[key] = "not_configured"
    errs = config_loader.validate_config(_CFG)
    checks["config"] = "ok" if not errs else f"errors: {errs}"
    unhealthy = [k for k, v in checks.items() if v not in ("ok", "not_configured")]
    status = 200 if not unhealthy else 503
    body = {"status": "healthy" if status == 200 else "unhealthy", "checks": checks}
    return JSONResponse(content=body, status_code=status)


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
    items = pending_queue.get_all(_CFG)
    return {"items": items, "count": len(items)}


class BatchBody(BaseModel):
    ids: list[str]


@app.post("/api/pending/batch/approve")
def batch_approve(body: BatchBody):
    """批量放行。"""
    ok_count, failed = pending_queue.apply_batch_decision(_CFG, body.ids, "approve")
    return {"ok_count": ok_count, "failed": failed}


@app.post("/api/pending/batch/reject")
def batch_reject(body: BatchBody):
    """批量拒绝。"""
    ok_count, failed = pending_queue.apply_batch_decision(_CFG, body.ids, "reject")
    return {"ok_count": ok_count, "failed": failed}


@app.post("/api/pending/{item_id}/approve")
def approve_one(item_id: str):
    """单项放行。"""
    ok, err = pending_queue.apply_decision(_CFG, item_id, "approve")
    if not ok:
        raise HTTPException(status_code=404, detail=err or "操作失败")
    return {"ok": True}


@app.post("/api/pending/{item_id}/reject")
def reject_one(item_id: str):
    """单项拒绝。"""
    ok, err = pending_queue.apply_decision(_CFG, item_id, "reject")
    if not ok:
        raise HTTPException(status_code=404, detail=err or "操作失败")
    return {"ok": True}


@app.get("/thumbs/{filename}")
def get_thumbnail(filename: str):
    """缩略图静态文件。P0：严格路径校验，防 path traversal。"""
    if ".." in filename or "/" in filename or "\\" in filename or os.path.isabs(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    from pathlib import Path
    base = Path(THUMBS_DIR).resolve()
    try:
        target = (base / filename).resolve()
        target.relative_to(base)  # 确保 target 在 base 下
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(target), media_type="image/jpeg")


def main():
    import uvicorn
    cfg = config_loader.load_config()
    port = cfg.get("paths", {}).get("dashboard_port") or os.environ.get("DASHBOARD_PORT", "8765")
    port = int(port)
    print(f"🏭 厂长中控台: http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
