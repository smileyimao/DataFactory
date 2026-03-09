# vision/foundation_models.py — CLIP + SAM 基础模型封装（v3.9，默认全部关闭）
# 依赖可选：open-clip-torch>=2.20.0（CLIP），segment-anything>=1.0（SAM）
# 缺包时工厂函数返回 None，不影响主流程。
import logging
import os
from typing import List, Optional, Any

import numpy as np

logger = logging.getLogger(__name__)

# ── 矿区场景 Prompt ─────────────────────────────────────────────────────────
SCENE_PROMPTS = [
    "a photo of an underground mining tunnel",
    "a photo of an open pit mine",
    "a photo of a dusty mining environment",
    "a photo of a mining conveyor belt",
    "a photo of a mining surface area",
]
SCENE_KEYS = [
    "underground_tunnel",
    "open_pit",
    "dusty_environment",
    "conveyor_belt",
    "surface_area",
]


# ───────────────────────────── ClipEmbedder ────────────────────────────────

class ClipEmbedder:
    """用 open-clip-torch 提供图像嵌入、语义去重、多样性采样、场景分类功能。"""

    def __init__(self, model_name: str = "ViT-B-32", device: Optional[str] = None):
        import open_clip  # type: ignore
        import torch

        self._torch = torch
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained="openai", device=self._device
        )
        model.eval()
        self._model = model
        self._preprocess = preprocess
        tokenizer = open_clip.get_tokenizer(model_name)

        # 预计算场景 text embedding
        tokens = tokenizer(SCENE_PROMPTS).to(self._device)
        with torch.no_grad():
            text_feats = model.encode_text(tokens)
            text_feats = text_feats / text_feats.norm(dim=-1, keepdim=True)
        self._scene_text_feats = text_feats  # (n_scenes, D)

    # ── 图像 embedding ────────────────────────────────────────────────────

    def get_embedding(self, img_path: str):
        """返回归一化图像 embedding Tensor，shape=(D,)。"""
        from PIL import Image  # type: ignore
        img = Image.open(img_path).convert("RGB")
        tensor = self._preprocess(img).unsqueeze(0).to(self._device)
        with self._torch.no_grad():
            feat = self._model.encode_image(tensor)
            feat = feat / feat.norm(dim=-1, keepdim=True)
        return feat.squeeze(0)  # (D,)

    # ── 语义去重 ──────────────────────────────────────────────────────────

    def is_semantic_duplicate(self, emb, seen_list: list, threshold: float = 0.98) -> bool:
        """余弦相似度 >= threshold → 视为语义重复。"""
        if not seen_list:
            return False
        stacked = self._torch.stack(seen_list)  # (N, D)
        sims = (stacked @ emb).cpu().numpy()    # (N,)
        eps = 1e-6  # 浮点精度容差
        return bool(np.max(sims) >= threshold - eps)

    # ── 多样性采样（最远点采样 FPS）────────────────────────────────────────

    def diversity_sample(self, items: list, embeddings: list, k: int) -> list:
        """
        最远点采样：从 items 中选 k 个语义最分散的帧。
        embeddings 与 items 一一对应，均为归一化 Tensor。
        """
        n = len(items)
        if k >= n:
            return items

        feats = self._torch.stack(embeddings).cpu().numpy()  # (N, D)
        selected = [0]
        min_dists = np.full(n, -np.inf)  # 余弦相似度越小越远，用负值作距离

        for _ in range(k - 1):
            last = feats[selected[-1]]
            sims = feats @ last  # (N,) 余弦相似度
            # 距离 = 1 - 余弦相似度；对已选点取最近距离的最小值
            dists = 1.0 - sims
            min_dists = np.maximum(min_dists, dists)
            # 排除已选
            min_dists[selected] = -np.inf
            selected.append(int(np.argmax(min_dists)))

        return [items[i] for i in sorted(selected)]

    # ── 场景分类 ──────────────────────────────────────────────────────────

    def classify_scene(self, img_path: str) -> str:
        """将图片分类为 SCENE_KEYS 之一（零样本 CLIP 分类）。"""
        emb = self.get_embedding(img_path)  # (D,)
        sims = (self._scene_text_feats @ emb).cpu().numpy()  # (n_scenes,)
        return SCENE_KEYS[int(np.argmax(sims))]


# ───────────────────────────── SamRefiner ──────────────────────────────────

class SamRefiner:
    """用 segment-anything 将 YOLO bbox 精化为多边形 mask。"""

    def __init__(self, model_type: str = "vit_b", checkpoint: str = "", device: Optional[str] = None):
        import torch
        from segment_anything import sam_model_registry, SamPredictor  # type: ignore

        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        sam = sam_model_registry[model_type](checkpoint=checkpoint)
        sam.to(self._device)
        self._predictor = SamPredictor(sam)

    def boxes_to_polygons(self, img_bgr, boxes_xyxy: list) -> list:
        """
        输入 BGR numpy 图像 + 像素坐标 bbox 列表 [(label, x1, y1, x2, y2), ...]
        返回 [{"label": str, "points": [[x, y], ...], "score": float}]
        """
        import cv2
        import torch

        if not boxes_xyxy:
            return []

        import numpy as _np
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        self._predictor.set_image(img_rgb)

        results = []
        for label, x1, y1, x2, y2 in boxes_xyxy:
            box = _np.array([x1, y1, x2, y2], dtype=float)
            try:
                masks, scores, _ = self._predictor.predict(
                    box=box,
                    multimask_output=False,
                )
            except Exception as e:
                logger.warning("SAM predict 异常 label=%s: %s", label, e)
                continue
            mask = masks[0].astype(_np.uint8)  # (H, W)
            score = float(scores[0])
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            contour = max(contours, key=cv2.contourArea)
            eps = 2.0
            approx = cv2.approxPolyDP(contour, eps, closed=True)
            points = approx.reshape(-1, 2).tolist()
            if len(points) < 3:
                continue
            results.append({"label": label, "points": points, "score": score})
        return results


# ───────────────────────────── 工厂函数 ────────────────────────────────────

def load_clip_embedder(cfg: dict) -> Optional[ClipEmbedder]:
    """
    按 cfg["foundation_models"] 开关加载 ClipEmbedder。
    ImportError 或开关未开 → 返回 None。
    """
    fm = cfg.get("foundation_models", {})
    if not fm.get("clip_enabled"):
        return None
    model_name = fm.get("clip_model", "ViT-B-32")
    device = fm.get("clip_device") or None
    try:
        embedder = ClipEmbedder(model_name=model_name, device=device)
        logger.info("CLIP 模型已加载: %s device=%s", model_name, embedder._device)
        return embedder
    except ImportError:
        logger.warning("open-clip-torch 未安装，CLIP 功能跳过。pip install open-clip-torch>=2.20.0")
        return None
    except Exception as e:
        logger.warning("CLIP 模型加载失败: %s", e)
        return None


def load_sam_refiner(cfg: dict) -> Optional[SamRefiner]:
    """
    按 cfg["foundation_models"] 开关加载 SamRefiner。
    checkpoint 不存在、ImportError 或开关未开 → 返回 None。
    """
    fm = cfg.get("foundation_models", {})
    if not fm.get("sam_enabled"):
        return None
    model_type = fm.get("sam_model_type", "vit_b")
    checkpoint = fm.get("sam_checkpoint", "models/sam_vit_b.pth")
    device = fm.get("sam_device") or None
    if not os.path.isfile(checkpoint):
        logger.warning("SAM checkpoint 不存在: %s，SAM 功能跳过", checkpoint)
        return None
    try:
        refiner = SamRefiner(model_type=model_type, checkpoint=checkpoint, device=device)
        logger.info("SAM 模型已加载: type=%s checkpoint=%s device=%s", model_type, checkpoint, refiner._device)
        return refiner
    except ImportError:
        logger.warning("segment-anything 未安装，SAM 功能跳过。pip install segment-anything>=1.0")
        return None
    except Exception as e:
        logger.warning("SAM 模型加载失败: %s", e)
        return None
