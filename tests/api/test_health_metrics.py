# tests/api/test_health_metrics.py
"""Dashboard API：/api/health、/api/metrics。"""
import pytest

# dashboard 依赖 cv2 + fastapi；缺包则跳过，与平台无关
pytest.importorskip("cv2")
pytest.importorskip("fastapi")
pytest.importorskip("dashboard")


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
