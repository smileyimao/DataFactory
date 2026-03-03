# dashboard/layout.py — DashboardModule：布局树 + Plotly 图表构造器
"""
所有颜色常量、Plotly 图表工厂函数和 Dash 布局树定义。
sentinel.py 只调用 build_layout() 和各图表函数，不直接操作 HTML。
"""
from dash import dcc, html
import plotly.graph_objects as go

# ── 调色板 ───────────────────────────────────────────────────────────────
BG       = "#1A1A1A"   # 主背景
PANEL    = "#111111"   # 面板背景
GREEN    = "#39FF14"   # 荧光绿（正常 / 活跃）
AMBER    = "#FFB300"   # 琥珀（警告 / CL 线）
RED      = "#FF3B3B"   # 红（报警 / UCL-LCL）
GRID     = "#2A2A2A"   # 网格线
TEXT     = "#C8C8C8"   # 主文字
DIM      = "#555555"   # 次文字 / 标签
FILL_G   = "rgba(57,255,20,0.07)"   # 绿色填充（趋势图）

_MONO = "monospace"
_GRAPH_CFG = {"displayModeBar": False}

_PANEL_STYLE = {
    "backgroundColor": "rgba(17, 17, 17, 0.90)",
    "border": "1px solid rgba(255, 255, 255, 0.05)",
    "borderRadius": "4px",
    "padding": "10px",
    "backdropFilter": "blur(5px)",
    "WebkitBackdropFilter": "blur(5px)",
    "boxShadow": "0 4px 18px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.02)",
}

_SECTION_LABEL = {
    "color": DIM,
    "fontSize": "9px",
    "letterSpacing": "2px",
    "marginBottom": "6px",
    "fontFamily": _MONO,
}


# ── 图表工厂 ─────────────────────────────────────────────────────────────

def make_gauge(
    title:       str,
    value:       float,
    min_val:     float,
    max_val:     float,
    threshold:   float,
    unit:        str  = "",
    high_is_bad: bool = True,
) -> go.Figure:
    """
    半圆仪表盘。
    high_is_bad=True  → value > threshold 时变红（Jitter、Brightness_max）
    high_is_bad=False → value < threshold 时变红（Blur）
    """
    if high_is_bad:
        color    = RED   if value > threshold else GREEN
        safe_rng = [min_val, threshold]
        warn_rng = [threshold, max_val]
    else:
        color    = RED   if value < threshold else GREEN
        safe_rng = [threshold, max_val]
        warn_rng = [min_val, threshold]

    fig = go.Figure(go.Indicator(
        mode  = "gauge+number",
        value = value,
        title = {"text": f"<b>{title}</b>", "font": {"size": 11, "color": TEXT}},
        number= {"suffix": f" {unit}",       "font": {"size": 20, "color": color}},
        gauge = {
            "axis":      {"range": [min_val, max_val],
                          "tickcolor": DIM, "tickfont": {"size": 8, "color": DIM}},
            "bar":       {"color": color, "thickness": 0.22},
            "bgcolor":   PANEL,
            "borderwidth": 0,
            "steps": [
                {"range": safe_rng, "color": "#172317"},
                {"range": warn_rng, "color": "#231717"},
            ],
            "threshold": {
                "line":      {"color": AMBER, "width": 2},
                "thickness": 0.75,
                "value":     threshold,
            },
        },
    ))
    fig.update_layout(
        height          = 125,
        margin          = dict(l=8, r=8, t=22, b=0),
        paper_bgcolor   = PANEL,
        plot_bgcolor    = PANEL,
        font            = {"family": _MONO, "size": 9, "color": TEXT},
    )
    return fig


def make_mini_trend(
    values: list,
    title:  str,
    color:  str = GREEN,
) -> go.Figure:
    """60 帧小趋势折线（填充）。"""
    fig = go.Figure(go.Scatter(
        y          = values,
        mode       = "lines",
        line       = dict(color=color, width=1.4),
        fill       = "tozeroy",
        fillcolor  = FILL_G if color == GREEN else "rgba(255,59,59,0.07)",
    ))
    fig.update_layout(
        height        = 62,
        margin        = dict(l=4, r=4, t=16, b=2),
        paper_bgcolor = PANEL,
        plot_bgcolor  = PANEL,
        font          = {"family": _MONO, "size": 9, "color": DIM},
        title         = dict(text=title, font=dict(size=8, color=DIM), x=0.5),
        xaxis         = dict(visible=False),
        yaxis         = dict(gridcolor=GRID, tickfont=dict(size=7),
                             tickcolor=DIM, showgrid=True),
        showlegend    = False,
    )
    return fig


def make_spc_chart(
    values:   list,
    frame_ids:list,
    cl:       float,
    ucl:      float,
    lcl:      float,
) -> go.Figure:
    """
    置信度 SPC 趋势图。
    含 CL（均值/先验）、UCL/LCL（±3σ）控制线，越界点用红叉标出。
    """
    fig = go.Figure()

    # 主曲线
    fig.add_trace(go.Scatter(
        x          = frame_ids,
        y          = values,
        mode       = "lines",
        name       = "Confidence",
        line       = dict(color=GREEN, width=1.6),
        fill       = "tozeroy",
        fillcolor  = FILL_G,
    ))

    # 越界帧（OOC 点）
    ooc_x = [fid for fid, v in zip(frame_ids, values) if v < lcl or v > ucl]
    ooc_y = [v   for v        in values               if v < lcl or v > ucl]
    if ooc_x:
        fig.add_trace(go.Scatter(
            x          = ooc_x,
            y          = ooc_y,
            mode       = "markers",
            name       = "OOC",
            marker     = dict(color=RED, size=7, symbol="x-thin-open", line=dict(width=2)),
            showlegend = False,
        ))

    # 控制线（Shape + Annotation）
    if frame_ids:
        x0, x1 = frame_ids[0], frame_ids[-1]
        for val, label, clr, dash in [
            (cl,  "CL",  AMBER, "dash"),
            (ucl, "UCL", RED,   "dot"),
            (lcl, "LCL", RED,   "dot"),
        ]:
            fig.add_shape(
                type  = "line",
                x0=x0, x1=x1, y0=val, y1=val,
                line  = dict(color=clr, width=1.2, dash=dash),
            )
            fig.add_annotation(
                x         = x1,
                y         = val,
                text      = f"  {label} {val:.3f}",
                showarrow = False,
                font      = dict(color=clr, size=9, family=_MONO),
                xanchor   = "left",
            )

    fig.update_layout(
        height        = 145,
        margin        = dict(l=8, r=60, t=8, b=24),
        paper_bgcolor = PANEL,
        plot_bgcolor  = PANEL,
        font          = {"family": _MONO, "size": 9, "color": TEXT},
        xaxis         = dict(
            gridcolor = GRID,
            title     = dict(text="Frame ID",   font=dict(size=8)),
            tickfont  = dict(size=8),
        ),
        yaxis         = dict(
            gridcolor = GRID, range = [-0.02, 1.05],
            title     = dict(text="Confidence", font=dict(size=8)),
            tickfont  = dict(size=8),
        ),
        legend        = dict(font=dict(size=8), bgcolor="rgba(0,0,0,0)"),
        showlegend    = True,
    )
    return fig


# ── Dash 布局树 ──────────────────────────────────────────────────────────

def build_layout() -> html.Div:
    """返回完整 Dash 布局（sentinel.py 中 app.layout 直接赋值此函数返回值）。"""
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

            # ── 标题栏 ───────────────────────────────────────────────────
            html.Div(
                style={
                    "borderBottom": f"1.5px solid {GREEN}",
                    "paddingBottom": "5px",
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "10px",
                    "flex": "0 0 auto",
                },
                children=[
                    html.Div(
                        "DF",
                        style={
                            "color": "#000", "backgroundColor": GREEN,
                            "padding": "2px 7px", "borderRadius": "3px",
                            "fontSize": "13px", "fontWeight": "900",
                            "letterSpacing": "1px", "lineHeight": "1.4",
                        },
                    ),
                    html.H2(
                        "SENTINEL-1  :  DATAFACTORY V3  TELEMETRY",
                        style={
                            "color": GREEN, "margin": "0", "flex": "1",
                            "letterSpacing": "3px", "fontSize": "15px",
                        },
                    ),
                    html.Div(
                        id    = "status-bar",
                        style = {"color": DIM, "fontSize": "10px",
                                 "textAlign": "right"},
                    ),
                ],
            ),

            # ── 主内容行 ─────────────────────────────────────────────────
            html.Div(
                style={
                    "display": "flex", "gap": "8px",
                    "flex": "4", "minHeight": "0",
                },
                children=[

                    # ── 左：物理 QC ──────────────────────────────────────
                    html.Div(
                        style={**_PANEL_STYLE, "width": "210px", "flexShrink": "0",
                               "overflowY": "auto"},
                        children=[
                            html.Div("STANDARD  QC", style=_SECTION_LABEL),
                            dcc.Graph(id="gauge-jitter",     config=_GRAPH_CFG,
                                      style={"height": "130px"}),
                            dcc.Graph(id="trend-jitter",     config=_GRAPH_CFG,
                                      style={"height": "58px"}),
                            dcc.Graph(id="gauge-blur",       config=_GRAPH_CFG,
                                      style={"height": "130px"}),
                            dcc.Graph(id="trend-blur",       config=_GRAPH_CFG,
                                      style={"height": "58px"}),
                            dcc.Graph(id="gauge-brightness", config=_GRAPH_CFG,
                                      style={"height": "130px"}),
                            dcc.Graph(id="trend-brightness", config=_GRAPH_CFG,
                                      style={"height": "58px"}),
                        ],
                    ),

                    # ── 中：视频主视窗 ───────────────────────────────────
                    html.Div(
                        style={
                            **_PANEL_STYLE,
                            "flex": "1", "minWidth": "0",
                            "display": "flex", "flexDirection": "column",
                        },
                        children=[
                            html.Div("LIVE  FEED", style=_SECTION_LABEL),
                            html.Img(
                                id    = "live-feed",
                                style = {
                                    "width": "100%",
                                    "flex": "1",
                                    "objectFit": "contain",
                                    "borderRadius": "2px",
                                    "border": f"1px solid {GRID}",
                                    "display": "block",
                                    "minHeight": "0",
                                },
                            ),
                        ],
                    ),

                    # ── 右：模型审计 ─────────────────────────────────────
                    html.Div(
                        style={**_PANEL_STYLE, "width": "195px", "flexShrink": "0",
                               "overflowY": "auto"},
                        children=[
                            html.Div("MODEL  AUDIT", style=_SECTION_LABEL),

                            html.Div("CONFIDENCE",
                                     style={**_SECTION_LABEL, "marginBottom": "2px"}),
                            html.Div(id="conf-value",
                                     style={"fontSize": "42px", "fontWeight": "bold",
                                            "color": GREEN, "lineHeight": "1",
                                            "fontFamily": _MONO}),
                            html.Div(id="conf-bar",
                                     style={"marginTop": "6px", "marginBottom": "14px"}),

                            html.Div("IoU  SNAPSHOT",
                                     style={**_SECTION_LABEL, "marginBottom": "2px"}),
                            html.Div("(labeled_return)",
                                     style={"color": DIM, "fontSize": "8px",
                                            "marginBottom": "4px"}),
                            html.Div(id="iou-value",
                                     style={"fontSize": "30px", "fontWeight": "bold",
                                            "color": AMBER, "lineHeight": "1",
                                            "fontFamily": _MONO}),
                            html.Div(id="iou-timestamp",
                                     style={"color": DIM, "fontSize": "9px",
                                            "marginBottom": "16px", "marginTop": "4px"}),

                            html.Div("SESSION  ALERTS",
                                     style={**_SECTION_LABEL, "marginBottom": "6px"}),
                            html.Div(id="alert-counts"),
                        ],
                    ),
                ],
            ),

            # ── 底部 SPC ─────────────────────────────────────────────────
            html.Div(
                style={
                    **_PANEL_STYLE,
                    "flex": "1.4", "minHeight": "0",
                    "display": "flex", "flexDirection": "column",
                },
                children=[
                    html.Div("CONFIDENCE  TREND  —  SPC  (CL / UCL / LCL)",
                             style=_SECTION_LABEL),
                    dcc.Graph(id="spc-chart", config=_GRAPH_CFG,
                              responsive=True,
                              style={"flex": "1", "minHeight": "0"}),
                ],
            ),

            # ── 定时器（不可见）─────────────────────────────────────────
            dcc.Interval(id="tick", interval=500, n_intervals=0),
        ],
    )
