# tests/unit/test_labeling_export.py — labeling_export 单元测试
"""
覆盖：
  - IMAGE_EXT 过滤（视频不进 for_labeling）
  - _collect_media_from_dir 只返回图片
  - _stratified_sample_by_video 抽样比例
  - _video_key 视频键提取
  - auto_update_after_batch manifest 结构
"""
import os
import json
import pytest

pytestmark = pytest.mark.unit


# ─── IMAGE_EXT 定义 ───────────────────────────────────────────────────────────

def test_image_ext_excludes_video():
    """IMAGE_EXT 不含视频扩展名。"""
    from labeling.labeling_export import IMAGE_EXT

    video_exts = {".mp4", ".mov", ".avi", ".mkv"}
    assert not (IMAGE_EXT & video_exts), f"IMAGE_EXT 不应包含视频扩展: {IMAGE_EXT & video_exts}"


def test_image_ext_contains_images():
    """IMAGE_EXT 包含常用图片格式。"""
    from labeling.labeling_export import IMAGE_EXT

    assert ".jpg" in IMAGE_EXT
    assert ".png" in IMAGE_EXT
    assert ".jpeg" in IMAGE_EXT


# ─── _collect_media_from_dir ──────────────────────────────────────────────────

class TestCollectMediaFromDir:
    def test_collects_only_images(self, tmp_path):
        """目录中混有视频和图片，只返回图片。"""
        from labeling.labeling_export import _collect_media_from_dir

        (tmp_path / "frame.jpg").write_bytes(b"img")
        (tmp_path / "frame.png").write_bytes(b"img")
        (tmp_path / "video.mp4").write_bytes(b"vid")
        (tmp_path / "video.mov").write_bytes(b"vid")

        result = _collect_media_from_dir(str(tmp_path))
        filenames = {r["filename"] for r in result}
        assert "frame.jpg" in filenames
        assert "frame.png" in filenames
        assert "video.mp4" not in filenames
        assert "video.mov" not in filenames

    def test_empty_dir_returns_empty(self, tmp_path):
        """空目录返回空列表。"""
        from labeling.labeling_export import _collect_media_from_dir

        assert _collect_media_from_dir(str(tmp_path)) == []

    def test_nonexistent_dir_returns_empty(self):
        """不存在的目录返回空列表，不报错。"""
        from labeling.labeling_export import _collect_media_from_dir

        assert _collect_media_from_dir("/nonexistent/path") == []

    def test_recursive_collection(self, tmp_path):
        """递归收集子目录中的图片。"""
        from labeling.labeling_export import _collect_media_from_dir

        sub = tmp_path / "Normal"
        sub.mkdir()
        (sub / "img.jpg").write_bytes(b"img")
        (tmp_path / "root.jpg").write_bytes(b"img")

        result = _collect_media_from_dir(str(tmp_path))
        assert len(result) == 2


# ─── _video_key ───────────────────────────────────────────────────────────────

class TestVideoKey:
    def test_frame_filename_strips_suffix(self):
        """videoname_f00042.jpg → videoname。"""
        from labeling.labeling_export import _video_key

        assert _video_key("myvideo_f00042.jpg") == "myvideo"

    def test_plain_image_returns_itself(self):
        """非帧文件名（无 _fNNNNN）原样返回。"""
        from labeling.labeling_export import _video_key

        assert _video_key("photo.jpg") == "photo.jpg"

    def test_complex_video_name(self):
        """含下划线的视频名也能正确提取。"""
        from labeling.labeling_export import _video_key

        assert _video_key("site_cam2_20240101_f00100.jpg") == "site_cam2_20240101"


# ─── _stratified_sample_by_video ─────────────────────────────────────────────

class TestStratifiedSampleByVideo:
    def _make_items(self, video_name, count):
        return [{"filename": f"{video_name}_f{i:05d}.jpg", "path": f"/fake/{i}.jpg"} for i in range(count)]

    def test_rate_100_percent_returns_all(self):
        """100% 抽样返回所有帧。"""
        from labeling.labeling_export import _stratified_sample_by_video

        items = self._make_items("vid", 10)
        result = _stratified_sample_by_video(items, 1.0)
        assert len(result) == 10

    def test_rate_50_percent(self):
        """50% 抽样，返回约一半（ceil）。"""
        from labeling.labeling_export import _stratified_sample_by_video

        items = self._make_items("vid", 10)
        result = _stratified_sample_by_video(items, 0.5)
        assert len(result) == 5

    def test_rate_10_percent_at_least_one(self):
        """10% 但每组至少 1 帧。"""
        from labeling.labeling_export import _stratified_sample_by_video

        items = self._make_items("vid", 10)
        result = _stratified_sample_by_video(items, 0.1)
        assert len(result) >= 1

    def test_multi_video_each_sampled(self):
        """多视频时每个视频独立抽样。"""
        from labeling.labeling_export import _stratified_sample_by_video

        items = self._make_items("vidA", 10) + self._make_items("vidB", 10)
        result = _stratified_sample_by_video(items, 0.5)
        # 每视频 5 帧，共 10
        assert len(result) == 10

    def test_empty_input_returns_empty(self):
        """空输入返回空列表。"""
        from labeling.labeling_export import _stratified_sample_by_video

        assert _stratified_sample_by_video([], 0.5) == []


# ─── auto_update_after_batch manifest 结构 ───────────────────────────────────

class TestAutoUpdateAfterBatch:
    def _make_cfg(self, tmp_path, sample_rate=0.0):
        # auto_update_after_batch 读取 cfg["paths"]["labeling_export"]
        for_labeling = tmp_path / "for_labeling"
        for_labeling.mkdir()
        return (
            {
                "labeling_pool": {
                    "auto_update_after_batch": True,
                    "upload_inspection": True,
                    "refinery_sample_rate": sample_rate,
                },
                "paths": {
                    "labeling_export": str(for_labeling),
                    "batch_subdirs": {
                        "inspection": "inspection",
                        "refinery": "refinery",
                    },
                },
            },
            {"batch_id": "20240101_120000"},
        )

    def test_inspection_frames_added_to_manifest(self, synthetic_batch_dir, tmp_path):
        """inspection 帧被加入 manifest，无视频。"""
        from labeling.labeling_export import auto_update_after_batch

        cfg, path_info = self._make_cfg(tmp_path)
        path_info["human_dir"] = os.path.join(synthetic_batch_dir, "inspection")

        result = auto_update_after_batch(cfg, path_info)
        assert result is not None

        # manifest 文件名为 manifest_for_labeling.json
        manifest_path = os.path.join(tmp_path, "for_labeling", "manifest_for_labeling.json")
        with open(manifest_path) as f:
            entries = json.load(f)

        assert len(entries) > 0
        for entry in entries:
            ext = os.path.splitext(entry["filename"])[1].lower()
            assert ext in {".jpg", ".jpeg", ".png", ".bmp"}, f"非图片文件进入 manifest: {entry['filename']}"

    def test_refinery_sampling_adds_entries(self, synthetic_batch_dir, tmp_path):
        """开启 refinery_sample_rate 后，manifest 中出现 subdir=refinery 条目。"""
        from labeling.labeling_export import auto_update_after_batch

        cfg, path_info = self._make_cfg(tmp_path, sample_rate=0.5)
        path_info["human_dir"] = os.path.join(synthetic_batch_dir, "inspection")
        path_info["fuel_dir"] = os.path.join(synthetic_batch_dir, "refinery")

        result = auto_update_after_batch(cfg, path_info)
        assert result is not None

        manifest_path = os.path.join(tmp_path, "for_labeling", "manifest_for_labeling.json")
        with open(manifest_path) as f:
            entries = json.load(f)

        refinery_entries = [e for e in entries if e.get("subdir") == "refinery"]
        assert len(refinery_entries) > 0
