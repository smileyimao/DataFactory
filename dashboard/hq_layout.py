# dashboard/hq_layout.py — HQ Command Center 布局 + 图表工厂
"""
颜色常量、Plotly 图表工厂函数、Dash HTML 组件构造器。
hq.py 只引用这里，不直接写 HTML 或 Plotly。
"""
from dash import html, dcc
import plotly.graph_objects as go

# ── 调色板 ───────────────────────────────────────────────────────────────
BG    = "#1A1A1A"
PANEL = "#111111"
GREEN = "#39FF14"   # Active / 正常
ICE   = "#00F2FF"   # Stable / 冰蓝主色
AMBER = "#FFB300"   # Warning / Calibrating
RED   = "#FF3B3B"   # Alert
DIM   = "#555555"
GRID  = "#2A2A2A"
TEXT  = "#C8C8C8"
_MONO = "JetBrains Mono, Courier New, monospace"

_PANEL = {
    "backgroundColor": "rgba(11, 11, 11, 0.90)",
    "border": "0.8px solid rgba(255, 255, 255, 0.07)",
    "borderRadius": "4px",
    "padding": "10px 12px",
    "backdropFilter": "blur(6px)",
    "WebkitBackdropFilter": "blur(6px)",
    "boxShadow": "0 4px 20px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.025)",
}
_GRAPH_CFG = {"displayModeBar": False}

# 十六进制数据流内容（重复两次保证 CSS translateX(-50%) 无缝循环）
_HEX_RAW = (
    "4F 2A 3C D1  8B FF 12 A9  55 7E C3 01  98 6D 44 BB  "
    "29 E0 73 F4  1C 8A 2F 5B  9D 0E 67 A3  3E C8 B2 4A  "
    "7F 21 5C 90  D6 13 88 E4  47 BC 09 FE  6A 31 C0 5D  "
    "A7 82 1F 64  0B 39 DA 76  EF 28 93 B5  "
)
_HEX_STREAM_CONTENT = _HEX_RAW * 2   # 无缝循环

# ── 站点定义 ────────────────────────────────────────────────────────────
SITES = [
    {
        "name": "SUDBURY",       "region": "Canada",    "lat":  46.49, "lon": -80.99,
        "status": "Active",      "phase": "Day",        "temp": "-12°C",
        "color": GREEN,          "dot_class": "active", "task": "YOLO Inference",
    },
    {
        "name": "PILBARA",       "region": "Australia", "lat": -21.13, "lon": 119.47,
        "status": "Standby",     "phase": "Night",      "temp": "34°C",
        "color": ICE,            "dot_class": "",       "task": "Idle",
    },
    {
        "name": "ATACAMA",       "region": "Chile",     "lat": -23.65, "lon": -70.41,
        "status": "Calibrating", "phase": "Sunrise",    "temp": "15°C",
        "color": AMBER,          "dot_class": "",       "task": "Sensor Cal",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# Plotly 图表工厂
# ═══════════════════════════════════════════════════════════════════════════

def _make_cpu_sparkline(history: list) -> dcc.Graph:
    """CPU 利用率实时扰动 Sparkline（嵌入 HW 面板底部）。"""
    y = history if history else [50.0]
    fig = go.Figure(go.Scatter(
        y=y, mode="lines",
        line=dict(color=GREEN, width=1.2),
        fill="tozeroy",
        fillcolor="rgba(57,255,20,0.06)",
    ))
    fig.update_layout(
        height=42,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, range=[0, 100]),
        showlegend=False,
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False},
                     style={"height": "42px", "marginTop": "6px"})


def make_world_map(packet_lon: float = -80.99,
                   trail_lons: list = None) -> go.Figure:
    """
    暗色 Scattergeo 地图。
    Sudbury 双圈高亮（模拟雷达 ping）+ 卫星弧线 + 移动数据包。
    packet_lon 由 dcc.Interval 每秒驱动，范围 -80.99 → 119.47。
    """
    fig = go.Figure()

    # Sudbury 光晕环（两圈，静态模拟脉冲）
    for sz, op in [(34, 0.22), (54, 0.09)]:
        fig.add_trace(go.Scattergeo(
            lat=[46.49], lon=[-80.99], mode="markers",
            marker=dict(size=sz, color=GREEN, opacity=op),
            showlegend=False, hoverinfo="skip",
        ))

    # 卫星弧线（经中间洋面弯曲，虚线）
    fig.add_trace(go.Scattergeo(
        lat=[46.49, 10.0, -21.13], lon=[-80.99, 20.0, 119.47],
        mode="lines",
        line=dict(color=ICE, width=0.8, dash="dot"),
        showlegend=False, hoverinfo="skip", opacity=0.35,
    ))

    # 站点主点 + 标签
    for s in SITES:
        fig.add_trace(go.Scattergeo(
            lat=[s["lat"]], lon=[s["lon"]],
            mode="markers+text",
            marker=dict(size=10, color=s["color"], symbol="circle",
                        line=dict(color=s["color"], width=1)),
            text=[s["name"]],
            textposition="top right",
            textfont=dict(color=s["color"], size=9, family=_MONO),
            showlegend=False,
            hovertemplate=f"<b>{s['name']}</b><br>{s['status']} · {s['temp']}<extra></extra>",
        ))

    # 彗星拖尾（3 个衰减点，模拟光纤传输感）
    if trail_lons:
        trail_cfg = [(5, 0.40), (4, 0.20), (3, 0.08)]
        for tlon, (tsz, top) in zip(trail_lons, trail_cfg):
            fig.add_trace(go.Scattergeo(
                lat=[15.0], lon=[tlon], mode="markers",
                marker=dict(size=tsz, color=ICE, opacity=top),
                showlegend=False, hoverinfo="skip",
            ))

    # 彗星头部（主数据包）
    fig.add_trace(go.Scattergeo(
        lat=[15.0], lon=[packet_lon],
        mode="markers",
        marker=dict(size=8, color=ICE, symbol="circle",
                    line=dict(color="#FFFFFF", width=1)),
        showlegend=False, hoverinfo="skip",
    ))

    fig.update_layout(
        geo=dict(
            showland=True,       landcolor="#3D6B48",
            showocean=True,      oceancolor="#152D4A",
            showcoastlines=True, coastlinecolor="#60A070", coastlinewidth=1.0,
            showcountries=True,  countrycolor="#4A6858",
            showlakes=True,      lakecolor="#152D4A",
            showrivers=False,
            showframe=False,
            bgcolor="#141414",
            projection_type="natural earth",
        ),
        paper_bgcolor="#0B0B0B",
        plot_bgcolor="#0B0B0B",
        margin=dict(l=0, r=0, t=0, b=0),
        template=None,
        uirevision="world-map",          # 保持视角，只更新数据包 trace，消除闪烁
        transition={"duration": 900, "easing": "linear"},   # 平滑插值替代硬切换
    )
    return fig


def make_topology(packet_x: float = 0.0) -> go.Figure:
    """
    三节点拓扑：SUDBURY-01 Edge → DATA-LINK → HQ-CENTRAL Cloud。
    节点 x 间距扩大到 3 个单位，annotation 垂直三层错开，防窄屏叠字。
    packet_x 范围 0 → 6（与新间距匹配）。
    """
    fig = go.Figure()

    NODES = [
        {"x": 0, "label": "SUDBURY-01", "status": "Active",  "task": "YOLO Inference", "color": GREEN},
        {"x": 3, "label": "DATA-LINK",  "status": "Stable",  "task": "120 Mbps",       "color": ICE},
        {"x": 6, "label": "HQ-CENTRAL", "status": "Online",  "task": "SPC Audit",      "color": GREEN},
    ]

    # 连接线（虚线）
    for x0, x1 in [(0.30, 2.70), (3.30, 5.70)]:
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[0, 0], mode="lines",
            line=dict(color=ICE, width=1.2, dash="dot"),
            showlegend=False, hoverinfo="skip",
        ))

    # 方向箭头
    for xb in [2.70, 5.70]:
        fig.add_annotation(
            x=xb + 0.01, y=0, ax=xb - 0.40, ay=0,
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=3, arrowcolor=ICE, arrowsize=0.9, arrowwidth=1.4,
            showarrow=True,
        )

    for n in NODES:
        # 外圈光晕
        fig.add_trace(go.Scatter(
            x=[n["x"]], y=[0], mode="markers",
            marker=dict(size=44, color=n["color"], opacity=0.08),
            showlegend=False, hoverinfo="skip",
        ))
        # 核心点（纯 marker，不内嵌文字，防叠字）
        fig.add_trace(go.Scatter(
            x=[n["x"]], y=[0], mode="markers",
            marker=dict(size=12, color=n["color"]),
            showlegend=False,
            hovertemplate=f"<b>{n['label']}</b><br>{n['status']}<br>{n['task']}<extra></extra>",
        ))
        # 三层垂直 annotation
        fig.add_annotation(x=n["x"], y=0.75,
            text=f"<b>{n['label']}</b>", showarrow=False,
            font=dict(color=n["color"], size=9, family=_MONO))
        fig.add_annotation(x=n["x"], y=0.46,
            text=f"● {n['status']}", showarrow=False,
            font=dict(color=n["color"], size=8, family=_MONO))
        fig.add_annotation(x=n["x"], y=0.20,
            text=n["task"], showarrow=False,
            font=dict(color=DIM, size=7, family=_MONO))

    # 移动数据包（range 扩大到 6）
    if 0.0 < packet_x < 6.0:
        fig.add_trace(go.Scatter(
            x=[packet_x], y=[0], mode="markers",
            marker=dict(size=8, color=ICE, symbol="circle",
                        line=dict(color="#FFFFFF", width=1)),
            showlegend=False, hoverinfo="skip",
        ))

    fig.update_layout(
        margin=dict(l=6, r=6, t=6, b=6),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, range=[-0.9, 6.9]),
        yaxis=dict(visible=False, range=[-0.55, 1.05]),
    )
    return fig


def make_storage_ring(used_pb: float = 1.2, total_pb: float = 5.0) -> go.Figure:
    """存储使用率环形图（ICE 冰蓝填充）。"""
    pct = used_pb / total_pb * 100
    fig = go.Figure(go.Pie(
        values=[used_pb, total_pb - used_pb],
        hole=0.72,
        marker=dict(colors=[ICE, "#141414"]),
        textinfo="none", direction="clockwise", sort=False, hoverinfo="skip",
    ))
    fig.add_annotation(
        text=(f"<b>{used_pb:.1f} PB</b><br>"
              f"<span style='font-size:9px;color:{DIM}'>/ {total_pb:.0f} PB  ({pct:.0f}%)</span>"),
        font=dict(color=ICE, size=13, family=_MONO),
        showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5,
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor=PANEL, showlegend=False,
    )
    return fig


def make_compute_bars(utilizations: list) -> go.Figure:
    """8× H100 横向利用率条图。超过 80% 变红。"""
    labels = [f"H100-{i+1:02d}" for i in range(len(utilizations))]
    colors = [RED if u > 80 else ICE for u in utilizations]
    fig = go.Figure(go.Bar(
        x=utilizations, y=labels, orientation="h",
        marker=dict(color=colors, opacity=0.75),
        text=[f"{u}%" for u in utilizations],
        textposition="inside",
        textfont=dict(size=8, color="#000", family=_MONO),
    ))
    fig.update_layout(
        margin=dict(l=62, r=30, t=20, b=8),
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        xaxis=dict(range=[0, 100], gridcolor=GRID,
                   tickfont=dict(size=7, color=DIM), ticksuffix="%"),
        yaxis=dict(tickfont=dict(size=8, color=DIM)),
        bargap=0.25,
    )
    return fig


def make_metric_gauge(
    title:       str,
    value:       float,
    min_val:     float,
    max_val:     float,
    threshold:   float,
    unit:        str  = "",
    high_is_bad: bool = False,
) -> go.Figure:
    """
    半圆仪表盘（HQ 冰蓝配色版）。
    high_is_bad=False（默认）→ value < threshold 时变红（Clarity、Confidence、IoU 均适用）。
    high_is_bad=True          → value > threshold 时变红。
    """
    if high_is_bad:
        color    = RED   if value > threshold else ICE
        safe_rng = [min_val, threshold]
        warn_rng = [threshold, max_val]
    else:
        color    = RED   if value < threshold else GREEN
        safe_rng = [threshold, max_val]
        warn_rng = [min_val, threshold]

    fig = go.Figure(go.Indicator(
        mode  = "gauge+number",
        value = value,
        # 不设 title：面板顶部的 hq-label 已提供标签，避免双重标题+裁切
        number= {"suffix": f" {unit}", "font": {"size": 26, "color": color},
                 "valueformat": ".3f" if max_val <= 1.0 else ".1f"},
        gauge = {
            "axis":      {"range": [min_val, max_val],
                          "tickcolor": DIM, "tickfont": {"size": 8, "color": DIM}},
            "bar":       {"color": color, "thickness": 0.22},
            "bgcolor":   PANEL,
            "borderwidth": 0,
            "steps": [
                {"range": safe_rng, "color": "#0D1F1D"},
                {"range": warn_rng, "color": "#1F0D0D"},
            ],
            "threshold": {
                "line":      {"color": AMBER, "width": 2},
                "thickness": 0.75,
                "value":     threshold,
            },
        },
    ))
    fig.update_layout(
        margin=dict(l=8, r=8, t=6, b=4),
        paper_bgcolor=PANEL, plot_bgcolor=PANEL,
        font={"family": _MONO, "size": 9, "color": TEXT},
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# HTML 组件构造器
# ═══════════════════════════════════════════════════════════════════════════

def render_odometer(value: int, font_size: str = "52px") -> html.Div:
    """
    CSS 翻转里程表：每位数字独立竖向滑动（0.48s cubic-bezier 缓动）。
    千位分隔符渲染为小号逗号。
    """
    formatted = f"{value:,}"
    children  = []
    dh = 1.2   # digit track height (em)

    for ch in formatted:
        if ch == ",":
            children.append(html.Span(",", className="odo-sep"))
        else:
            d = int(ch)
            strip = html.Div(
                className="odo-digit-inner",
                style={"transform": f"translateY(-{d * dh}em)"},
                children=[html.Div(str(i), style={"height": f"{dh}em"}) for i in range(10)],
            )
            children.append(html.Div(strip, className="odo-digit-outer"))

    return html.Div(
        children,
        className="odo-wrap",
        style={"fontSize": font_size, "color": GREEN, "fontWeight": "700"},
    )


def make_site_tiles(weather: dict = None) -> html.Div:
    """
    三个站点状态卡片（Sudbury / Pilbara / Atacama）。
    weather: dict  {name: {"temp": "−5°C", "emoji": "⛅", "phase": "Day"}}
    传入 None 时使用 SITES 中的默认静态值。
    """
    STATUS_COLOR = {"Active": GREEN, "Standby": ICE, "Calibrating": AMBER}
    cards = []
    for s in SITES:
        sc  = STATUS_COLOR.get(s["status"], DIM)
        extra_cls = "active-site" if s["status"] == "Active" else ""
        # 优先用实时天气，否则降级到静态默认值
        w     = (weather or {}).get(s["name"]) or {}
        temp  = w.get("temp",  s["temp"])
        emoji = w.get("emoji", "☀")
        phase = w.get("phase", s["phase"])

        # 本地时间（由 hq.py callback 通过 weather["local_time"] 注入）
        local_time = w.get("local_time", "--:--")
        # 温度格式：有数值时显示 "−5°C"，无时只显示 emoji
        if temp and temp != "N/A":
            weather_str = f"{emoji} {temp}"
        else:
            weather_str = emoji if emoji != "~" else "N/A"

        cards.append(html.Div(
            className=f"site-card {extra_cls}".strip(),
            style={"borderLeftColor": sc},
            children=[
                # 行 1：站点名 + 区域
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between",
                           "marginBottom": "3px"},
                    children=[
                        html.Span([
                            html.Span(className=f"pulse-dot {s['dot_class']}",
                                      style={"backgroundColor": sc}),
                            html.Span(s["name"],
                                      style={"color": sc, "fontSize": "12px",
                                             "fontWeight": "700"}),
                        ]),
                        html.Span(s["region"],
                                  style={"color": DIM, "fontSize": "9px"}),
                    ],
                ),
                # 行 2：状态 · 本地时间 · 天气
                html.Div(
                    style={"display": "flex", "gap": "6px", "fontSize": "10px",
                           "alignItems": "center", "marginBottom": "2px"},
                    children=[
                        html.Span(s["status"], style={"color": sc, "fontWeight": "700"}),
                        html.Span("·", style={"color": DIM}),
                        html.Span(local_time,  style={"color": ICE, "letterSpacing": "0.5px"}),
                        html.Span("·", style={"color": DIM}),
                        html.Span(weather_str, style={"color": TEXT}),
                    ],
                ),
                # 行 3：时段 + 任务
                html.Div(
                    style={"display": "flex", "gap": "8px", "fontSize": "9px",
                           "color": DIM},
                    children=[
                        html.Span(f"{phase}"),
                        html.Span(s["task"], style={"color": DIM}),
                    ],
                ),
            ],
        ))
    return html.Div(cards)


def make_hw_panel(
    cpu_pct:     float,
    mem_pct:     float,
    cpu_temp:    str,
    battery:     str,
    thermal:     str,
    cpu_history: list = None,
) -> html.Div:
    """本地 Edge 硬件面板（psutil 真实数据）。"""
    t_color  = RED if thermal == "ELEVATED" else GREEN
    bat_icon = "⚡" if "Charging" in battery else "🔋"

    def _bar_row(label: str, pct: float, base_color: str) -> html.Div:
        color = RED if pct > 85 else (AMBER if pct > 65 else base_color)
        return html.Div([
            html.Div(className="hw-row", children=[
                html.Span(label,        style={"color": DIM,   "fontSize": "10px"}),
                html.Span(f"{pct:.0f}%",style={"color": color, "fontSize": "10px",
                                               "fontWeight": "700"}),
            ]),
            html.Div(className="hw-bar-track", children=[
                html.Div(className="hw-bar-fill",
                         style={"width": f"{pct:.0f}%", "backgroundColor": color}),
            ]),
        ], style={"marginBottom": "8px"})

    return html.Div([
        html.Div("LOCAL  EDGE  HW", className="hq-label"),
        html.Div("Intel Mac · Sudbury-01",
                 style={"color": DIM, "fontSize": "9px", "marginBottom": "10px"}),
        _bar_row("CPU", cpu_pct, GREEN),
        _bar_row("MEM", mem_pct, ICE),
        html.Div(className="hw-row", children=[
            html.Span("CPU TEMP", style={"color": DIM, "fontSize": "10px"}),
            html.Span(cpu_temp,   style={"color": ICE, "fontSize": "10px"}),
        ]),
        html.Div(className="hw-row", children=[
            html.Span("THERMAL", style={"color": DIM,     "fontSize": "10px"}),
            html.Span(thermal,   style={"color": t_color, "fontSize": "10px",
                                        "fontWeight": "700"}),
        ]),
        html.Div(className="hw-row", children=[
            html.Span(bat_icon + " POWER", style={"color": DIM,   "fontSize": "10px"}),
            html.Span(battery,             style={"color": GREEN,  "fontSize": "10px"}),
        ]),
        # CPU 频率扰动 Sparkline（毛刺感）
        html.Div(className="cpu-spark-wrap", children=[
            html.Div("CPU PULSE", className="hq-label",
                     style={"marginBottom": "2px"}),
            _make_cpu_sparkline(cpu_history or [cpu_pct]),
        ]),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# 完整布局树
# ═══════════════════════════════════════════════════════════════════════════

def build_hq_layout() -> html.Div:
    """返回完整 HQ Command Center 布局（hq.py 中 app.layout 直接赋值）。"""
    _G = {"displayModeBar": False}   # 局部别名，减少行宽
    return html.Div(
        style={
            "backgroundColor": "#050505",
            "height": "100vh",
            "overflow": "hidden",
            "fontFamily": _MONO,
            "padding": "7px 14px",
            "color": TEXT,
            "display": "flex",
            "flexDirection": "column",
            "gap": "6px",
            "boxSizing": "border-box",
        },
        children=[

            # CRT 叠加层（固定覆盖，不干扰交互）
            html.Div(className="crt-lines"),
            html.Div(className="crt-sweep"),

            # ── 标题栏 ──────────────────────────────────────────────────
            html.Div(
                style={
                    "borderBottom": f"1.5px solid {ICE}",
                    "paddingBottom": "5px",
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "10px",
                    "flex": "0 0 auto",
                },
                children=[
                    # DataFactory 品牌徽标
                    html.Div(
                        "DF",
                        style={
                            "color": "#000", "backgroundColor": ICE,
                            "padding": "2px 7px", "borderRadius": "3px",
                            "fontSize": "13px", "fontWeight": "900",
                            "letterSpacing": "1px", "lineHeight": "1.4",
                        },
                    ),
                    html.H2(
                        "DATAFACTORY V3  —  GLOBAL COMMAND CENTER",
                        style={"color": ICE, "margin": "0", "flex": "1",
                               "fontSize": "15px", "letterSpacing": "3px"},
                    ),
                    html.Div(
                        id="hq-status-bar",
                        style={"color": DIM, "fontSize": "10px", "textAlign": "right"},
                    ),
                ],
            ),

            # ── ROW A ── 全球网络地图 + 站点状态 ─────────────────────────
            html.Div(
                style={"display": "flex", "gap": "8px",
                       "flex": "3", "minHeight": "0"},
                children=[
                    # 世界地图（deep dark panel，无 dp-bg 以免 backdrop-filter 干扰 SVG 渲染）
                    html.Div(
                        style={
                            **_PANEL,
                            "flex": "1", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                        },
                        children=[
                            html.Div("GLOBAL  NETWORK", className="hq-label"),
                            dcc.Graph(id="hq-world-map", config=_G,
                                      responsive=True,
                                      style={"flex": "1", "minHeight": "0"}),
                        ],
                    ),
                    # 三站点卡片（动态，由 callback 更新天气）
                    html.Div(
                        style={**_PANEL, "width": "230px", "flexShrink": "0",
                               "overflowY": "auto"},
                        children=[
                            html.Div("SITE  STATUS", className="hq-label"),
                            html.Div(id="hq-sites"),
                        ],
                    ),
                ],
            ),

            # ── ROW B ── 系统拓扑 | Gold Frames | 本地硬件 ──────────────
            html.Div(
                style={"display": "flex", "gap": "8px",
                       "flex": "2.2", "minHeight": "0"},
                children=[
                    # 拓扑图
                    html.Div(
                        style={
                            **_PANEL,
                            "flex": "1.8", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                        },
                        children=[
                            html.Div("SYSTEM  TOPOLOGY", className="hq-label"),
                            dcc.Graph(id="hq-topology", config=_G,
                                      responsive=True,
                                      style={"flex": "1", "minHeight": "0"}),
                        ],
                    ),
                    # Gold Frames 里程表
                    html.Div(
                        style={
                            **_PANEL, "flex": "0.85", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                            "justifyContent": "center", "alignItems": "center",
                            "textAlign": "center",
                        },
                        children=[
                            html.Div("GOLD  ASSETS", className="hq-label"),
                            html.Div(
                                className="odo-area",
                                style={"width": "100%", "textAlign": "center"},
                                children=[
                                    html.Div(id="hq-odometer",
                                             style={"margin": "4px 0 3px"}),
                                    html.Div("cumulative archive frames",
                                             style={"color": DIM, "fontSize": "8px",
                                                    "letterSpacing": "1px"}),
                                    html.Div(className="hex-stream-outer", children=[
                                        html.Span(_HEX_STREAM_CONTENT,
                                                  className="hex-stream"),
                                    ]),
                                ],
                            ),
                        ],
                    ),
                    # 本地硬件面板（psutil 真实数据）
                    html.Div(
                        id="hq-hw-panel",
                        style={**_PANEL, "flex": "0.85", "minWidth": "0",
                               "overflowY": "auto"},
                    ),
                ],
            ),

            # ── ROW C ── HQ Cloud 存储 | 8×H100 | 日合格率 ───────────────
            html.Div(
                style={"display": "flex", "gap": "8px",
                       "flex": "1.9", "minHeight": "0"},
                children=[
                    html.Div(
                        style={
                            **_PANEL, "flex": "1", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                        },
                        children=[
                            html.Div("HQ  STORAGE", className="hq-label"),
                            dcc.Graph(id="hq-storage", config=_G,
                                      responsive=True,
                                      style={"flex": "1", "minHeight": "0"}),
                        ],
                    ),
                    html.Div(
                        style={
                            **_PANEL, "flex": "1.6", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                        },
                        children=[
                            html.Div("HQ  COMPUTE  —  8×  NVIDIA  H100", className="hq-label"),
                            dcc.Graph(id="hq-compute", config=_G,
                                      responsive=True,
                                      style={"flex": "1", "minHeight": "0"}),
                        ],
                    ),
                    html.Div(
                        style={
                            **_PANEL, "flex": "0.65", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                            "justifyContent": "center", "alignItems": "center",
                        },
                        children=[
                            html.Div("DAILY  YIELD", className="hq-label"),
                            html.Div(id="hq-daily-yield",
                                     style={"fontSize": "44px", "fontWeight": "700",
                                            "color": GREEN, "lineHeight": "1"}),
                            html.Div("data qualified rate",
                                     style={"color": DIM, "fontSize": "8px",
                                            "marginTop": "4px"}),
                        ],
                    ),
                ],
            ),

            # ── ROW D ── 核心指标仪表 (Confidence | Clarity | IoU) ────────
            html.Div(
                style={"display": "flex", "gap": "8px",
                       "flex": "1.7", "minHeight": "0"},
                children=[
                    html.Div(
                        id="hq-gauge-conf",
                        className="dp-fg",
                        style={
                            **_PANEL, "flex": "1", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                        },
                        children=[
                            html.Div("CONFIDENCE", className="hq-label"),
                            dcc.Graph(id="hq-gauge-conf-plot", config=_G,
                                      responsive=True,
                                      style={"flex": "1", "minHeight": "0"}),
                        ],
                    ),
                    html.Div(
                        id="hq-gauge-clarity",
                        className="dp-fg",
                        style={
                            **_PANEL, "flex": "1", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                        },
                        children=[
                            html.Div("CLARITY  (Image Quality)", className="hq-label"),
                            dcc.Graph(id="hq-gauge-clarity-plot", config=_G,
                                      responsive=True,
                                      style={"flex": "1", "minHeight": "0"}),
                        ],
                    ),
                    html.Div(
                        id="hq-gauge-iou",
                        className="dp-fg",
                        style={
                            **_PANEL, "flex": "1", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                        },
                        children=[
                            html.Div("IoU  SNAPSHOT  (labeled_return)", className="hq-label"),
                            dcc.Graph(id="hq-gauge-iou-plot", config=_G,
                                      responsive=True,
                                      style={"flex": "1", "minHeight": "0"}),
                        ],
                    ),
                ],
            ),

            # ── 定时器 + 客户端状态存储 ──────────────────────────────────
            dcc.Interval(id="hq-tick", interval=1000, n_intervals=0),
            dcc.Store(
                id="hq-store",
                data={"packet_pos": 0.0, "gold": 1_248_500},
            ),
        ],
    )
