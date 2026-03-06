# tests/unit/test_usage_tracker.py
"""utils.usage_tracker 单元测试。"""
import json
import os
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.unit


# ─────────────────────────── Fixtures ──────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_tracker(tmp_path, monkeypatch):
    """每个测试用独立临时目录，避免写入真实 logs/。"""
    import utils.usage_tracker as _t
    usage_file = str(tmp_path / "feature_usage.json")
    monkeypatch.setattr(_t, "_LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(_t, "_USAGE_FILE", usage_file)


# ─────────────────────────── _fmt_last_used ────────────────────────────────

class TestFmtLastUsed:
    def _call(self, iso_str, today):
        from utils.usage_tracker import _fmt_last_used
        return _fmt_last_used(iso_str, today)

    def test_none_returns_never(self):
        assert self._call(None, date.today()) == "从未使用"

    def test_empty_string_returns_never(self):
        assert self._call("", date.today()) == "从未使用"

    def test_today(self):
        today = date.today()
        assert self._call(today.isoformat() + "T10:00:00", today) == "今天"

    def test_yesterday(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        assert self._call(yesterday.isoformat() + "T10:00:00", today) == "昨天"

    def test_within_week(self):
        today = date.today()
        three_days_ago = today - timedelta(days=3)
        result = self._call(three_days_ago.isoformat() + "T10:00:00", today)
        assert result == "3天前"

    def test_older_returns_iso_date(self):
        today = date.today()
        old = today - timedelta(days=10)
        result = self._call(old.isoformat() + "T10:00:00", today)
        assert result == old.isoformat()

    def test_malformed_iso_returns_never(self):
        assert self._call("not-a-date", date.today()) == "从未使用"


# ─────────────────────────── track() ───────────────────────────────────────

class TestTrack:
    def test_track_creates_file(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        assert os.path.isfile(t._USAGE_FILE)

    def test_track_sets_count(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        data = json.loads(open(t._USAGE_FILE).read())
        assert data["feature_a"]["count"] == 1

    def test_track_increments_count(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        t.track("feature_a")
        data = json.loads(open(t._USAGE_FILE).read())
        assert data["feature_a"]["count"] == 2

    def test_track_sets_first_and_last_used(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        data = json.loads(open(t._USAGE_FILE).read())
        entry = data["feature_a"]
        assert entry.get("first_used")
        assert entry.get("last_used")

    def test_track_first_used_not_overwritten(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        data1 = json.loads(open(t._USAGE_FILE).read())
        first = data1["feature_a"]["first_used"]
        t.track("feature_a")
        data2 = json.loads(open(t._USAGE_FILE).read())
        assert data2["feature_a"]["first_used"] == first

    def test_track_updates_daily(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        t.track("feature_a")
        data = json.loads(open(t._USAGE_FILE).read())
        today = date.today().isoformat()
        assert data["feature_a"]["daily"][today] == 2

    def test_track_independent_features(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        t.track("feature_b")
        t.track("feature_b")
        data = json.loads(open(t._USAGE_FILE).read())
        assert data["feature_a"]["count"] == 1
        assert data["feature_b"]["count"] == 2

    def test_track_silent_on_corrupt_json(self, tmp_path):
        from utils import usage_tracker as t
        # 写入损坏的 JSON
        os.makedirs(str(tmp_path), exist_ok=True)
        with open(t._USAGE_FILE, "w") as f:
            f.write("{broken json")
        # 应当静默，不抛出异常
        t.track("feature_a")

    def test_track_does_not_raise_on_read_only_dir(self, tmp_path, monkeypatch):
        """写入失败时 track() 必须静默，不影响主流程。"""
        import utils.usage_tracker as t
        # 指向不可能创建的路径
        monkeypatch.setattr(t, "_USAGE_FILE", "/nonexistent_dir/usage.json")
        monkeypatch.setattr(t, "_LOGS_DIR", "/nonexistent_dir")
        t.track("feature_a")  # must not raise


# ─────────────────────────── reset() ───────────────────────────────────────

class TestReset:
    def test_reset_single_feature(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        t.track("feature_b")
        t.reset("feature_a")
        data = json.loads(open(t._USAGE_FILE).read())
        assert "feature_a" not in data
        assert "feature_b" in data

    def test_reset_all(self, tmp_path):
        from utils import usage_tracker as t
        t.track("feature_a")
        t.track("feature_b")
        t.reset(None)
        data = json.loads(open(t._USAGE_FILE).read())
        assert data == {}

    def test_reset_nonexistent_no_raise(self, tmp_path):
        from utils import usage_tracker as t
        t.reset("never_existed")  # must not raise

    def test_reset_empty_store_no_raise(self, tmp_path):
        from utils import usage_tracker as t
        t.reset(None)  # empty store, must not raise


# ─────────────────────────── report() ──────────────────────────────────────

class TestReport:
    def test_report_empty_data_no_crash(self, capsys, tmp_path):
        from utils import usage_tracker as t
        t.report(days=30)  # must not raise
        out = capsys.readouterr().out
        assert "Feature Usage Report" in out

    def test_report_shows_feature_name(self, capsys, tmp_path):
        from utils import usage_tracker as t
        t.track("my_feature")
        t.report(days=30)
        out = capsys.readouterr().out
        assert "my_feature" in out

    def test_report_suggest_delete_when_zero(self, capsys, tmp_path):
        """功能在统计周期内 0 次调用 → 建议删除。"""
        from utils import usage_tracker as t
        # 手动写一条很旧的记录（在统计期外）
        old_date = (date.today() - timedelta(days=60)).isoformat()
        data = {"old_feature": {"count": 1, "daily": {old_date: 1}, "last_used": old_date + "T00:00:00"}}
        import json as _json
        with open(t._USAGE_FILE, "w") as f:
            _json.dump(data, f)
        t.report(days=30)
        out = capsys.readouterr().out
        assert "❌" in out

    def test_report_suggest_ok_when_frequent(self, capsys, tmp_path):
        from utils import usage_tracker as t
        for _ in range(15):
            t.track("hot_feature")
        t.report(days=30)
        out = capsys.readouterr().out
        assert "✅" in out
