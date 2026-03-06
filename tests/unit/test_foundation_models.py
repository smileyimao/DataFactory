# tests/unit/test_foundation_models.py
"""vision.foundation_models 单元测试。

不依赖 open-clip-torch 或 segment-anything；
工厂函数行为 + 常量一致性 + 纯逻辑（FPS / 语义去重）均可无模型测试。
"""
import os
import types

import numpy as np
import pytest

pytestmark = pytest.mark.unit


# ─────────────────────────── 常量一致性 ────────────────────────────────────

def test_scene_keys_match_prompts():
    from vision.foundation_models import SCENE_KEYS, SCENE_PROMPTS
    assert len(SCENE_KEYS) == len(SCENE_PROMPTS), "SCENE_KEYS 与 SCENE_PROMPTS 数量不一致"


def test_scene_keys_are_unique():
    from vision.foundation_models import SCENE_KEYS
    assert len(SCENE_KEYS) == len(set(SCENE_KEYS))


def test_scene_prompts_are_non_empty():
    from vision.foundation_models import SCENE_PROMPTS
    for p in SCENE_PROMPTS:
        assert p.strip(), "SCENE_PROMPTS 中存在空字符串"


# ─────────────────────────── load_clip_embedder() ──────────────────────────

class TestLoadClipEmbedder:
    def test_returns_none_when_disabled(self):
        from vision.foundation_models import load_clip_embedder
        cfg = {"foundation_models": {"clip_enabled": False}}
        assert load_clip_embedder(cfg) is None

    def test_returns_none_when_key_missing(self):
        from vision.foundation_models import load_clip_embedder
        assert load_clip_embedder({}) is None

    def test_returns_none_when_open_clip_missing(self, monkeypatch):
        """clip_enabled=True 但 open_clip 未安装 → None，不崩溃。"""
        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "open_clip":
                raise ImportError("open_clip not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        from vision.foundation_models import load_clip_embedder
        cfg = {"foundation_models": {"clip_enabled": True, "clip_model": "ViT-B-32"}}
        result = load_clip_embedder(cfg)
        assert result is None


# ─────────────────────────── load_sam_refiner() ────────────────────────────

class TestLoadSamRefiner:
    def test_returns_none_when_disabled(self):
        from vision.foundation_models import load_sam_refiner
        cfg = {"foundation_models": {"sam_enabled": False}}
        assert load_sam_refiner(cfg) is None

    def test_returns_none_when_key_missing(self):
        from vision.foundation_models import load_sam_refiner
        assert load_sam_refiner({}) is None

    def test_returns_none_when_checkpoint_missing(self, tmp_path):
        from vision.foundation_models import load_sam_refiner
        cfg = {
            "foundation_models": {
                "sam_enabled": True,
                "sam_model_type": "vit_b",
                "sam_checkpoint": str(tmp_path / "nonexistent.pth"),
            }
        }
        assert load_sam_refiner(cfg) is None

    def test_returns_none_when_segment_anything_missing(self, tmp_path, monkeypatch):
        """sam_enabled=True，checkpoint 存在，但 segment_anything 未安装 → None。"""
        ckpt = tmp_path / "sam.pth"
        ckpt.write_bytes(b"fake")

        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "segment_anything":
                raise ImportError("segment_anything not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        from vision.foundation_models import load_sam_refiner
        cfg = {
            "foundation_models": {
                "sam_enabled": True,
                "sam_model_type": "vit_b",
                "sam_checkpoint": str(ckpt),
            }
        }
        assert load_sam_refiner(cfg) is None


# ─────────────────────────── 纯逻辑：FPS 多样性采样 ──────────────────────

class _FakeEmbedder:
    """最小 mock：只借用 torch.stack，不需要 CLIP 模型。"""

    def __init__(self):
        import torch
        self._torch = torch

    # 复制同名方法进行测试
    def diversity_sample(self, items, embeddings, k):
        from vision.foundation_models import ClipEmbedder
        return ClipEmbedder.diversity_sample(self, items, embeddings, k)

    def is_semantic_duplicate(self, emb, seen_list, threshold=0.98):
        from vision.foundation_models import ClipEmbedder
        return ClipEmbedder.is_semantic_duplicate(self, emb, seen_list, threshold)


torch = pytest.importorskip("torch")  # torch 必须安装（ultralytics 依赖），否则全跳


class TestDiversitySample:
    def _embedder(self):
        return _FakeEmbedder()

    def _rand_emb(self, dim=32):
        v = torch.randn(dim)
        return v / v.norm()

    def test_k_ge_n_returns_all(self):
        emb = _FakeEmbedder()
        items = ["a", "b", "c"]
        embeddings = [self._rand_emb() for _ in items]
        result = emb.diversity_sample(items, embeddings, k=10)
        assert result == items

    def test_k_eq_n_returns_all(self):
        emb = _FakeEmbedder()
        items = ["a", "b", "c"]
        embeddings = [self._rand_emb() for _ in items]
        result = emb.diversity_sample(items, embeddings, k=3)
        assert result == items

    def test_returns_exactly_k_items(self):
        emb = _FakeEmbedder()
        items = [f"item_{i}" for i in range(10)]
        embeddings = [self._rand_emb() for _ in items]
        result = emb.diversity_sample(items, embeddings, k=4)
        assert len(result) == 4

    def test_result_is_subset_of_input(self):
        emb = _FakeEmbedder()
        items = [f"item_{i}" for i in range(8)]
        embeddings = [self._rand_emb() for _ in items]
        result = emb.diversity_sample(items, embeddings, k=3)
        for r in result:
            assert r in items

    def test_identical_embeddings_still_returns_k(self):
        """全相同向量时 FPS 仍能返回 k 个（不崩溃）。"""
        emb = _FakeEmbedder()
        vec = torch.ones(32) / (32 ** 0.5)
        items = [f"item_{i}" for i in range(5)]
        embeddings = [vec.clone() for _ in items]
        result = emb.diversity_sample(items, embeddings, k=3)
        assert len(result) == 3


# ─────────────────────────── 纯逻辑：语义去重 ──────────────────────────────

class TestIsSemanticDuplicate:
    def _embedder(self):
        return _FakeEmbedder()

    def _rand_emb(self, dim=32):
        v = torch.randn(dim)
        return v / v.norm()

    def test_empty_seen_returns_false(self):
        emb = _FakeEmbedder()
        result = emb.is_semantic_duplicate(self._rand_emb(), seen_list=[], threshold=0.98)
        assert result is False

    def test_identical_embedding_is_duplicate(self):
        emb = _FakeEmbedder()
        vec = self._rand_emb()
        result = emb.is_semantic_duplicate(vec, seen_list=[vec], threshold=0.98)
        assert result is True

    def test_orthogonal_not_duplicate(self):
        emb = _FakeEmbedder()
        # 构造两个正交向量（余弦相似度 = 0）
        a = torch.zeros(32)
        b = torch.zeros(32)
        a[0] = 1.0
        b[1] = 1.0
        result = emb.is_semantic_duplicate(b, seen_list=[a], threshold=0.98)
        assert result is False

    def test_threshold_boundary(self):
        emb = _FakeEmbedder()
        # 构造相似度精确为 1.0 的向量
        vec = self._rand_emb()
        # threshold=1.0 → 只有完全相同才算重复
        assert emb.is_semantic_duplicate(vec, seen_list=[vec], threshold=1.0) is True
        # threshold=1.01（不可能达到）→ 不是重复
        assert emb.is_semantic_duplicate(vec, seen_list=[vec], threshold=1.01) is False
