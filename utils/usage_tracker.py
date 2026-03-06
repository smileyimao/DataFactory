# utils/usage_tracker.py — 轻量级功能使用追踪（v3.9）
# 记录每个功能的调用次数和时间，供审计和裁剪决策使用。
# track() 失败绝对静默，不影响主流程。
import json
import os
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# 存储路径：utils/ 的上两级为项目根，logs/ 在项目根下
_LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_USAGE_FILE = os.path.join(_LOGS_DIR, "feature_usage.json")


# ─────────────────────────── 私有 I/O ──────────────────────────────────────

def _load() -> dict:
    """读取使用记录文件，不存在则返回空 dict。"""
    if not os.path.isfile(_USAGE_FILE):
        return {}
    try:
        with open(_USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    """原子写入使用记录，自动创建 logs/ 目录。"""
    os.makedirs(_LOGS_DIR, exist_ok=True)
    tmp = _USAGE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _USAGE_FILE)


# ─────────────────────────── 公开 API ──────────────────────────────────────

def track(feature_name: str) -> None:
    """
    记录一次功能调用。
    失败时静默跳过，绝不抛出异常。单次耗时目标 < 5ms。
    """
    try:
        now = datetime.now()
        today = now.date().isoformat()
        now_iso = now.isoformat(timespec="seconds")

        data = _load()
        entry = data.get(feature_name, {})
        entry["count"] = entry.get("count", 0) + 1
        if not entry.get("first_used"):
            entry["first_used"] = now_iso
        entry["last_used"] = now_iso
        daily = entry.get("daily", {})
        daily[today] = daily.get(today, 0) + 1
        entry["daily"] = daily
        data[feature_name] = entry
        _save(data)
    except Exception as e:
        logger.warning("usage_tracker.track(%s) 失败（已跳过）: %s", feature_name, e)


def report(days: int = 30) -> None:
    """生成过去 N 天的使用报告并打印。"""
    data = _load()
    today = date.today()
    cutoff = today - timedelta(days=days)

    # 计算每个功能在统计周期内的调用次数
    rows = []
    for name, entry in sorted(data.items()):
        daily = entry.get("daily", {})
        period_count = sum(
            v for k, v in daily.items()
            if k >= cutoff.isoformat()
        )
        last_used_str = _fmt_last_used(entry.get("last_used"), today)
        if period_count > 10:
            suggestion = "✅ 正常"
        elif period_count >= 1:
            suggestion = "⚠️  使用偏少"
        else:
            suggestion = "❌ 建议删除"
        rows.append((name, period_count, last_used_str, suggestion))

    # 没有任何记录时显示空表
    print(f"\n📊 Feature Usage Report")
    print(f"生成时间: {today.isoformat()}")
    print(f"统计周期: 最近{days}天\n")

    col_w = max((len(r[0]) for r in rows), default=20)
    col_w = max(col_w, 20)
    header = f"{'功能':<{col_w}}  {'调用次数':>8}    {'最后使用':<12}    建议"
    print(header)
    print("─" * (len(header) + 8))
    for name, cnt, last, sugg in rows:
        cnt_str = f"{cnt:,}"
        print(f"{name:<{col_w}}  {cnt_str:>8}    {last:<12}    {sugg}")

    delete_list = [r[0] for r in rows if r[3].startswith("❌")]
    watch_list  = [r[0] for r in rows if r[3].startswith("⚠️")]
    print()
    print(f"建议删除：{delete_list if delete_list else '无'}")
    print(f"建议观察：{watch_list  if watch_list  else '无'}")


def reset(feature_name: Optional[str] = None) -> None:
    """
    重置使用计数。
    - feature_name 传入字符串 → 只重置该功能
    - 不传（None）           → 重置全部
    """
    data = _load()
    if feature_name:
        if feature_name in data:
            del data[feature_name]
            print(f"✅ 已重置功能计数: {feature_name}")
        else:
            print(f"⚠️  未找到功能记录: {feature_name}")
    else:
        count = len(data)
        data = {}
        print(f"✅ 已重置全部功能计数（共 {count} 项）")
    try:
        _save(data)
    except Exception as e:
        logger.warning("usage_tracker.reset 写入失败: %s", e)


# ─────────────────────────── 工具函数 ──────────────────────────────────────

def _fmt_last_used(last_iso: Optional[str], today: date) -> str:
    """将 ISO 时间戳格式化为可读的相对日期。"""
    if not last_iso:
        return "从未使用"
    try:
        last_date = datetime.fromisoformat(last_iso).date()
        delta = (today - last_date).days
        if delta == 0:
            return "今天"
        if delta == 1:
            return "昨天"
        if delta < 7:
            return f"{delta}天前"
        return last_date.isoformat()
    except Exception:
        return "从未使用"
