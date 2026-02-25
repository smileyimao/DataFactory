# tests/api/test_health_metrics.py
"""Dashboard API：/api/health、/api/metrics。"""
import sys

import pytest

# 需要 dashboard 模块
pytest.importorskip("dashboard")
pytestmark = pytest.mark.skipif(
    sys.platform == "darwin",
    reason="dashboard 依赖链含 cv2，macOS 上 numpy/cv2 存在 Floating-point exception",
)


def test_health_endpoint(project_root):
    """GET /api/health 应返回 200 或 503。"""
    from config import config_loader
    from fastapi.testclient import TestClient

    config_loader.set_base_dir(project_root)
    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code in (200, 503)


def test_metrics_endpoint(project_root):
    """GET /api/metrics 应返回 200 及 JSON。"""
    from config import config_loader
    from fastapi.testclient import TestClient

    config_loader.set_base_dir(project_root)
    from dashboard.app import app

    client = TestClient(app)
    r = client.get("/api/metrics")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
