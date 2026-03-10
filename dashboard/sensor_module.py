# dashboard/sensor_module.py — DataSource 适配层
"""
DataSource 接口 + 三种实现：
  MockDataSource     — 纯软件仿真，用于 UI 验证（--source mock）
  ArchiveDataSource  — 回放 storage/archive/ 已归档帧（--source archive，TODO v2）
  LivePipelineSource — 轮询 DB 接收实时 pipeline 输出（--source live，TODO v3）
"""
import abc
import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class FrameData:
    """单帧遥测数据包。"""
    frame_id:    int
    timestamp:   float
    jitter:      float          # px — 帧间运动抖动量
    blur:        float          # Laplacian 方差（越高越清晰）
    brightness:  float          # 均值像素亮度 [0, 255]
    confidence:  float          # YOLO 最高检测置信度 [0, 1]
    frame_rgb:   np.ndarray     # H×W×3 uint8
    detections:  List[Tuple]    # [(x1,y1,x2,y2,conf,cls), …]
    iou_snapshot: Optional[float] = None  # 最近一次 labeled_return IoU


# ── 接口 ─────────────────────────────────────────────────────────────────

class DataSource(abc.ABC):
    @abc.abstractmethod
    def next_frame(self) -> FrameData:
        """拉取下一帧遥测数据。"""

    @abc.abstractmethod
    def get_iou_snapshot(self) -> Optional[float]:
        """最新一次标注回传 IoU 快照（无导入时返回 None）。"""


# ── MockDataSource ────────────────────────────────────────────────────────

class MockDataSource(DataSource):
    """
    纯软件 Mock：用 AR(1) 过程模拟真实视频流的统计特性，
    包含偶发异常尖峰（Type_A / Type_B），IoU 模拟低频批次到达。
    """

    def __init__(self, width: int = 640, height: int = 360):
        self.width  = width
        self.height = height
        self._fid   = 0

        # AR(1) 状态
        self._jitter = 14.0
        self._conf   = 0.72

        # IoU 快照（模拟批次导入，低频刷新）
        self._iou: Optional[float] = 0.964
        self._iou_timer = 0

    # ------------------------------------------------------------------

    def next_frame(self) -> FrameData:
        self._fid += 1

        # ---- 物理指标 ----
        jitter     = self._next_jitter()
        blur       = self._next_blur()
        brightness = max(10.0, min(250.0, random.gauss(128.0, 18.0)))

        # ---- 算法指标 ----
        conf = self._next_conf()

        # ---- IoU 快照低频刷新 ----
        self._iou_timer += 1
        if self._iou_timer >= random.randint(400, 800):
            self._iou = max(0.70, min(1.0, random.gauss(0.945, 0.030)))
            self._iou_timer = 0

        # ---- 合成帧 + 检测框 ----
        frame = self._gen_frame(blur, brightness)
        dets  = self._gen_detections(conf)

        return FrameData(
            frame_id    = self._fid,
            timestamp   = time.time(),
            jitter      = jitter,
            blur        = blur,
            brightness  = brightness,
            confidence  = conf,
            frame_rgb   = frame,
            detections  = dets,
            iou_snapshot= self._iou,
        )

    def get_iou_snapshot(self) -> Optional[float]:
        return self._iou

    # ------------------------------------------------------------------
    # 私有信号生成器
    # ------------------------------------------------------------------

    def _next_jitter(self) -> float:
        """AR(1) 漂移 + 偶发剧烈抖动（Type_A 尖峰）。"""
        self._jitter = self._jitter * 0.88 + random.gauss(13.0, 2.5) * 0.12
        if random.random() < 0.018:           # ~1.8% 尖峰概率
            self._jitter = random.uniform(36.0, 58.0)
        return max(0.0, self._jitter)

    def _next_blur(self) -> float:
        """大部分时间清晰，偶发模糊（Type_A）。"""
        blur = random.gauss(88.0, 11.0)
        if random.random() < 0.022:
            blur = random.uniform(4.0, 17.0)
        return max(1.0, blur)

    def _next_conf(self) -> float:
        """置信度平滑游走 + 偶发低置信段（Type_B）。"""
        self._conf = self._conf * 0.92 + random.gauss(0.72, 0.035) * 0.08
        self._conf = max(0.05, min(0.99, self._conf))
        if random.random() < 0.016:
            self._conf = random.uniform(0.20, 0.38)
        return self._conf

    def _gen_frame(self, blur: float, brightness: float) -> np.ndarray:
        """合成场景帧（深色天空渐变 + 灰色路面）。"""
        h, w = self.height, self.width
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # 天空渐变（蓝灰调）
        sky_h = h // 2
        for row in range(sky_h):
            v = int(12 + row * 30 / sky_h)
            frame[row, :] = [v // 3, v // 2, v]

        # 路面（冷灰，近处略亮）
        for row in range(sky_h, h):
            v = int(28 + (row - sky_h) * 38 / (h - sky_h))
            frame[row, :] = [v, v, v]

        # 地平线虚线（HMI 装饰）
        frame[sky_h, ::8] = [40, 90, 40]

        # 亮度缩放
        scale = brightness / 128.0
        frame = np.clip(frame.astype(np.float32) * scale, 0, 255).astype(np.uint8)

        # 模糊时叠加噪声
        if blur < 22.0:
            noise = np.random.randint(-30, 30, (h, w, 3), dtype=np.int16)
            frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # 荧光绿扫描线（HMI 美学，每帧下移 3px）
        sl_y = (self._fid * 3) % h
        frame[sl_y, :] = np.clip(
            frame[sl_y, :].astype(np.int16) + [0, 35, 0], 0, 255
        ).astype(np.uint8)

        return frame

    def _gen_detections(self, conf: float) -> List[Tuple]:
        """随机生成 0–3 个车辆检测框。"""
        n = random.choices([0, 1, 2, 3], weights=[0.18, 0.48, 0.26, 0.08])[0]
        dets = []
        for _ in range(n):
            x1 = random.randint(20, self.width - 140)
            y1 = random.randint(self.height // 3, self.height - 85)
            x2 = min(x1 + random.randint(75, 210), self.width - 1)
            y2 = min(y1 + random.randint(38, 105), self.height - 1)
            c  = max(0.10, min(0.99, conf + random.gauss(0, 0.05)))
            dets.append((x1, y1, x2, y2, c, 2))   # cls=2 (car)
        return dets


# ── 存根：接口已定，后续只填实现 ─────────────────────────────────────────

class ArchiveDataSource(DataSource):
    """
    --source archive：循环回放 storage/archive/Batch_xxx/inspection + refinery 真实帧。

    每帧做真实物理指标计算：
      - Blur       : Laplacian 方差（cv2）
      - Brightness : 灰度均值
      - Jitter     : 与上一帧的帧差均值
      - Confidence : 伪标签 .txt 第 6 列最高值（无 txt → 0）
      - Detections : 从 .txt 解析像素坐标框（需图片尺寸做反归一化）
    """

    def __init__(self, archive_dir: str = "storage/archive", loop: bool = True):
        import cv2 as _cv2   # 验证依赖可用
        self._cv2 = _cv2
        self._loop    = loop
        self._fid     = 0
        self._prev_gray: Optional[np.ndarray] = None
        self._iou_snapshot: Optional[float]   = None

        # 收集所有 jpg（inspection + refinery，按文件名排序）
        self._frames: List[str] = []
        IMG_EXT = {".jpg", ".jpeg", ".png"}
        for root, _, files in os.walk(archive_dir):
            subdir = os.path.basename(root)
            if subdir not in ("inspection", "refinery"):
                continue
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in IMG_EXT:
                    self._frames.append(os.path.join(root, f))
        self._frames.sort()
        self._cursor = 0

        if not self._frames:
            import time as _time
            print(f"[ArchiveDataSource] archive 暂无帧，等待 pipeline 产出帧 ({archive_dir}) ...")
            while not self._frames:
                _time.sleep(5)
                for root, _, files in os.walk(archive_dir):
                    subdir = os.path.basename(root)
                    if subdir not in ("inspection", "refinery"):
                        continue
                    for f in sorted(files):
                        if os.path.splitext(f)[1].lower() in IMG_EXT:
                            p = os.path.join(root, f)
                            if p not in self._frames:
                                self._frames.append(p)
                self._frames.sort()
            print(f"[ArchiveDataSource] 检测到 {len(self._frames)} 帧，开始回放")
        else:
            print(f"[ArchiveDataSource] 找到 {len(self._frames)} 帧，loop={loop}")

        # 尝试读取最新 comparison_report.json 作为初始 IoU 快照
        self._iou_snapshot = self._load_latest_iou(archive_dir)

    # ------------------------------------------------------------------

    def next_frame(self) -> FrameData:
        if self._cursor >= len(self._frames):
            if self._loop:
                self._cursor = 0
                self._prev_gray = None   # 跨循环重置 jitter 基准
            else:
                raise StopIteration("archive 帧已回放完毕")

        img_path = self._frames[self._cursor]
        self._cursor += 1
        self._fid    += 1

        cv2 = self._cv2
        bgr = cv2.imread(img_path)
        if bgr is None:
            # 读取失败时跳过（递归取下一帧）
            return self.next_frame()

        frame_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        gray      = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        h, w      = bgr.shape[:2]

        # ---- 物理指标 ----
        blur       = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(gray))

        if self._prev_gray is not None and self._prev_gray.shape == gray.shape:
            jitter = float(np.mean(np.abs(gray.astype(np.int16) - self._prev_gray.astype(np.int16))))
        else:
            jitter = 0.0
        self._prev_gray = gray

        # ---- 伪标签 / 检测框 ----
        base    = os.path.splitext(img_path)[0]
        txt_path = base + ".txt"
        dets, conf = self._parse_txt(txt_path, w, h)

        return FrameData(
            frame_id     = self._fid,
            timestamp    = time.time(),
            jitter       = jitter,
            blur         = blur,
            brightness   = brightness,
            confidence   = conf,
            frame_rgb    = frame_rgb,
            detections   = dets,
            iou_snapshot = self._iou_snapshot,
        )

    def get_iou_snapshot(self) -> Optional[float]:
        return self._iou_snapshot

    # ------------------------------------------------------------------
    # 私有辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_txt(
        txt_path: str, img_w: int, img_h: int
    ) -> tuple:
        """
        解析 YOLO .txt（6 列含 conf），返回 (detections, max_conf)。
        detections: [(x1,y1,x2,y2,conf,cls), ...]（像素坐标）
        """
        dets     = []
        max_conf = 0.0
        if not os.path.isfile(txt_path):
            return dets, max_conf
        with open(txt_path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                try:
                    cls = int(parts[0])
                    xc, yc, bw, bh = (float(p) for p in parts[1:5])
                    conf = float(parts[5]) if len(parts) >= 6 else 0.5
                except ValueError:
                    continue
                x1 = int((xc - bw / 2) * img_w)
                y1 = int((yc - bh / 2) * img_h)
                x2 = int((xc + bw / 2) * img_w)
                y2 = int((yc + bh / 2) * img_h)
                dets.append((
                    max(0, x1), max(0, y1),
                    min(img_w - 1, x2), min(img_h - 1, y2),
                    conf, cls,
                ))
                max_conf = max(max_conf, conf)
        return dets, max_conf

    @staticmethod
    def _load_latest_iou(archive_dir: str) -> Optional[float]:
        """扫描 labeled_return/ 找最新 comparison_report.json，提取 consistency_rate。"""
        lr_dir = os.path.join(os.path.dirname(archive_dir), "labeled_return")
        if not os.path.isdir(lr_dir):
            return None
        best_rate = None
        for root, _, files in os.walk(lr_dir):
            if "comparison_report.json" in files:
                try:
                    import json
                    with open(os.path.join(root, "comparison_report.json")) as fh:
                        data = json.load(fh)
                    rate = data.get("consistency_rate")
                    if rate is not None:
                        best_rate = float(rate)
                except Exception:
                    pass
        return best_rate


class LivePipelineSource(DataSource):
    """
    --source live：轮询 DB production_history 表，接收 main.py --guard 的实时输出。
    TODO v3：SELECT 最新 batch_metrics 行，将批次级指标降级为帧级近似值；
             逐帧 Blur/Jitter 需在 qc_engine 写一份轻量 ring buffer 到共享 DB。
    """
    def next_frame(self) -> FrameData:
        raise NotImplementedError("LivePipelineSource 尚未实现，请用 --source mock")

    def get_iou_snapshot(self) -> Optional[float]:
        raise NotImplementedError


# ── 工厂函数 ──────────────────────────────────────────────────────────────

def build_source(source: str, archive_dir: str = "storage/archive", **kwargs) -> DataSource:
    """根据 --source 参数返回对应 DataSource 实例。"""
    if source == "mock":
        return MockDataSource(**kwargs)
    elif source == "archive":
        return ArchiveDataSource(archive_dir=archive_dir)
    elif source == "live":
        return LivePipelineSource()
    else:
        raise ValueError(f"未知数据源: {source!r}，可选 mock / archive / live")
