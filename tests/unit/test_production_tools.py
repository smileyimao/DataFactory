# tests/unit/test_production_tools.py — production_tools.compute_video_tiers 单元测试
"""验证视频三档分层逻辑（high/standard/low）。"""
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def tier_cfg():
    return {
        "production_setting": {
            "video_tier_high_detection_rate": 0.60,
            "video_tier_high_conf": 0.70,
            "video_tier_low_detection_rate": 0.30,
            "video_tier_low_conf": 0.50,
        }
    }


def _det(conf):
    """构造单帧检测结果。"""
    return [{"conf": conf, "class_id": 0}]


class TestComputeVideoTiers:
    def test_high_tier(self, tier_cfg):
        """高命中率 + 高置信度 → high。"""
        from engines.production_tools import compute_video_tiers

        dets = {f"f{i:03d}": _det(0.85) for i in range(8)}  # 8/10 帧有检测
        tiers = compute_video_tiers({"vid": dets}, {"vid": 10}, tier_cfg)
        assert tiers["vid"] == "high"

    def test_low_tier_by_conf(self, tier_cfg):
        """低置信度 → low。"""
        from engines.production_tools import compute_video_tiers

        dets = {f"f{i:03d}": _det(0.30) for i in range(8)}
        tiers = compute_video_tiers({"vid": dets}, {"vid": 10}, tier_cfg)
        assert tiers["vid"] == "low"

    def test_low_tier_by_detection_rate(self, tier_cfg):
        """命中率低于 low_detection_rate → low。"""
        from engines.production_tools import compute_video_tiers

        # 只有 2/10 帧有检测
        dets = {"f000": _det(0.80), "f001": _det(0.80)}
        tiers = compute_video_tiers({"vid": dets}, {"vid": 10}, tier_cfg)
        assert tiers["vid"] == "low"

    def test_standard_tier(self, tier_cfg):
        """中间档 → standard。"""
        from engines.production_tools import compute_video_tiers

        # 5/10 帧有检测，置信度 0.60
        dets = {f"f{i:03d}": _det(0.60) for i in range(5)}
        tiers = compute_video_tiers({"vid": dets}, {"vid": 10}, tier_cfg)
        assert tiers["vid"] == "standard"

    def test_no_detections_is_low(self, tier_cfg):
        """无任何检测帧 → low。"""
        from engines.production_tools import compute_video_tiers

        tiers = compute_video_tiers({"vid": {}}, {"vid": 10}, tier_cfg)
        assert tiers["vid"] == "low"

    def test_multiple_videos_independent(self, tier_cfg):
        """多视频各自独立分档。"""
        from engines.production_tools import compute_video_tiers

        dets_high = {f"f{i:03d}": _det(0.85) for i in range(8)}
        dets_low = {f"f{i:03d}": _det(0.30) for i in range(8)}
        tiers = compute_video_tiers(
            {"high_vid": dets_high, "low_vid": dets_low},
            {"high_vid": 10, "low_vid": 10},
            tier_cfg,
        )
        assert tiers["high_vid"] == "high"
        assert tiers["low_vid"] == "low"

    def test_fallback_no_total_frames(self, tier_cfg):
        """total_frames_by_video 为空时，只用 mean_conf 判档。"""
        from engines.production_tools import compute_video_tiers

        dets = {f"f{i:03d}": _det(0.85) for i in range(5)}
        tiers = compute_video_tiers({"vid": dets}, {}, tier_cfg)
        assert tiers["vid"] == "high"
