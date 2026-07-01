#!/usr/bin/env python3
"""
meteo_core.py — Récupération + consolidation des données météo APDL/IH/marées.

Partagé par :
  - fetch_meteo.py        (one-shot, pour GitHub Actions -> live.json)
  - cva_meteo_proxy.py    (serveur local de dev, optionnel)

Aucune clé secrète n'est requise : l'API liveweather.apdl.pt s'authentifie via
une session Laravel Sanctum (cookie CSRF public).
"""

import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://liveweather.apdl.pt"
LOCODE = "PTLEI"

ENDPOINTS = {
    "apdl":  f"{BASE}/api/weather/latest/apdl/{LOCODE}",
    "ih":    f"{BASE}/api/weather/latest/ih/{LOCODE}",
    "tides": f"{BASE}/api/tides/{LOCODE}/chart",
    "fc":    f"{BASE}/api/weather/forecasts/{LOCODE}",
    "astro": f"{BASE}/api/weather/latest/astronomical/{LOCODE}",
}

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def deg_to_card(deg):
    if deg is None:
        return None
    return COMPASS[int((float(deg) % 360) / 22.5 + 0.5) % 16]


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Récupération (session Sanctum, une passe)
# --------------------------------------------------------------------------- #
def new_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (CVA-meteo)",
        "Referer": f"{BASE}/",
    })
    s.get(f"{BASE}/sanctum/csrf-cookie", timeout=30)
    xsrf = urllib.parse.unquote(s.cookies.get("XSRF-TOKEN", ""))
    s.headers.update({
        "X-XSRF-TOKEN": xsrf,
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def fetch_all():
    """Retourne {clé: payload JSON} pour les 5 endpoints (exception si auth KO)."""
    s = new_session()
    raw = {}
    for key, url in ENDPOINTS.items():
        r = s.get(url, timeout=30)
        r.raise_for_status()
        raw[key] = r.json()
    return raw


# --------------------------------------------------------------------------- #
# Consolidation
# --------------------------------------------------------------------------- #
def _sensors(payload):
    return {s["code"]: s for s in (payload or {}).get("sensors", [])}


def _sensor_block(s):
    if not s:
        return None
    return {
        "name": s.get("name"),
        "value": fnum(s.get("value")),
        "unit": s.get("unit"),
        "trend": s.get("trend"),
        "sparkline": [fnum(x) for x in s.get("sparklineData", []) if fnum(x) is not None],
    }


def _local_offset_hours(naive_local_str):
    try:
        local = datetime.strptime(naive_local_str, "%Y-%m-%d %H:%M:%S")
        utc = datetime.now(timezone.utc).replace(tzinfo=None)
        return round((local - utc).total_seconds() / 3600.0)
    except Exception:
        return 0


def _to_local_hm(iso_utc, offset_h):
    try:
        dt = datetime.fromisoformat(iso_utc)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return (dt + timedelta(hours=offset_h)).strftime("%H:%M")
    except Exception:
        return None


def _next_event(events, now_str):
    if not events:
        return None
    fut = [e for e in events if e.get("time", "") >= now_str]
    e = (fut or events)[0]
    hm = e["time"][11:16] if len(e.get("time", "")) >= 16 else e.get("time")
    return {"time": hm, "level_m": fnum(e.get("level"))}


def _build_forecast(fc, offset_h, hours=24):
    if not fc:
        return []
    rows = {r["sensor"]["code"]: r["values"] for r in fc.get("rows", [])}
    timeline = fc.get("timeline", [])

    def at(code, i):
        vals = rows.get(code)
        if not vals or i >= len(vals):
            return None
        return fnum(vals[i].get("value"))

    out = []
    for i, t in enumerate(timeline[:hours]):
        hm = _to_local_hm(t["datetime"].replace(" ", "T") + "+00:00", offset_h)
        out.append({
            "hour": (hm[:2] + "h") if hm else t.get("hour"),
            "wind_kn": at("VVT", i),
            "wind_dir_deg": at("IVT", i),
            "beaufort": at("EBF", i),
            "wave_m": at("AST", i),
            "swell_m": at("ASO", i),
            "period_s": at("TPP", i),
            "water_temp_c": at("TWA", i),
            "wave_power_kw": at("POT", i),
        })
    return out


def consolidate(raw):
    """raw -> dict JSON consommé par le widget. Inclut un timestamp absolu."""
    apdl = _sensors(raw.get("apdl"))
    ih = _sensors(raw.get("ih"))
    astro = _sensors(raw.get("astro"))
    tides = raw.get("tides") or {}
    fc = raw.get("fc") or {}

    last_dt = (raw.get("apdl") or {}).get("last_datetime", "")
    offset_h = _local_offset_hours(last_dt) if last_dt else 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def val(d, code):
        return fnum(d.get(code, {}).get("value")) if d.get(code) else None

    fc_built = _build_forecast(fc, offset_h)
    wave_power = fc_built[0].get("wave_power_kw") if fc_built else None

    curve = []
    for p in tides.get("tides", []):
        try:
            dt = datetime.strptime(p["time"], "%Y-%m-%d %H:%M:%S")
            curve.append([int(dt.timestamp()), fnum(p.get("level"))])
        except Exception:
            continue

    now_utc = datetime.now(timezone.utc)
    return {
        "updated_at": last_dt or now_str,
        "generated_at": now_utc.isoformat(timespec="seconds"),
        "generated_epoch": int(now_utc.timestamp()),
        "station": "APDL Leixões — Estação Física",
        "stale": False,
        "wind": {
            "speed_kn": val(apdl, "VVT"),
            "gust_kn": val(apdl, "RVT"),
            "direction_deg": val(apdl, "DVT"),
            "direction_card": deg_to_card(val(apdl, "DVT")),
            "trend": apdl.get("VVT", {}).get("trend"),
            "sparkline": _sensor_block(apdl.get("VVT"))["sparkline"] if apdl.get("VVT") else [],
        },
        "atmosphere": {
            "pressure_mbar": val(apdl, "PAT"),
            "temp_air_c": val(apdl, "TAR"),
            "humidity_pct": val(apdl, "HRE"),
            "rain_mm": val(apdl, "PER"),
        },
        "sea": {
            "wave_height_m": val(ih, "ASZ"),
            "wave_max_m": val(ih, "AMV"),
            "period_peak_s": val(ih, "TPP"),
            "period_mean_s": val(ih, "TPM"),
            "swell_direction_deg": val(ih, "DPP"),
            "swell_direction_card": deg_to_card(val(ih, "DPP")),
            "water_temp_c": val(ih, "TWA"),
            "sea_level_m": val(ih, "IOB"),
            "wave_power_kw_m": wave_power,
        },
        "tides": {
            "next_high": _next_event(tides.get("highs"), now_str),
            "next_low": _next_event(tides.get("lows"), now_str),
            "curve": curve,
        },
        "forecast_24h": fc_built,
        "astro": {
            "sunrise": _to_local_hm(astro.get("NSS", {}).get("value", ""), offset_h),
            "sunset": _to_local_hm(astro.get("PSS", {}).get("value", ""), offset_h),
            "moonrise": _to_local_hm(astro.get("NSL", {}).get("value", ""), offset_h),
            "moonset": _to_local_hm(astro.get("PSL", {}).get("value", ""), offset_h),
        },
        "sensors": {
            code: _sensor_block(src.get(code))
            for code, src in {
                "VVT": apdl, "RVT": apdl, "DVT": apdl, "PAT": apdl,
                "TAR": apdl, "HRE": apdl, "PER": apdl,
                "ASZ": ih, "AMV": ih, "TPP": ih, "TPM": ih,
                "DPP": ih, "TWA": ih, "IOB": ih,
            }.items() if src.get(code)
        },
    }
