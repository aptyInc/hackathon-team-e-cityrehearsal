"""Weather endpoints for the Lingampally -> Lakdikapul corridor. Owner: Data and proof workstream.

    GET /weather?day=july|2026-07-DD&hour=H   that hour's July weather (data/raw/weather_july_hourly.csv, measured
                                              (Open-Meteo reanalysis)). day=july (default): mean over the 31 days and the
                                              share of days with rain at that hour. No hour: all 24 hours of that day.
    GET /weather/now                          current conditions at the corridor's midpoint (Open-Meteo forecast API,
                                              model data), cached 10 minutes; 503 when Open-Meteo cannot be reached
    GET /weather/factors                      the rain factors (data/rain/rain_factors.json + data/weather/results.json):
                                              how much rain slows the trip and each stretch, with 95% ranges (estimated)

Hour H means the slot H:00-H+1:00, as in TomTom's hourly data and POST /corridor/runs {hour}. Rain in a slot is the
total over that hour; temperature, humidity, wind and cloud cover are the values at the end of the hour.
Every answer carries `label` and `source`. The rain-class names match POST /corridor/runs {weather}: an hour's
`what_if` is the simulation setting that matches it ("dry", "light_rain", "heavy_rain").
"""
import csv, json, os, re, subprocess, threading, time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parents[2]
WEATHER_CSV = ROOT / "data/raw/weather_july_hourly.csv"
FACTORS = ROOT / "data/rain/rain_factors.json"
RESULTS = ROOT / "data/weather/results.json"
WATERLOGGING = ROOT / "data/weather/waterlogging_points.json"
LABEL = "measured (Open-Meteo reanalysis)"
SOURCE = "Open-Meteo historical weather archive (ERA5-based reanalysis, ~9 km grid), mean of 3 points on the corridor"
POINTS = {"A_lingampally": "Lingampally", "M_gachibowli": "Khajaguda (Gachibowli)", "B_lakdikapul": "Lakdikapul"}
MID = {"name": "Khajaguda X Roads (corridor midpoint by distance)", "lat": 17.4227, "lon": 78.3821}
NOW_URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=precipitation,rain,showers,"
           "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,cloud_cover,is_day&timezone=Asia%2FKolkata")
NOW_TTL_S = 600
WHAT_IF = {"dry": "dry", "light": "light_rain", "moderate": "heavy_rain", "heavy": "heavy_rain"}
WMO = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
       51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
       61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
       71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers", 81: "Showers",
       82: "Violent showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail",
       99: "Thunderstorm with hail"}

router = APIRouter()
_lock = threading.Lock()
_mem: dict = {}


def _num(v):
    if v in ("", None):
        return None
    f = float(v)
    return int(f) if f.is_integer() and "." not in str(v) else f


def rain_class(mm_per_hour: float) -> str:
    """Same limits as data/weather/analyse_weather_hourly.py: dry < 0.1, light < 1, moderate 1-5, heavy > 5 mm/h."""
    return "dry" if mm_per_hour < 0.1 else "light" if mm_per_hour < 1 else "moderate" if mm_per_hour <= 5 else "heavy"


def rows() -> dict:
    """{(date, hour): row} from weather_july_hourly.csv, re-read when the file changes."""
    if not WEATHER_CSV.exists():
        raise HTTPException(404, "data/raw/weather_july_hourly.csv missing: run data/weather/analyse_weather_hourly.py")
    m = WEATHER_CSV.stat().st_mtime
    with _lock:
        if _mem.get("csv_mtime") != m:
            _mem["csv"] = {(r["date"], int(r["hour"])): r for r in csv.DictReader(WEATHER_CSV.open())}
            _mem["csv_mtime"] = m
        return _mem["csv"]


def factors() -> dict:
    if not FACTORS.exists():
        raise HTTPException(404, "data/rain/rain_factors.json missing")
    return json.loads(FACTORS.read_text())


def waterlogging() -> dict | None:
    """data/weather/waterlogging_points.json: reported water-logging hotspots per corridor junction (public sources,
    not measured by us), the extra speed factors the simulation applies there, and which severities flood in each
    rain class. None without the file."""
    return json.loads(WATERLOGGING.read_text()) if WATERLOGGING.exists() else None


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def expected_waterlogging(cls: str) -> dict:
    """The junctions likely to flood in this rain class (dry / light / moderate / heavy), with the extra speed factor
    the simulation applies there, and one plain sentence for the screen."""
    wl = waterlogging()
    what_if = WHAT_IF.get(cls, "dry")
    label = "reported (public sources), not measured by us"
    if not wl:
        return {"rain_class": cls, "what_if": what_if, "junctions": [], "names": [], "label": label,
                "text": "water-logging points not available (data/weather/waterlogging_points.json missing)"}
    sev = wl.get("expected_at", {}).get(cls, [])
    table = wl.get("extra_speed_factor", {}).get(what_if, {})
    js = [{"junction_id": p["junction_id"], "name": p["name"], "short": p.get("short", p["name"]), "severity": p.get("severity"),
           "extra_speed_factor": table.get(p.get("severity"), 1.0), "what_reported": p.get("what_reported"),
           "label": wl["extra_speed_factor"].get("label", "assumed, scaled by reported severity")}
          for p in wl.get("points", []) if p.get("severity") in sev]
    names = [j["short"] for j in js]
    kind = {"dry": "Dry", "light": "Light rain", "moderate": "Moderate rain", "heavy": "Heavy rain"}[cls]
    main = [j["short"] for j in js if j["severity"] in ("high", "medium")]
    minor = len(js) - len(main)
    if not js:
        text = f"{kind}: no water-logging expected at the reported points" if cls != "dry" else "Dry: no water-logging expected"
    else:
        tail = f", and {minor} minor one{'s' if minor > 1 else ''}" if main and minor else ""
        text = (f"{kind}: expect longer queues at {_join(main or names)} (reported water-logging point{'s' if len(js) > 1 else ''}"
                f"{'; chronic ones only' if cls == 'light' else ''}{tail})")
    return {"rain_class": cls, "what_if": what_if, "junctions": js, "names": names, "text": text, "label": label,
            "sim": f"POST /corridor/runs {{weather: '{what_if}'}} caps the lanes within {wl.get('radius_m', 300)} m of these junctions "
                   f"by extra_speed_factor on top of the stretch rain factor" if js else None}


def _effect(cls: str, f: dict | None) -> dict | None:
    """The estimated trip-time effect of an hour of this rain class (from rain_factors.json), in plain numbers."""
    if not f:
        return None
    s = (f.get("what_if") or {}).get("settings", {}).get(WHAT_IF.get(cls, "dry"))
    if not s:
        return None
    t, ci = s.get("trip_travel_time_factor"), s.get("trip_travel_time_factor_ci95") or [None, None]
    pct = lambda x: None if x is None else round((x - 1) * 100, 1)   # noqa: E731
    return {"what_if": WHAT_IF.get(cls, "dry"), "trip_time_pct": pct(t), "trip_time_pct_ci95": [pct(ci[0]), pct(ci[1])],
            "meaning": s.get("meaning"), "label": "estimated"}


def one_slot(r: dict, f: dict | None) -> dict:
    cls = r["rain_class"]
    return {"date": r["date"], "hour": int(r["hour"]), "slot": r["slot"],
            "rain_mm": _num(r["precipitation_mean"]), "rain_class": cls, "what_if": WHAT_IF.get(cls, "dry"),
            "temperature_c": _num(r["temperature_2m_mean"]), "humidity_pct": _num(r["relative_humidity_2m_mean"]),
            "wind_kmh": _num(r["wind_speed_10m_mean"]), "cloud_cover_pct": _num(r["cloud_cover_mean"]),
            "weather_code": _num(r["weather_code_mean"]), "text": r["weather_text"],
            "by_point": {p: {"name": n, "rain_mm": _num(r[f"precipitation_{p}"]), "temperature_c": _num(r[f"temperature_2m_{p}"]),
                             "weather_code": _num(r[f"weather_code_{p}"])} for p, n in POINTS.items()},
            "rain_effect": _effect(cls, f), "expected_waterlogging": expected_waterlogging(cls)}


def july_slot(data: dict, hour: int, f: dict | None) -> dict:
    rs = [data[k] for k in sorted(data) if k[1] == hour]
    mean = lambda col: round(sum(float(r[col]) for r in rs) / len(rs), 2)   # noqa: E731
    mm = [float(r["precipitation_mean"]) for r in rs]
    texts = [r["weather_text"] for r in rs]
    common = max(set(texts), key=texts.count)
    classes = {c: round(sum(r["rain_class"] == c for r in rs) / len(rs), 3) for c in ("dry", "light", "moderate", "heavy")}
    return {"date": "july", "hour": hour, "slot": f"{hour:02d}:00-{hour + 1:02d}:00", "days": len(rs),
            "rain_mm": mean("precipitation_mean"), "rain_mm_max": round(max(mm), 2),
            "share_of_days_with_rain": round(sum(x >= 0.1 for x in mm) / len(mm), 3),
            "share_of_days_with_rain_1mm": round(sum(x >= 1 for x in mm) / len(mm), 3),
            "share_of_days_by_class": classes,
            "temperature_c": mean("temperature_2m_mean"), "humidity_pct": mean("relative_humidity_2m_mean"),
            "wind_kmh": mean("wind_speed_10m_mean"), "cloud_cover_pct": mean("cloud_cover_mean"),
            "text": f"Typical July {hour:02d}:00: rain on {round(100 * sum(x >= 0.1 for x in mm) / len(mm))}% of days "
                    f"({round(100 * sum(x >= 1 for x in mm) / len(mm))}% with 1 mm or more); most often {common.lower()}",
            "most_common_text": common,
            # the wettest class seen on 10%+ of July days at this hour: the water-logging to plan for at this hour
            "expected_waterlogging": expected_waterlogging(next((c for c in ("heavy", "moderate", "light") if classes[c] >= 0.1), "dry"))}


@router.get("/weather")
def get_weather(day: str = Query("july", description="'july' (typical July day) or a date 2026-07-01..2026-07-31"),
                hour: int | None = Query(None, description="0..23: the slot hour:00-hour+1:00; none = all 24 hours")):
    """July 2026 weather on the corridor for one hour (or all 24) of a day, or of a typical July day."""
    d = (day or "july").strip().lower()
    if d != "july" and not re.fullmatch(r"2026-07-(0[1-9]|[12]\d|3[01])", d):
        raise HTTPException(400, f"day must be 'july' or a date from 2026-07-01 to 2026-07-31, got {day!r}")
    if hour is not None and not 0 <= hour <= 23:
        raise HTTPException(400, f"hour must be between 0 and 23 (meaning hh:00-hh+1:00), got {hour}")
    data = rows()
    try:
        f = factors()
    except HTTPException:
        f = None
    hours = [hour] if hour is not None else list(range(24))
    out = [july_slot(data, h, f) for h in hours] if d == "july" else [one_slot(data[(d, h)], f) for h in hours]
    if d == "july":
        for s in out:     # what an hour of the commonest kind of rain (light) does to the trip
            s["rain_effect_when_raining"] = _effect("light", f)
    head = {"day": d, "source": SOURCE, "label": LABEL, "rain_effect_label": "estimated (data/rain/rain_factors.json)",
            "note": "reanalysis on a ~9 km grid: good for 'did it rain here that hour', smooths short downpours; "
                    "rain in a slot is the total over that hour"}
    return head | (out[0] if hour is not None else {"hours": out})


def _fetch_now() -> dict:
    """Open-Meteo's current conditions at the corridor midpoint (the raw answer). Tries Python, then curl (some
    laptops fail Python's certificate check). Raises RuntimeError when both fail."""
    url = NOW_URL.format(lat=MID["lat"], lon=MID["lon"])
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=8) as r:
            return json.load(r)
    except Exception as e:
        try:
            out = subprocess.run(["curl", "-sSf", "--max-time", "8", url], capture_output=True, text=True, timeout=12)
            if out.returncode == 0 and out.stdout.startswith("{"):
                return json.loads(out.stdout)
            raise RuntimeError(out.stderr.strip()[:200] or "no answer")
        except Exception as e2:
            raise RuntimeError(f"{type(e).__name__}: {e}; curl: {e2}")


def now_payload(raw: dict) -> dict:
    cur = raw["current"]
    interval = float(cur.get("interval") or 3600)
    mm = float(cur.get("precipitation") or 0.0)
    rate = round(mm * 3600 / interval, 2)
    cls = rain_class(rate)
    code = cur.get("weather_code")
    try:
        f = factors()
    except HTTPException:
        f = None
    return {"time": cur.get("time"), "interval_s": int(interval), "rain_mm": mm, "rain_mm_per_hour": rate,
            "is_raining": rate >= 0.1, "rain_class": cls, "what_if": WHAT_IF[cls],
            "temperature_c": cur.get("temperature_2m"), "humidity_pct": cur.get("relative_humidity_2m"),
            "wind_kmh": cur.get("wind_speed_10m"), "cloud_cover_pct": cur.get("cloud_cover"), "is_day": bool(cur.get("is_day")),
            "weather_code": code, "text": WMO.get(code, "Unknown"),
            "location": MID | {"grid": [raw.get("latitude"), raw.get("longitude")]},
            "rain_effect": _effect(cls, f), "expected_waterlogging": expected_waterlogging(cls),
            "source": "Open-Meteo forecast API, current conditions (weather model, 15-minute data)",
            "label": "modelled (Open-Meteo forecast), not a rain gauge"}


@router.get("/weather/now")
def weather_now():
    """Weather right now at the corridor's midpoint; cached for 10 minutes. 503 when Open-Meteo cannot be reached."""
    with _lock:
        hit = _mem.get("now")
        if hit and time.time() - hit["at"] < NOW_TTL_S:
            return hit["payload"] | {"cached": True, "age_s": round(time.time() - hit["at"])}
    try:
        payload = now_payload(_fetch_now())
    except Exception as e:
        stale = _mem.get("now")
        msg = f"current weather unavailable (Open-Meteo could not be reached: {str(e)[:160]})"
        if stale:    # an older answer is better than none; say how old
            return stale["payload"] | {"cached": True, "stale": True, "age_s": round(time.time() - stale["at"]), "warning": msg}
        raise HTTPException(503, msg)
    payload["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with _lock:
        _mem["now"] = {"at": time.time(), "payload": payload}
    return payload | {"cached": False, "age_s": 0}


@router.get("/weather/factors")
def weather_factors():
    """How much rain slows the trip and each stretch (estimated, July 2026 hourly), and the simulation's what-if settings."""
    f = factors()
    res = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    h = res.get("headline", {})
    wi = f.get("what_if", {})
    legs = wi.get("legs", [])
    per_leg = res.get("per_leg", [])
    pct = lambda x: None if x is None else round((x - 1) * 100, 1)   # noqa: E731
    return {
        "label": f.get("label", "estimated"), "confidence": f.get("confidence"), "basis": f.get("basis"),
        "headline": {"any_rain": h.get("any_rain"), "by_class": h.get("by_class"), "sustained": h.get("sustained"),
                     "previous_hour_per_mm": h.get("previous_hour_per_mm"), "within_day_check": h.get("within_day_check"),
                     "mean_trip_min": res.get("data", {}).get("mean_trip_min_06_23")},
        "data": {k: res.get("data", {}).get(k) for k in ("traffic", "weather", "slots", "days", "hours", "slots_by_rain_class",
                                                         "typical_mm_per_hour", "max_hourly_rain_mm", "class_limits_mm_per_hour")},
        "what_if": {name: {"meaning": s.get("meaning"), "class": s.get("class"),
                           "trip_time_pct": pct(s.get("trip_travel_time_factor")),
                           "trip_time_pct_ci95": [pct(x) for x in s.get("trip_travel_time_factor_ci95") or [None, None]],
                           "per_leg_speed_factor": s.get("per_leg_speed_factor")}
                    for name, s in wi.get("settings", {}).items()},
        "per_leg": [{"leg": l["leg"], "from": l["from"], "to": l["to"], "distance_m": l["distance_m"], "mean_min": l["mean_min"],
                     "light": l.get("light"), "moderate": l.get("moderate"), "sustained": l.get("sustained"),
                     "sim_speed_factor": {name: s.get("per_leg_speed_factor", {}).get(l["leg"]) for name, s in wi.get("settings", {}).items()}}
                    for l in per_leg] if per_leg else [{"leg": k} for k in legs],
        "first_look": f.get("first_look"),
        "sim": {"post_corridor_runs_field": "weather", "values": list(wi.get("settings", {}).keys()), "how": wi.get("how"),
                "input_label": "estimated (rain factors from TomTom hourly x Open-Meteo, July 2026)"},
        "source_files": f.get("source_files"),
        "waterlogging": _waterlogging_factors(),
    }


def _waterlogging_factors() -> dict:
    """The reported water-logging points with their sources, the extra speed factors per rain setting, and which
    junctions flood in each what-if (for /weather/factors)."""
    wl = waterlogging()
    if not wl:
        return {"label": "reported (public sources), not measured by us", "points": [], "note": "data/weather/waterlogging_points.json missing"}
    return {"label": wl.get("label"), "what_this_is": wl.get("what_this_is"), "radius_m": wl.get("radius_m"),
            "extra_speed_factor": wl.get("extra_speed_factor"), "expected_at": wl.get("expected_at"),
            "severity_meaning": wl.get("severity_meaning"), "how": wl.get("how_the_simulation_uses_it"),
            "points": wl.get("points", []), "not_found": wl.get("not_found", []), "sources_checked": wl.get("sources_checked", []),
            "by_what_if": {w: expected_waterlogging(c)["names"] for c, w in (("light", "light_rain"), ("heavy", "heavy_rain"))},
            "updated": wl.get("updated")}
