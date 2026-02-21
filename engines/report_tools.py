# engines/report_tools.py — 报告生成：JSON 清单、HTML 报告、图表，只干活不决策
import os
import json
import io
import base64
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, List, Optional

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def generate_json_manifest(data_list: List[Any], target_path: str, filename: str = "manifest.json") -> str:
    """将列表写入 target_path/filename，返回写入文件路径。"""
    os.makedirs(target_path, exist_ok=True)
    out = os.path.join(target_path, filename)
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps(data_list, indent=4, ensure_ascii=False))
    return out


def _plot_base64(brs: List[float], bls: List[float], save_path: Optional[str] = None) -> str:
    """生成亮度/模糊分布图，返回 base64 内嵌 HTML 的 img 标签。若 save_path 指定则同时保存 PNG 副本。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.hist(brs, bins=20, color="skyblue", edgecolor="white")
    ax1.set_title("Brightness Dist")
    ax1.set_xlabel("Value")
    ax1.set_ylabel("Count")
    ax2.hist(bls, bins=20, color="salmon", edgecolor="white")
    ax2.set_title("Blur Dist")
    ax2.set_xlabel("Value")
    plt.tight_layout()
    if save_path:
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        plt.savefig(save_path, format="png", dpi=100)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f'<img src="data:image/png;base64,{b64}" style="width:100%;">'


def generate_html_report(
    data_list: List[Any],
    target_path: str,
    batch_id: str,
    mode: str,
    pass_rate_gate: float = 80.0,
    copy_to_dir: Optional[str] = None,
) -> str:
    """生成 quality_report.html，返回文件路径。若 copy_to_dir 指定则同步写入该目录（HTML+图表副本）供持久化。"""
    os.makedirs(target_path, exist_ok=True)
    df = pd.DataFrame(data_list) if data_list else pd.DataFrame()
    total = len(df)
    normal_count = len(df[df["env"] == "Normal"]) if total and "env" in df.columns else 0
    pass_rate = (normal_count / total * 100) if total > 0 else 0.0
    if total > 0 and "source" in df.columns and "br" in df.columns:
        video_report = df.groupby("source")["br"].agg("mean")
        stats_table_html = video_report.to_frame(name="Avg Brightness").to_html(
            classes="table", float_format=lambda x: f"{x:.2f}"
        )
        brs = df["br"].tolist()
        bls = df["bl"].tolist()
        bad_cases = df[df["env"] != "Normal"].to_dict("records") if "env" in df.columns else []
    else:
        stats_table_html = "<p>无有效采样数据（可能为损坏或 0 字节视频）。</p>"
        brs, bls = [], []
        bad_cases = []
    rows_html = "".join([
        f"<tr><td>{c.get('source', 'Unknown')}</td><td>{c.get('frame_id', 0)}</td>"
        f"<td>{c.get('br', 0):.1f}</td><td>{c.get('bl', 0):.1f}</td><td>{c.get('jitter', 0):.1f}</td>"
        f'<td class="status-bad">{c.get("env", "Unknown")}</td><td><code>{c.get("filename", "N/A")}</code></td></tr>'
        for c in bad_cases
    ])
    chart_save_path = os.path.join(copy_to_dir, f"{batch_id}_chart.png") if copy_to_dir else None
    if brs or bls:
        plot_html = _plot_base64(brs, bls, save_path=chart_save_path)
    else:
        plot_html = "<p>无亮度/模糊数据，跳过图表。</p>"
    ts = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
    html_content = f"""
<html>
<head><meta charset="UTF-8"><title>Datafactory Quality Report</title>
<style>
body {{ font-family: sans-serif; margin: 40px; background: #f4f7f6; color: #333; }}
.card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }}
.kpi-box {{ display: flex; gap: 20px; }}
.kpi {{ flex: 1; text-align: center; padding: 20px; border-radius: 8px; color: white; }}
.pass {{ background: #2ecc71; }} .fail {{ background: #e74c3c; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #34495e; color: white; }}
.status-bad {{ color: #e74c3c; font-weight: bold; }}
</style>
</head>
<body>
<h1>Datafactory Production Report ({mode})</h1>
<p>Batch ID: {batch_id} | Generated at: {ts} (Toronto)</p>
<div class="kpi-box">
  <div class="kpi {'pass' if pass_rate >= pass_rate_gate else 'fail'}">
    <h3>Pass Rate (Gate: {pass_rate_gate}%)</h3>
    <h2 style="font-size: 40px;">{pass_rate:.2f}%</h2>
  </div>
  <div class="kpi" style="background: #3498db;">
    <h3>Total Samples</h3>
    <h2 style="font-size: 40px;">{total}</h2>
  </div>
</div>
<div class="card"><h3>Per-Video Quality Overview (Average Brightness)</h3>{stats_table_html}</div>
<div class="card"><h3>Quality Distribution Chart</h3>{plot_html}</div>
<div class="card"><h3>Bad Case Traceability ({len(bad_cases)} items)</h3>
<table><thead><tr><th>Source Video</th><th>Frame ID</th><th>Brightness</th><th>Blur</th><th>Jitter</th><th>Judgment</th><th>Filename</th></tr></thead>
<tbody>{rows_html}</tbody></table></div>
</body>
</html>
"""
    out = os.path.join(target_path, "quality_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_content)
    if copy_to_dir:
        os.makedirs(copy_to_dir, exist_ok=True)
        archive_html = os.path.join(copy_to_dir, f"{batch_id}_quality_report.html")
        shutil.copy2(out, archive_html)
    return out
