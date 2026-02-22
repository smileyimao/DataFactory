# engines/report_tools.py — 报告生成：JSON 清单、HTML 报告、图表、批次工业报表，只干活不决策
import os
import json
import io
import base64
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

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


def generate_batch_industrial_report(
    qc_archive: List[Dict[str, Any]],
    qualified: List[Dict[str, Any]],
    blocked: List[Dict[str, Any]],
    auto_reject: List[Tuple[Dict[str, Any], str]],
    batch_id: str,
    qc_dir: str,
    gate: float,
    dual_high: Optional[float] = None,
    dual_low: Optional[float] = None,
    version_info: Optional[Dict[str, str]] = None,
) -> str:
    """
    生成一批物料的工业报表 HTML（单独一张，便于邮件/MLflow 一目了然）。
    含：批次概览、合格/待复核/自动拦截/重复 四栏 KPI、逐条物料明细表。
    返回写入路径。
    """
    os.makedirs(qc_dir, exist_ok=True)
    ts = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
    total = len(qc_archive)
    n_qualified = len(qualified)
    n_blocked = len(blocked)
    n_auto_reject = len(auto_reject)
    qualified_set = {id(x) for x in qualified}
    auto_reject_set = {id(x[0]) for x in auto_reject}
    pct = lambda a, b: (a / b * 100) if b else 0.0

    rows = []
    for item in qc_archive:
        name = item["filename"]
        score = item.get("score", 0)
        is_dup = item.get("is_duplicate", False)
        if is_dup:
            conclusion = "重复"
            conclusion_css = "dup"
        elif id(item) in qualified_set:
            conclusion = "合格"
            conclusion_css = "ok"
        elif id(item) in auto_reject_set:
            conclusion = "自动拦截"
            conclusion_css = "rej"
        else:
            conclusion = "待复核"
            conclusion_css = "block"
        dup_str = "是" if is_dup else "否"
        rows.append(
            f'<tr><td>{name}</td><td>{score:.1f}%</td><td>{dup_str}</td>'
            f'<td class="conclusion-{conclusion_css}">{conclusion}</td></tr>'
        )
    rows_html = "\n".join(rows)

    gate_line = ""
    if dual_high is not None and dual_low is not None:
        gate_line = f"<p>双门槛：高≥{dual_high}% 放行，低<{dual_low}% 拦截，中间待复核。</p>"
    else:
        gate_line = f"<p>准入线：{gate}%</p>"

    version_line = ""
    if version_info:
        version_line = (
            f"<p>算法版本: {version_info.get('algorithm_version', '-')} | "
            f"视觉模型: {version_info.get('vision_model_version', '-')}</p>"
        )

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>批次工业报表 - {batch_id}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 24px; background: #f0f2f5; color: #1a1a1a; }}
h1 {{ margin: 0 0 8px 0; font-size: 1.5rem; color: #1a1a1a; }}
.report-meta {{ color: #666; font-size: 0.9rem; margin-bottom: 20px; }}
.kpi-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }}
.kpi {{ flex: 1; min-width: 120px; padding: 16px; border-radius: 10px; color: #fff; text-align: center; }}
.kpi h3 {{ margin: 0 0 4px 0; font-size: 0.85rem; opacity: 0.95; }}
.kpi .num {{ font-size: 1.75rem; font-weight: 700; }}
.kpi .pct {{ font-size: 0.8rem; opacity: 0.9; }}
.kpi-ok {{ background: linear-gradient(135deg, #2ecc71, #27ae60); }}
.kpi-block {{ background: linear-gradient(135deg, #f39c12, #e67e22); }}
.kpi-rej {{ background: linear-gradient(135deg, #e74c3c, #c0392b); }}
.kpi-dup {{ background: linear-gradient(135deg, #95a5a6, #7f8c8d); }}
.card {{ background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 20px; margin-bottom: 20px; }}
.card h2 {{ margin: 0 0 12px 0; font-size: 1.1rem; color: #333; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }}
th {{ background: #34495e; color: #fff; font-weight: 600; }}
.conclusion-ok {{ color: #27ae60; font-weight: 600; }}
.conclusion-block {{ color: #e67e22; font-weight: 600; }}
.conclusion-rej {{ color: #c0392b; font-weight: 600; }}
.conclusion-dup {{ color: #7f8c8d; font-weight: 600; }}
.footer {{ margin-top: 24px; color: #888; font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="card">
<h1>批次工业报表</h1>
<p class="report-meta">Batch ID: <strong>{batch_id}</strong> | 生成时间: {ts} (Toronto)</p>
{gate_line}
{version_line}
</div>
<div class="kpi-row">
  <div class="kpi kpi-ok"><h3>合格</h3><div class="num">{n_qualified}</div><div class="pct">{pct(n_qualified, total):.1f}%</div></div>
  <div class="kpi kpi-block"><h3>待复核</h3><div class="num">{n_blocked}</div><div class="pct">{pct(n_blocked, total):.1f}%</div></div>
  <div class="kpi kpi-rej"><h3>自动拦截</h3><div class="num">{n_auto_reject}</div><div class="pct">{pct(n_auto_reject, total):.1f}%</div></div>
  <div class="kpi kpi-dup"><h3>重复</h3><div class="num">{sum(1 for x in qc_archive if x.get("is_duplicate"))}</div><div class="pct">{pct(sum(1 for x in qc_archive if x.get("is_duplicate")), total):.1f}%</div></div>
</div>
<div class="card">
<h2>物料明细（共 {total} 条）</h2>
<table>
<thead><tr><th>文件名</th><th>得分</th><th>是否重复</th><th>结论</th></tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>
<p class="footer">Datafactory 批次工业报表 · 本邮件由系统自动生成</p>
</body>
</html>
"""
    out = os.path.join(qc_dir, "batch_industrial_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_content)
    return out


def generate_vision_report(
    per_video: List[Dict[str, Any]],
    batch_id: str,
    qc_dir: str,
    version_info: Optional[Dict[str, str]] = None,
    vision_skipped: bool = False,
) -> str:
    """
    生成智能检测结果 HTML（含缩略图 base64 内嵌），与 MLflow 同批数据一致，可一并作 artifact。
    vision_skipped=True 表示本批未执行推理（模型未加载或未启用），报告会标注“未执行”；否则 0 检测框会标注“已执行但未检出”。
    返回写入路径。
    """
    os.makedirs(qc_dir, exist_ok=True)
    ts = datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M:%S")
    version_line = ""
    if version_info:
        version_line = f"<p>视觉模型: {version_info.get('vision_model_version', '-')}</p>"
    total_det = sum(p.get("n_detections") or 0 for p in per_video)
    ran_with_frames = any((p.get("n_frames") or 0) > 0 for p in per_video)
    if vision_skipped:
        status_note = '<p class="status-note status-skipped">本批<strong>未执行</strong>智能检测：视觉模型未加载或未启用。</p>'
    elif total_det == 0 and ran_with_frames:
        status_note = '<p class="status-note status-zero">本批<strong>已执行</strong>智能检测，未检出目标（可能画面无 COCO 类别或置信度不足）。</p>'
    else:
        status_note = ""
    rows = []
    for p in per_video:
        name = p.get("name", "")
        n_frames = p.get("n_frames", 0)
        n_det = p.get("n_detections", 0)
        err = p.get("error", "")
        if err:
            rows.append(f"<tr><td>{name}</td><td>{n_frames}</td><td>-</td><td class=\"err\">{err}</td></tr>")
        else:
            rows.append(f"<tr><td>{name}</td><td>{n_frames}</td><td>{n_det}</td><td>-</td></tr>")
    table_rows = "\n".join(rows)
    cards = []
    for p in per_video:
        name = p.get("name", "")
        n_det = p.get("n_detections", 0)
        thumbs = p.get("thumbnails") or []
        imgs = "".join(
            f'<img src="data:image/jpeg;base64,{b64}" alt="检测帧" class="thumb"/>'
            for b64 in thumbs[:6]
        )
        cards.append(
            f'<div class="card"><h3>{name}</h3>'
            f'<p>检测框数: {n_det}</p><div class="thumbs">{imgs}</div></div>'
        )
    cards_html = "\n".join(cards)
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>智能检测结果 - {batch_id}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 24px; background: #f0f2f5; color: #1a1a1a; }}
h1 {{ margin: 0 0 8px 0; font-size: 1.5rem; }}
.report-meta {{ color: #666; font-size: 0.9rem; margin-bottom: 16px; }}
.card {{ background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 16px; margin-bottom: 16px; }}
.card h3 {{ margin: 0 0 8px 0; font-size: 1rem; }}
.thumbs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
.thumb {{ max-width: 320px; max-height: 200px; object-fit: contain; border: 1px solid #ddd; border-radius: 6px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }}
th {{ background: #34495e; color: #fff; }}
.err {{ color: #c0392b; }}
.status-note {{ margin-top: 12px; padding: 10px 12px; border-radius: 6px; font-size: 0.9rem; }}
.status-skipped {{ background: #fef3e2; color: #b45f06; border: 1px solid #f0c674; }}
.status-zero {{ background: #e8f4fd; color: #1a5276; border: 1px solid #aed6f1; }}
.footer {{ margin-top: 24px; color: #888; font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="card">
<h1>智能检测结果</h1>
<p class="report-meta">Batch ID: <strong>{batch_id}</strong> | 生成时间: {ts} (Toronto)</p>
{version_line}
<p>本批总检测框数: <strong>{total_det}</strong></p>
{status_note}
</div>
<div class="card">
<h2>汇总</h2>
<table>
<thead><tr><th>视频/文件</th><th>抽帧数</th><th>检测框数</th><th>备注</th></tr></thead>
<tbody>
{table_rows}
</tbody>
</table>
</div>
{cards_html}
<p class="footer">Datafactory 智能检测报告 · 与 MLflow 同批数据</p>
</body>
</html>
"""
    out = os.path.join(qc_dir, "vision_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_content)
    return out
