# utils/site_info.py — 站点实时时钟 + 天气
"""
提供两个公共函数：

  get_site_times()   → {"sudbury": "07:32", "pilbara": "20:32", ...}
  get_site_weather() → {"sudbury": {"temp": -5, "desc": "Snow", "icon": "❄"}, ...}

天气数据 10 分钟缓存，API Key 从环境变量 OPENWEATHER_API_KEY 读取。
未设置 Key 时返回占位数据，不影响 dashboard 启动。

依赖：pytz, requests（已列入 requirements.txt）
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# ── 配置路径 ──────────────────────────────────────────────────────────────
_CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")

# 站点默认值（settings.yaml 解析失败时使用）
_SITE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "sudbury": {"timezone": "America/Toronto",  "lat": 46.4917,  "lon": -81.0000},
    "pilbara": {"timezone": "Australia/Perth",  "lat": -23.3517, "lon": 119.7200},
    "atacama": {"timezone": "America/Santiago", "lat": -24.5000, "lon": -69.2500},
}

# OpenWeatherMap 主要天气描述 → emoji 映射
_OWM_EMOJI: Dict[str, str] = {
    "Clear":         "☀",
    "Clouds":        "☁",
    "Rain":          "🌧",
    "Drizzle":       "🌦",
    "Snow":          "❄",
    "Thunderstorm":  "⛈",
    "Mist":          "🌫",
    "Fog":           "🌫",
    "Haze":          "🌫",
    "Dust":          "💨",
    "Sand":          "💨",
    "Ash":           "🌋",
    "Squall":        "💨",
    "Tornado":       "🌪",
}


# ── 内部辅助 ──────────────────────────────────────────────────────────────

def _load_sites() -> Dict[str, Dict[str, Any]]:
    """从 settings.yaml 读取 sites 节，失败时使用内置默认值。"""
    try:
        with open(_CFG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        sites = cfg.get("sites", {})
        if sites:
            return sites
    except Exception as e:
        logger.debug("site_info: 读取 settings.yaml 失败，使用默认值: %s", e)
    return _SITE_DEFAULTS


# ── 公共函数 1：本地时钟 ──────────────────────────────────────────────────

def get_site_times() -> Dict[str, str]:
    """
    返回各站点当前本地时间。
    格式：{"sudbury": "07:32", "pilbara": "20:32", "atacama": "08:32"}

    依赖 pytz；若未安装则降级为 UTC 偏移估算。
    """
    sites = _load_sites()
    result: Dict[str, str] = {}

    try:
        import pytz
        _use_pytz = True
    except ImportError:
        _use_pytz = False
        logger.warning("site_info: pytz 未安装，使用 UTC 偏移估算本地时间")

    # 粗略 UTC 偏移（pytz 缺失时的降级方案）
    _FALLBACK_OFFSET = {
        "America/Toronto":  -5,
        "Australia/Perth":   8,
        "America/Santiago": -3,
    }

    for name, info in sites.items():
        tz_name = info.get("timezone", "UTC")
        try:
            if _use_pytz:
                import pytz
                tz = pytz.timezone(tz_name)
                local_dt = datetime.now(tz)
            else:
                from datetime import timezone as _tz, timedelta
                offset = _FALLBACK_OFFSET.get(tz_name, 0)
                local_dt = datetime.now(_tz.utc).replace(tzinfo=None)
                from datetime import timedelta
                local_dt = datetime.utcnow() + timedelta(hours=offset)
            result[name] = local_dt.strftime("%H:%M")
        except Exception as e:
            logger.debug("site_info: 获取 %s 时间失败: %s", name, e)
            result[name] = "--:--"

    return result


# ── 公共函数 2：实时天气 ──────────────────────────────────────────────────

_weather_cache: Dict[str, Any] = {"ts": 0.0, "data": {}}


def get_site_weather() -> Dict[str, Dict[str, Any]]:
    """
    从 OpenWeatherMap Current Weather API 获取各站点天气，10 分钟缓存。
    格式：{"sudbury": {"temp": -5, "desc": "Light snow", "icon": "❄"}, ...}

    API Key 从环境变量 OPENWEATHER_API_KEY 读取。
    未设置 Key 时返回占位数据（temp=None, desc="N/A", icon="~"）。
    """
    now = time.time()
    # 缓存命中
    if now - _weather_cache["ts"] < 600.0 and _weather_cache["data"]:
        return _weather_cache["data"]

    api_key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
    sites   = _load_sites()
    result: Dict[str, Dict[str, Any]] = {}

    if not api_key:
        # 无 API Key：返回占位，不报错，dashboard 正常运行
        logger.debug("site_info: OPENWEATHER_API_KEY 未设置，天气显示为 N/A")
        for name in sites:
            result[name] = {"temp": None, "desc": "N/A", "icon": "~"}
        _weather_cache.update({"ts": now, "data": result})
        return result

    import requests as _requests

    for name, info in sites.items():
        lat = info.get("lat", 0)
        lon = info.get("lon", 0)
        try:
            url = (
                f"https://api.openweathermap.org/data/2.5/weather"
                f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
            )
            resp = _requests.get(url, timeout=5, headers={"User-Agent": "DataFactory/3.7"})
            resp.raise_for_status()
            data = resp.json()

            temp     = round(data["main"]["temp"])
            main_key = data["weather"][0]["main"]          # e.g. "Snow"
            desc     = data["weather"][0]["description"].capitalize()
            icon     = _OWM_EMOJI.get(main_key, "~")
            result[name] = {"temp": temp, "desc": desc, "icon": icon}

        except Exception as e:
            logger.warning("site_info: 获取 %s 天气失败: %s", name, e)
            # 保留上次缓存值（避免因短暂网络问题清空数据）
            prev = _weather_cache.get("data", {}).get(name)
            result[name] = prev if prev else {"temp": None, "desc": "N/A", "icon": "~"}

    _weather_cache.update({"ts": now, "data": result})
    return result
