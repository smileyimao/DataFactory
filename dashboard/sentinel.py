#!/usr/bin/env python3
# dashboard/sentinel.py — SENTINEL-1 主入口
"""
只监控，不干预。实时遥测看板，独立运行，不依赖 main.py 进程。

启动:
  python dashboard/sentinel.py                    # mock 模式，port 8766
  python dashboard/sentinel.py --source mock
  python dashboard/sentinel.py --source archive   # TODO v2
  python dashboard/sentinel.py --source live      # TODO v3
  python dashboard/sentinel.py --port 9000

依赖（pip install）:
  dash>=2.0  plotly>=5.0  pillow>=9.0  psutil>=5.0
  GPUtil（可选，GPU 温度）
"""
import argparse
import csv
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

# ── sys.path 设置（支持 python dashboard/sentinel.py 直接运行）────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR   = os.path.dirname(_SCRIPT_DIR)
for _p in (_BASE_DIR, _SCRIPT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dash
from dash import Input, Output, html

from sensor_module    import FrameData, build_source
from inference_module import IoUTracker, draw_frame, _placeholder_frame
import layout as _L

# ── 遥测常量（对齐 settings.yaml 默认值）────────────────────────────────
HISTORY        = 300       # 环形缓冲帧数（SPC 计算窗口）
MINI_LEN       = 60        # 小趋势图显示帧数

THR_JITTER     = 35.0      # px — 超出 → Type_A
THR_BLUR_MIN   = 20.0      # Laplacian var — 低于 → Type_A（内部用）
THR_CLARITY    = 15.0      # Clarity % — 低于 → Type_A（展示用，= THR_BLUR_MIN/1.5）
THR_CONF       = 0.40      # 置信度 — 低于 → Type_B
THR_IOU        = 0.95      # IoU 快照 — 低于 → Type_C

# SPC 先验基准（方案 B：历史均值 + 滚动 σ）
SPC_PRIOR_MEAN = 0.72
SPC_PRIOR_STD  = 0.08

# ── 全局状态（单进程单用户监控服务，全局变量合理）────────────────────────
_buf:         Deque[FrameData] = deque(maxlen=HISTORY)
_buf_lock     = threading.Lock()
_iou_tracker  = IoUTracker()

_alert_counts: Dict[str, int] = {"A": 0, "B": 0, "C": 0}
_session_start = datetime.now()
_fps_state:    Dict[str, Any] = {"frames": 0, "last_ts": time.time(), "fps": 0.0}

# 最新渲染帧（CPython GIL 保护单次引用赋值，无需额外锁）
_latest_b64: Optional[str] = None
_log_path:   str = ""


# ── CSV 静默日志 ──────────────────────────────────────────────────────────

def _init_log(log_dir: str) -> str:
    os.makedirs(log_dir, exist_ok=True)
    fname = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path  = os.path.join(log_dir, fname)
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            ["Timestamp", "Frame_ID", "Jitter", "Blur",
             "Brightness", "Confidence", "IoU", "Alert_Type"]
        )
    return path


def _log_alert(fd: FrameData, alert_type: str) -> None:
    """静默追加一行到 CSV，不阻塞采集线程（顺序写，单线程调用）。"""
    iou = _iou_tracker.latest
    with open(_log_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.fromtimestamp(fd.timestamp).isoformat(timespec="milliseconds"),
            fd.frame_id,
            f"{fd.jitter:.2f}",
            f"{fd.blur:.2f}",
            f"{fd.brightness:.1f}",
            f"{fd.confidence:.4f}",
            f"{iou:.4f}" if iou is not None else "",
            alert_type,
        ])


# ── 后台采集线程 ──────────────────────────────────────────────────────────

def _acquire_loop(source, target_fps: float) -> None:
    """
    以 target_fps 速率从数据源拉帧：
      1. 更新 IoU 快照
      2. 渲染帧（PIL 叠加检测框 / FPS / 温度）
      3. 写入环形缓冲
      4. 静默检测 Type_A/B/C 并写 CSV
    """
    global _latest_b64
    interval = 1.0 / max(target_fps, 1.0)

    while True:
        t0 = time.monotonic()
        try:
            fd = source.next_frame()
        except NotImplementedError:
            raise
        except Exception:
            time.sleep(interval)
            continue

        # ---- IoU 快照 ----
        snap = source.get_iou_snapshot()
        if snap is not None and snap != _iou_tracker.latest:
            _iou_tracker.update(snap, datetime.now().strftime("%H:%M:%S"))

        # ---- FPS 计算（1 秒滑窗）----
        _fps_state["frames"] += 1
        now = time.time()
        elapsed = now - _fps_state["last_ts"]
        if elapsed >= 1.0:
            _fps_state["fps"] = _fps_state["frames"] / elapsed
            _fps_state["frames"] = 0
            _fps_state["last_ts"] = now

        # ---- 帧渲染（PIL，含检测框叠加）----
        try:
            _latest_b64 = draw_frame(
                fd.frame_rgb, fd.detections,
                fps=_fps_state["fps"], frame_id=fd.frame_id,
            )
        except Exception:
            pass

        # ---- 写入缓冲 ----
        with _buf_lock:
            _buf.append(fd)

        # ---- 静默报警检测 ----
        if fd.jitter > THR_JITTER or fd.blur < THR_BLUR_MIN:
            _alert_counts["A"] += 1
            if _log_path:
                _log_alert(fd, "Type_A")

        if fd.confidence < THR_CONF:
            _alert_counts["B"] += 1
            if _log_path:
                _log_alert(fd, "Type_B")

        iou_now = _iou_tracker.latest
        if iou_now is not None and iou_now < THR_IOU:
            _alert_counts["C"] += 1
            if _log_path:
                _log_alert(fd, "Type_C")

        # ---- 速率控制 ----
        sleep_t = interval - (time.monotonic() - t0)
        if sleep_t > 0:
            time.sleep(sleep_t)


# ── Dash 应用 ─────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    title      = "SENTINEL-1",
    update_title = None,
    suppress_callback_exceptions = True,
)
app.layout = _L.build_layout()


@app.callback(
    [
        Output("status-bar",      "children"),
        Output("gauge-jitter",    "figure"),
        Output("trend-jitter",    "figure"),
        Output("gauge-blur",      "figure"),
        Output("trend-blur",      "figure"),
        Output("gauge-brightness","figure"),
        Output("trend-brightness","figure"),
        Output("live-feed",       "src"),
        Output("conf-value",      "children"),
        Output("conf-value",      "style"),
        Output("conf-bar",        "children"),
        Output("iou-value",       "children"),
        Output("iou-value",       "style"),
        Output("iou-timestamp",   "children"),
        Output("alert-counts",    "children"),
        Output("spc-chart",       "figure"),
    ],
    Input("tick", "n_intervals"),
)
def refresh(_n):
    import numpy as np

    with _buf_lock:
        frames = list(_buf)

    if not frames:
        raise dash.exceptions.PreventUpdate

    latest    = frames[-1]
    tail      = lambda lst: lst[-MINI_LEN:]

    jitter_h  = [f.jitter     for f in frames]
    blur_h    = [f.blur       for f in frames]
    clarity_h = [min(100.0, b / 1.5) for b in blur_h]   # 归一化到 0-100%
    bright_h  = [f.brightness for f in frames]
    conf_h    = [f.confidence for f in frames]
    fid_h     = [f.frame_id   for f in frames]

    # ---- 状态栏 ----
    elapsed   = datetime.now() - _session_start
    secs      = int(elapsed.total_seconds())
    hh, mm, ss = secs // 3600, (secs % 3600) // 60, secs % 60
    status = (
        f"● LIVE  |  Session {_session_start.strftime('%Y-%m-%d  %H:%M')}"
        f"  [{hh:02d}:{mm:02d}:{ss:02d}]  |  "
        f"Frames  {latest.frame_id:,}  |  "
        f"Alerts  {_alert_counts['A']}A / {_alert_counts['B']}B / {_alert_counts['C']}C"
        + (f"  |  Log → {os.path.basename(_log_path)}" if _log_path else "")
    )

    # ---- 仪表 + 趋势 ----
    clarity   = min(100.0, latest.blur / 1.5)
    j_color = _L.RED if latest.jitter > THR_JITTER else _L.GREEN
    b_color = _L.RED if clarity       < THR_CLARITY else _L.GREEN

    g_jitter   = _L.make_gauge("JITTER",   latest.jitter, 0,   60,  THR_JITTER,  "px", high_is_bad=True)
    t_jitter   = _L.make_mini_trend(tail(jitter_h),  "Jitter  60f",  color=j_color)
    g_blur     = _L.make_gauge("CLARITY",  clarity,       0,  100,  THR_CLARITY, "%",  high_is_bad=False)
    t_blur     = _L.make_mini_trend(tail(clarity_h), "Clarity  60f", color=b_color)
    g_bright   = _L.make_gauge("BRIGHTNESS", latest.brightness, 0,  255,  55.0,          "",  high_is_bad=False)
    t_bright   = _L.make_mini_trend(tail(bright_h), "Brightness  60f")

    # ---- 视频帧 ----
    feed_src = _latest_b64 or _placeholder_frame()

    # ---- 置信度显示 ----
    conf = latest.confidence
    if conf < THR_CONF:
        c_color = _L.RED
    elif conf < 0.60:
        c_color = _L.AMBER
    else:
        c_color = _L.GREEN

    conf_style = {
        "fontSize": "46px", "fontWeight": "bold",
        "color": c_color, "lineHeight": "1", "fontFamily": "monospace",
    }
    conf_bar = _make_bar(int(conf * 100), c_color)

    # ---- IoU 快照 ----
    iou = _iou_tracker.latest
    if iou is not None:
        iou_disp  = f"{iou:.3f}"
        iou_color = _L.RED if iou < THR_IOU else _L.GREEN
        iou_ts    = f"Updated  {_iou_tracker.last_ts or '—'}"
    else:
        iou_disp  = "—"
        iou_color = _L.DIM
        iou_ts    = "Awaiting  labeled_return  import"

    iou_style = {
        "fontSize": "34px", "fontWeight": "bold",
        "color": iou_color, "lineHeight": "1", "fontFamily": "monospace",
    }

    # ---- 报警计数 ----
    alert_block = _make_alert_block()

    # ---- SPC（先验 → 滚动均值，20 帧切换）----
    if len(conf_h) >= 20:
        cl  = float(np.mean(conf_h))
        std = float(np.std(conf_h))
    else:
        cl  = SPC_PRIOR_MEAN
        std = SPC_PRIOR_STD
    ucl = min(1.0, cl + 3 * std)
    lcl = max(0.0, cl - 3 * std)
    spc = _L.make_spc_chart(conf_h, fid_h, cl, ucl, lcl)

    return (
        status,
        g_jitter, t_jitter,
        g_blur,   t_blur,
        g_bright, t_bright,
        feed_src,
        f"{conf:.3f}", conf_style, conf_bar,
        iou_disp, iou_style, iou_ts,
        alert_block,
        spc,
    )


# ── UI 辅助组件 ───────────────────────────────────────────────────────────

def _make_bar(pct: int, color: str) -> html.Div:
    """水平进度条（置信度可视化）。"""
    return html.Div(
        style={
            "width": "100%", "height": "5px",
            "backgroundColor": _L.GRID, "borderRadius": "3px", "overflow": "hidden",
        },
        children=[html.Div(style={
            "width": f"{max(0, min(100, pct))}%", "height": "100%",
            "backgroundColor": color, "transition": "width 0.4s ease",
        })],
    )


def _make_alert_block() -> html.Div:
    """三行报警计数（Type_A / B / C）。"""
    def _row(label: str, count: int, color: str) -> html.Div:
        return html.Div(
            style={"display": "flex", "justifyContent": "space-between",
                   "marginBottom": "4px"},
            children=[
                html.Span(label, style={"color": _L.DIM,  "fontSize": "10px"}),
                html.Span(str(count),
                          style={"color": color, "fontSize": "10px",
                                 "fontWeight": "bold"}),
            ],
        )
    return html.Div([
        _row("Type_A  Physical",   _alert_counts["A"], _L.AMBER),
        _row("Type_B  Confidence", _alert_counts["B"], _L.RED),
        _row("Type_C  IoU",        _alert_counts["C"], _L.RED),
    ])


# ── 入口 ──────────────────────────────────────────────────────────────────

def main() -> None:
    global _log_path

    parser = argparse.ArgumentParser(
        description="SENTINEL-1 — DataFactory V3 遥测看板（只读）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "数据源:\n"
            "  mock    纯软件仿真（默认，无需硬件）\n"
            "  archive 回放 storage/archive/ 归档帧（TODO v2）\n"
            "  live    接入 main.py --guard 实时输出（TODO v3）\n"
        ),
    )
    parser.add_argument("--source",  choices=["mock", "archive", "live"], default="mock")
    parser.add_argument("--port",    type=int,   default=8766)
    parser.add_argument("--fps",         type=float, default=30.0,
                        help="采集帧率（archive 模式控制回放速度）")
    parser.add_argument("--archive-dir", default=os.path.join(_BASE_DIR, "storage/archive"),
                        help="archive 数据源根目录（--source archive 时使用）")
    parser.add_argument("--log-dir",     default=os.path.join(_BASE_DIR, "logs"),
                        help="session_log.csv 写入目录")
    parser.add_argument("--no-log",      action="store_true",
                        help="禁用 CSV 静默日志")
    args = parser.parse_args()

    if not args.no_log:
        _log_path = _init_log(args.log_dir)
        print(f"[SENTINEL-1] 日志: {_log_path}")

    source = build_source(args.source, archive_dir=args.archive_dir)
    print(f"[SENTINEL-1] 数据源: {args.source}  |  采集 {args.fps:.0f} fps")

    t = threading.Thread(
        target   = _acquire_loop,
        args     = (source, args.fps),
        daemon   = True,
        name     = "sentinel-acquire",
    )
    t.start()

    print(f"[SENTINEL-1] 看板: http://localhost:{args.port}")
    print(f"[SENTINEL-1] 停止: Ctrl-C")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
