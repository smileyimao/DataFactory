#!/usr/bin/env python3
# dashboard/hq.py — HQ Global Command Center 主入口
"""
只读全局监控，独立运行，与 sentinel.py 互不干扰。

启动:
  python dashboard/hq.py                  # port 8767，mock 指标
  python dashboard/hq.py --port 8900
  python dashboard/hq.py --no-db          # 强制 mock DB（离线调试用）

依赖（同 sentinel.py，已在 requirements.txt 中）:
  dash>=2.0  plotly>=5.0  pillow>=9.0  psutil>=5.0
"""
import argparse
import json as _json
import os
import random
import sys
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

# ── sys.path 设置 ────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR   = os.path.dirname(_SCRIPT_DIR)
for _p in (_BASE_DIR, _SCRIPT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dash
from dash import Input, Output, State, html

from hq_layout import (
    build_hq_layout,
    make_world_map, make_topology,
    make_storage_ring, make_compute_bars,
    make_metric_gauge, make_hw_panel,
    make_site_tiles,
    render_odometer,
    GREEN, ICE, AMBER, RED, DIM, TEXT, _MONO,
)

# ── HQ 常量 ──────────────────────────────────────────────────────────────
GOLD_BASE       = 1_248_500    # 历史归档基数（展示用）
GOLD_SCALE      = 300          # file_count → 帧数估算系数

STORAGE_USED_PB = 1.2
STORAGE_TOTAL_PB= 5.0
H100_UTILS      = [22, 19, 24, 21, 18, 23, 20, 22]   # Mock 8× H100 利用率
DAILY_YIELD     = 98.2

THR_CONF        = 0.40     # Confidence 报警门槛
THR_CLARITY     = 40.0     # Clarity 报警门槛（%）
THR_IOU         = 0.95     # IoU 报警门槛

# 数据包动画：每 tick +0.02，50 秒绕地球一圈
PACKET_STEP     = 0.02

_session_start  = datetime.now()

# CPU 历史环形缓冲（60 个采样点 → Sparkline 毛刺感）
_cpu_history: deque = deque(maxlen=60)

# ── 站点时区偏移（UTC offset，用于 phase 计算）──────────────────────────
_SITE_UTC_OFFSETS = {"SUDBURY": -5, "PILBARA": 8, "ATACAMA": -3}

def _get_phase(site_name: str) -> str:
    """根据站点本地时刻返回 Day / Night / Sunrise / Sunset。"""
    offset = _SITE_UTC_OFFSETS.get(site_name, 0)
    local_hour = (datetime.now(timezone.utc) + timedelta(hours=offset)).hour
    if 5  <= local_hour < 7:  return "Sunrise"
    if 7  <= local_hour < 19: return "Day"
    if 19 <= local_hour < 21: return "Sunset"
    return "Night"

# ── Open-Meteo 天气轮询（无需 API Key，10 分钟缓存）──────────────────────
_WEATHER_CACHE: Dict[str, Any] = {"ts": 0.0}
_SITE_COORDS = {
    "SUDBURY": ( 46.49,  -80.99),
    "PILBARA": (-21.13,  119.47),
    "ATACAMA": (-23.65,  -70.41),
}
_WMO_EMOJI: Dict[int, str] = {
    0: "☀", 1: "🌤", 2: "⛅", 3: "☁",
    45: "🌫", 48: "🌫",
    51: "🌦", 53: "🌧", 55: "🌧", 61: "🌧", 63: "🌧", 65: "🌧",
    71: "🌨", 73: "❄", 75: "❄", 77: "❄",
    80: "🌦", 81: "🌧", 82: "⛈",
    85: "🌨", 86: "❄",
    95: "⛈", 96: "⛈", 99: "⛈",
}

def _poll_weather() -> dict:
    """
    每 600 秒从 Open-Meteo 拉取三站点实时气温 + 天气码。
    无需 API Key；失败时保留上次缓存值。
    """
    now = time.time()
    if now - _WEATHER_CACHE.get("ts", 0) < 600.0:
        return _WEATHER_CACHE

    for name, (lat, lon) in _SITE_COORDS.items():
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,weathercode&timezone=auto"
            )
            with urllib.request.urlopen(url, timeout=5) as r:
                data = _json.loads(r.read())
            cur   = data.get("current", {})
            temp_c = cur.get("temperature_2m")
            wcode  = int(cur.get("weathercode", 0))
            emoji  = _WMO_EMOJI.get(wcode, "~")
            temp_s = f"{temp_c:.0f}°C" if temp_c is not None else "N/A"
            _WEATHER_CACHE[name] = {
                "temp":  temp_s,
                "emoji": emoji,
                "phase": _get_phase(name),
            }
        except Exception:
            # 保留上次缓存；若从未成功则 phase 至少动态计算
            if name not in _WEATHER_CACHE:
                _WEATHER_CACHE[name] = {"temp": "N/A", "emoji": "~",
                                        "phase": _get_phase(name)}
            else:
                _WEATHER_CACHE[name]["phase"] = _get_phase(name)

    _WEATHER_CACHE["ts"] = now
    return _WEATHER_CACHE

# ── psutil 硬件轮询（3 秒缓存）────────────────────────────────────────────
_hw_cache: Dict[str, Any] = {"ts": 0.0}

def _poll_hw() -> dict:
    now = time.time()
    if now - _hw_cache.get("ts", 0) < 3.0:
        return _hw_cache
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        temp_str = "N/A"
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                all_t = [t.current for readings in temps.values() for t in readings]
                if all_t:
                    temp_str = f"{max(all_t):.0f}°C"
        except AttributeError:
            pass

        thermal = "ELEVATED" if temp_str != "N/A" and float(temp_str[:-2]) > 80 else "OK"

        bat_str = "N/A"
        try:
            bat = psutil.sensors_battery()
            if bat:
                bat_str = (
                    f"{bat.percent:.0f}%  Charging"
                    if bat.power_plugged else
                    f"{bat.percent:.0f}%  Battery"
                )
        except AttributeError:
            pass

        _cpu_history.append(cpu)
        _hw_cache.update({"ts": now, "cpu": cpu, "mem": mem,
                          "temp": temp_str, "thermal": thermal, "bat": bat_str})
    except Exception:
        _hw_cache.setdefault("cpu",     50.0)
        _hw_cache.setdefault("mem",     60.0)
        _hw_cache.setdefault("temp",    "N/A")
        _hw_cache.setdefault("thermal", "OK")
        _hw_cache.setdefault("bat",     "N/A")
    return _hw_cache


# ── DB 查询（带降级）────────────────────────────────────────────────────
_db_cache: Dict[str, Any] = {"ts": 0.0, "gold": GOLD_BASE,
                              "conf": 0.72, "clarity": 85.0, "iou": 0.964}

def _poll_db(db_url: str) -> dict:
    """
    每 30 秒从 DB 读一次 batch_metrics 汇总。
    失败时返回缓存 + mock 漂移，保持 UI 刷新。
    """
    now = time.time()
    if now - _db_cache.get("ts", 0) < 30.0:
        # 在缓存有效期内，mock 指标做轻微随机漂移（保持 UI 活性）
        _db_cache["conf"]    = max(0.05, min(0.99,
            _db_cache["conf"] * 0.95 + random.gauss(0.72, 0.02) * 0.05))
        _db_cache["clarity"] = max(0.0, min(100.0,
            _db_cache["clarity"] * 0.97 + random.gauss(85.0, 3.0) * 0.03))
        return _db_cache

    try:
        from engines.db_connection import connect
        conn = connect(db_url)
        cur  = conn.cursor()

        # Gold Frames = SUM(file_count) × GOLD_SCALE + GOLD_BASE
        cur.execute("SELECT COALESCE(SUM(file_count), 0) FROM batch_metrics")
        row = cur.fetchone()
        file_sum = int(row[0]) if row and row[0] else 0
        gold = GOLD_BASE + file_sum * GOLD_SCALE

        # 最新 IoU（最近一次 label_import 的 consistency_rate）
        try:
            cur.execute(
                "SELECT consistency_rate FROM label_import "
                "ORDER BY imported_at DESC LIMIT 1"
            )
            r = cur.fetchone()
            iou = float(r[0]) if r and r[0] is not None else _db_cache["iou"]
        except Exception:
            iou = _db_cache["iou"]

        conn.close()
        _db_cache.update({
            "ts":      now,
            "gold":    gold,
            "iou":     iou,
            "conf":    max(0.05, min(0.99, random.gauss(0.72, 0.03))),
            "clarity": max(0.0,  min(100.0, random.gauss(85.0, 6.0))),
        })
    except Exception:
        _db_cache["ts"] = now   # 避免每秒重试
    return _db_cache


# ── Dash 应用 ──────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    title        = "HQ COMMAND",
    update_title = None,
    suppress_callback_exceptions = True,
    assets_folder = os.path.join(_SCRIPT_DIR, "assets"),
)
app.layout = build_hq_layout()

_DB_URL = ""   # 由 main() 注入


@app.callback(
    [
        Output("hq-status-bar",         "children"),
        Output("hq-world-map",          "figure"),
        Output("hq-topology",           "figure"),
        Output("hq-odometer",           "children"),
        Output("hq-hw-panel",           "children"),
        Output("hq-storage",            "figure"),
        Output("hq-compute",            "figure"),
        Output("hq-daily-yield",        "children"),
        Output("hq-gauge-conf-plot",    "figure"),
        Output("hq-gauge-clarity-plot", "figure"),
        Output("hq-gauge-iou-plot",     "figure"),
        Output("hq-sites",              "children"),
        Output("hq-store",              "data"),
    ],
    Input("hq-tick",   "n_intervals"),
    State("hq-store",  "data"),
)
def refresh(_n, store):
    store = store or {"packet_pos": 0.0, "gold": GOLD_BASE}

    # ── 动画推进 ────────────────────────────────────────────────────────
    pos = (store["packet_pos"] + PACKET_STEP) % 1.0

    packet_lon = -80.99 + (119.47 - (-80.99)) * pos
    trail_lons = [
        -80.99 + (119.47 - (-80.99)) * ((pos - (i + 1) * PACKET_STEP) % 1.0)
        for i in range(3)
    ]
    packet_x = pos * 6.0

    # ── DB / Mock 数据 ───────────────────────────────────────────────────
    db      = _poll_db(_DB_URL)
    gold    = db["gold"]
    conf    = db["conf"]
    clarity = db["clarity"]
    iou     = db["iou"]

    # ── 本地硬件 ────────────────────────────────────────────────────────
    hw = _poll_hw()

    # ── 天气（10 分钟缓存，Open-Meteo）──────────────────────────────────
    weather = _poll_weather()

    # ── 状态栏 ──────────────────────────────────────────────────────────
    elapsed = datetime.now() - _session_start
    s  = int(elapsed.total_seconds())
    hh, mm, ss = s // 3600, (s % 3600) // 60, s % 60
    status = (
        f"● ONLINE  |  Session {_session_start.strftime('%Y-%m-%d  %H:%M')}"
        f"  [{hh:02d}:{mm:02d}:{ss:02d}]  |  "
        f"Sites  3  Active  |  "
        f"Conf  {conf:.3f}  Clarity  {clarity:.0f}%  IoU  {iou:.3f}"
    )

    # ── Plotly 图表 ──────────────────────────────────────────────────────
    world   = make_world_map(packet_lon, trail_lons=trail_lons)
    topo    = make_topology(packet_x)
    storage = make_storage_ring(STORAGE_USED_PB, STORAGE_TOTAL_PB)
    compute = make_compute_bars(H100_UTILS)

    g_conf    = make_metric_gauge("CONFIDENCE", conf,    0.0,   1.0,  THR_CONF,    "",  high_is_bad=False)
    g_clarity = make_metric_gauge("CLARITY",    clarity, 0.0, 100.0,  THR_CLARITY, "%", high_is_bad=False)
    g_iou     = make_metric_gauge("IoU",        iou,     0.0,   1.0,  THR_IOU,     "",  high_is_bad=False)

    # ── HTML 组件 ────────────────────────────────────────────────────────
    odometer  = render_odometer(int(gold))
    hw_panel  = make_hw_panel(
        cpu_pct     = hw.get("cpu",     50.0),
        mem_pct     = hw.get("mem",     60.0),
        cpu_temp    = hw.get("temp",    "N/A"),
        battery     = hw.get("bat",     "N/A"),
        thermal     = hw.get("thermal", "OK"),
        cpu_history = list(_cpu_history),
    )
    yield_color = RED if DAILY_YIELD < 95.0 else (AMBER if DAILY_YIELD < 98.0 else GREEN)
    daily_yield = html.Span(f"{DAILY_YIELD:.1f}%", style={"color": yield_color})
    sites_panel = make_site_tiles(weather)

    new_store = {"packet_pos": pos, "gold": gold}
    return (
        status,
        world,
        topo,
        odometer,
        hw_panel,
        storage,
        compute,
        daily_yield,
        g_conf,
        g_clarity,
        g_iou,
        sites_panel,
        new_store,
    )


# ── 入口 ──────────────────────────────────────────────────────────────────

def main() -> None:
    global _DB_URL

    parser = argparse.ArgumentParser(
        description="HQ Global Command Center — DataFactory V3",
    )
    parser.add_argument("--port",  type=int, default=8767)
    parser.add_argument("--no-db", action="store_true",
                        help="强制 Mock DB（不读 batch_metrics，离线调试）")
    args = parser.parse_args()

    if not args.no_db:
        try:
            from config.config_loader import load_config
            cfg = load_config()
            _DB_URL = cfg.get("paths", {}).get("db_url", "")
        except Exception as e:
            print(f"[HQ] 配置加载失败，使用 Mock DB: {e}")
            _DB_URL = ""
    else:
        print("[HQ] --no-db: 使用 Mock 数据")

    print(f"[HQ] 看板: http://localhost:{args.port}")
    print("[HQ] 停止: Ctrl-C")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
