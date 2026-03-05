# vision/model_registry.py — v3 MLflow Model Registry：解析 models:/name/version 为本地路径
"""
当 vision.model_path 或 cascade_light_model_path 为 models:/name/version 时，
从 MLflow Model Registry 下载到本地缓存并返回 .pt 路径，供 YOLO 加载。
"""
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 缓存：models:/uri -> 本地路径，避免重复下载
_resolved_cache: dict = {}


def _get_cache_dir(base_dir: str) -> str:
    """模型缓存目录：项目 models/registry_cache 或 ~/.datafactory/model_cache。"""
    if base_dir:
        d = os.path.join(base_dir, "models", "registry_cache")
        os.makedirs(d, exist_ok=True)
        return d
    d = os.path.join(os.path.expanduser("~"), ".datafactory", "model_cache")
    os.makedirs(d, exist_ok=True)
    return d


def resolve_model_uri(
    uri: str,
    base_dir: str = "",
    mlflow_tracking_uri: Optional[str] = None,
) -> str:
    """
    解析模型 URI。若为 models:/name/version，从 MLflow 下载到缓存并返回本地 .pt 路径；否则返回原路径（相对 base_dir 解析）。
    """
    uri = (uri or "").strip()
    if not uri:
        return ""
    if uri in _resolved_cache:
        cached = _resolved_cache[uri]
        if os.path.isfile(cached):
            return cached
        _resolved_cache.pop(uri, None)
    if not uri.startswith("models:/"):
        # 本地路径：相对 base_dir 解析
        if base_dir and not os.path.isabs(uri):
            resolved = os.path.normpath(os.path.join(base_dir, uri))
            if os.path.isfile(resolved):
                return resolved
        return uri
    # models:/name/version
    try:
        import mlflow
        if mlflow_tracking_uri:
            mlflow.set_tracking_uri(mlflow_tracking_uri)
        parts = re.sub(r"^models:/", "", uri).strip().split("/")
        if len(parts) < 2:
            logger.warning("models:/ URI 格式错误，需要 models:/name/version: %s", uri)
            return uri
        name, version = parts[0], parts[1]
        model_uri = f"models:/{name}/{version}"
        cache_dir = _get_cache_dir(base_dir)
        safe_name = re.sub(r"[^\w\-]", "_", name)
        dst = os.path.join(cache_dir, f"{safe_name}_{version}")
        local_dir = mlflow.artifacts.download_artifacts(artifact_uri=model_uri, dst_path=dst)
        for root, _, files in os.walk(local_dir):
            for f in files:
                if f.endswith(".pt"):
                    path = os.path.join(root, f)
                    _resolved_cache[uri] = path
                    logger.info("Model Registry 解析: %s -> %s", uri, path)
                    return path
        logger.warning("Model Registry 中未找到 .pt 文件: %s", uri)
        return uri
    except ImportError:
        logger.warning("mlflow 未安装，无法解析 models:/ URI: %s", uri)
        return uri
    except Exception as e:
        logger.warning("Model Registry 解析失败 %s: %s", uri, e)
        return uri
