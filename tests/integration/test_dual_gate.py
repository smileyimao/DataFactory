# tests/integration/test_dual_gate.py
"""双门槛分流 + archiver 集成测试。"""
import os
import sys

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        sys.platform == "darwin",
        reason="archiver 依赖 cv2，macOS 上 numpy/cv2 存在 Floating-point exception",
    ),
]

DUAL_GATE_HIGH = 90.0
DUAL_GATE_LOW = 50.0

MOCK_ITEMS = [
    {"score": 95.0, "filename": "high_95pts.mp4"},
    {"score": 60.0, "filename": "mid_60pts.mp4"},
    {"score": 30.0, "filename": "low_30pts.mp4"},
]


def _build_mock_qc_archive(source_archive_dir: str):
    archive = []
    for m in MOCK_ITEMS:
        name = m["filename"]
        archive_path = os.path.join(source_archive_dir, name)
        archive.append({
            "filename": name,
            "archive_path": archive_path,
            "fingerprint": "",
            "score": m["score"],
            "passed": m["score"] >= 80.0,
            "is_duplicate": False,
            "duplicate_batch_id": None,
            "duplicate_created_at": None,
        })
    return archive


def _dual_gate_split(qc_archive, dual_high, dual_low):
    qualified = [x for x in qc_archive if not x["is_duplicate"] and x["score"] >= dual_high]
    auto_reject = [(x, "quality") for x in qc_archive if not x["is_duplicate"] and x["score"] < dual_low]
    blocked = [x for x in qc_archive if x["is_duplicate"] or (dual_low <= x["score"] < dual_high)]
    return qualified, blocked, auto_reject


def test_dual_gate_split_and_archive(test_cfg, temp_dir, project_root):
    """双门槛分流正确，auto_reject 归档至废片库。"""
    from config import config_loader
    from core import archiver
    from core import time_utils

    config_loader.set_base_dir(project_root)
    cfg = dict(test_cfg)
    cfg.setdefault("production_setting", {})["dual_gate_high"] = DUAL_GATE_HIGH
    cfg.setdefault("production_setting", {})["dual_gate_low"] = DUAL_GATE_LOW

    source_archive_dir = os.path.join(temp_dir, "source")
    rejected_dir = cfg["paths"]["rejected_material"]
    os.makedirs(source_archive_dir, exist_ok=True)

    for m in MOCK_ITEMS:
        p = os.path.join(source_archive_dir, m["filename"])
        with open(p, "wb") as f:
            f.write(b"")

    qc_archive = _build_mock_qc_archive(source_archive_dir)
    qualified, blocked, auto_reject = _dual_gate_split(qc_archive, DUAL_GATE_HIGH, DUAL_GATE_LOW)

    assert len(qualified) == 1 and qualified[0]["score"] == 95.0
    assert len(blocked) == 1 and blocked[0]["score"] == 60.0
    assert len(auto_reject) == 1 and auto_reject[0][0]["score"] == 30.0

    batch_id = time_utils.now_toronto().strftime("%Y%m%d_%H%M%S")
    archiver.archive_rejected(cfg, auto_reject, batch_id)

    batch_fails = os.path.join(rejected_dir, f"Batch_{batch_id}_Fails")
    assert os.path.isdir(batch_fails), "废片库批次目录应已创建"
