# tests/unit/test_archiver.py — archiver 文件路由单元测试
"""
验证 archive_rejected 的文件路由逻辑：
  - duplicate → redundant_archives/
  - quality fail → rejected_material/Batch_xxx_fails/
"""
import os
import pytest

pytestmark = pytest.mark.unit


def _make_cfg(tmp_path):
    rejected = tmp_path / "rejected"
    redundant = tmp_path / "redundant"
    rejected.mkdir()
    redundant.mkdir()
    return {
        "paths": {
            "rejected_material": str(rejected),
            "redundant_archives": str(redundant),
        },
        "retry": {"max_attempts": 1, "backoff_seconds": 0},
        "batch_prefix": "Batch_",
        "batch_fails_suffix": "_fails",
    }


def _make_item(tmp_path, filename, score=45.0):
    """在 tmp_path 创建一个假文件，返回 archiver item dict。"""
    src = tmp_path / filename
    src.write_bytes(b"fake content")
    return {"archive_path": str(src), "filename": filename, "score": score}


class TestArchiveRejected:
    def test_duplicate_goes_to_redundant(self, tmp_path):
        """重复文件应移入 redundant_archives。"""
        from core.archiver import archive_rejected

        cfg = _make_cfg(tmp_path)
        item = _make_item(tmp_path, "dup.jpg")

        archive_rejected(cfg, [(item, "duplicate")], batch_id="20240101_120000")

        redundant_dir = cfg["paths"]["redundant_archives"]
        assert os.path.isfile(os.path.join(redundant_dir, "dup.jpg"))

    def test_quality_fail_goes_to_rejected(self, tmp_path):
        """质量不合格文件应移入 rejected_material/Batch_xxx_fails/。"""
        from core.archiver import archive_rejected

        cfg = _make_cfg(tmp_path)
        item = _make_item(tmp_path, "bad.jpg", score=30.0)

        archive_rejected(cfg, [(item, "blurry")], batch_id="20240101_120000")

        rejected_dir = cfg["paths"]["rejected_material"]
        batch_fails = os.path.join(rejected_dir, "Batch_20240101_120000_fails")
        assert os.path.isdir(batch_fails)
        # 文件名含分数后缀
        files = os.listdir(batch_fails)
        assert any("30pts" in f for f in files)

    def test_missing_source_file_skipped(self, tmp_path):
        """source 文件不存在时，跳过不崩溃。"""
        from core.archiver import archive_rejected

        cfg = _make_cfg(tmp_path)
        item = {"archive_path": "/nonexistent/file.jpg", "filename": "file.jpg", "score": 50.0}

        # 不应抛异常
        archive_rejected(cfg, [(item, "blurry")], batch_id="20240101_120000")

    def test_empty_reject_list(self, tmp_path):
        """空列表，不报错，不创建多余目录。"""
        from core.archiver import archive_rejected

        cfg = _make_cfg(tmp_path)
        archive_rejected(cfg, [], batch_id="20240101_120000")

    def test_multiple_items_mixed_reasons(self, tmp_path):
        """混合原因：dup + quality fail，各去各的目录。"""
        from core.archiver import archive_rejected

        cfg = _make_cfg(tmp_path)
        dup_item = _make_item(tmp_path, "dup.jpg")
        bad_item = _make_item(tmp_path, "bad.jpg", score=20.0)

        archive_rejected(cfg, [(dup_item, "duplicate"), (bad_item, "too_dark")], batch_id="20240101_120000")

        assert os.path.isfile(os.path.join(cfg["paths"]["redundant_archives"], "dup.jpg"))
        batch_fails = os.path.join(cfg["paths"]["rejected_material"], "Batch_20240101_120000_fails")
        assert any("20pts" in f for f in os.listdir(batch_fails))
