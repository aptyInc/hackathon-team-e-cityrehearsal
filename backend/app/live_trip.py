"""Live trip estimate for the corridor, Lingampally -> Lakdikapul (A->B), from TomTom's live Traffic Flow.

GET /corridor/live_trip (route in corridor.py) serves live_trip(): one refresh asks TomTom's Traffic Flow Segment Data
(`flowSegmentData`, TOMTOM_MAPS_KEY) about the 16 points of data/live/flow_points.json (1-2 per leg, on the corridor's own
carriageway, away from junctions and, where possible, from flyovers with a road underneath: build_flow_points.py). The
answer is cached for 5 minutes (stale-while-error: an older answer, marked stale, when TomTom cannot be reached; 503 when
there is none). Budget: at most 24 requests a refresh, at most CR_LIVE_DAILY_CAP (2000) a day (TomTom's free tier is
2,500 non-tile requests a day); beyond that the last answer is served.

Every answer is checked before it is used: the road class must be FRC0-3 and the returned road must run along the
corridor A->B near the point (its vertices within 25 m of TomTom's route geometry, in the A->B direction); a point
that snapped to another road (the road under a flyover, the other carriageway, a side street) is dropped.

Estimator (per leg k), in plain words:
    T_k = T_quiet_k x F_k
  T_quiet_k  TomTom Traffic Stats' July 2026 leg time at the leg's quietest hour of the day (night): the leg at free flow
             on TomTom Stats' own scale, so the waiting at signals that every trip has is in it (measured).
  F_k        the live congestion factor: freeFlowSpeed / currentSpeed of the leg's points (TomTom live flow: how much
             slower than free flow the road is right now), confidence-weighted; points on the same TomTom flow segment
             count once. With low confidence (TomTom then leans on its historical speeds) F_k leans the same way, towards
             the July same-hour factor: F_k = c x F_live + (1 - c) x F_july_hour, c = the points' mean confidence.
  Why not simply distance / live speed (reported as flow_only_time_s): the flow speed is a segment average measured
  away from the junctions here, so it misses part of the signal waiting; TomTom's free-flow speed matches Stats' quiet
  hour closely (checked: night flow 38 km/h over 16.8 km vs Stats 40 km/h at 04:00), so scaling the quiet-hour leg time
  by the same live/free-flow ratio keeps both on TomTom Stats' scale. Equivalently: the July same-hour leg time x (live
  congestion / July same-hour congestion).
  Sanity terms:
  - live junction delay (TomTom Junction Analytics, data/raw/tomtom_corridor_junction_live.csv): the leg takes at
    least its free-flow time plus the time lost right now on the corridor's A->B approach to the junction ending it
    (delay_s, latest snapshot at most 20 minutes old): T_k = max(T_k, T_quiet_k + delay_s). Points mid-leg cannot see
    a queue at the junction; this catches it. usual_delay_s and the excess over it are reported, not used.
  - bounds: 0.6 x T_quiet_k <= T_k <= 3 x the leg's slowest July hour.
  - a leg without a usable point takes its July same-hour time (confidence 0 for that leg).
  Trip total = sum of the legs; confidence = the legs' confidences weighted by their time. Labels: speeds "measured
  (TomTom live flow)", the trip and leg times "estimated".

Now-cast runs (POST /corridor/runs {day: "live"}) use frozen(): the estimate of the current 10-minute bucket, kept for
the whole bucket, so a baseline and its variants in the same bucket are fitted to the same live trip.
"""
import csv, json, math, os, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
POINTS = ROOT / "data/live/flow_points.json"
ROUTE_JSON = ROOT / "data/tomtom/corridor/10051304.json"
CALIBRATION = ROOT / "sim/corridor/calibration.json"
LIVE_DIR = Path(os.getenv("CR_LIVE_DIR", ROOT / "data/live"))       # budget, frozen buckets and the request log (gitignored)
IST = timezone(timedelta(hours=5, minutes=30))
REFRESH_S = 300                    # cache: one TomTom refresh per 5 minutes at most
BUCKET_S = 600                     # now-cast runs: one fit per 10-minute bucket
MAX_PER_REFRESH = 24
DAILY_CAP = int(os.getenv("CR_LIVE_DAILY_CAP", "2000"))
JA_FRESH_S = 20 * 60
FLOW_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json?point={lat},{lon}&unit=KMPH&key={key}"
SPEED_LABEL = "measured (TomTom live flow)"
TRIP_LABEL = "estimated"
NEAR_M, ON_ROUTE_M = 400, 25       # check: the returned road's vertices within NEAR_M of the point lie within ON_ROUTE_M of the route


class LiveUnavailable(Exception):
    """No live estimate to serve (no key, no points file, TomTom unreachable and nothing cached, budget spent)."""


def key() -> str | None:
    return (os.getenv("TOMTOM_MAPS_KEY") or "").strip() or None


def available() -> bool:
    """Can GET /corridor/live_trip work at all (key and points file present)? No network call."""
    return bool(key()) and POINTS.exists()


def points() -> list[dict]:
    return json.loads(POINTS.read_text())["points"][:MAX_PER_REFRESH]


def _scrub(msg: str) -> str:
    k = key()
    return msg.replace(k, "***") if k else msg


def fetch_point(pt: dict) -> dict:
    """TomTom's flowSegmentData for one point (the raw `flowSegmentData` object). Python first (certifi's
    certificates), then curl. RuntimeError (key scrubbed) when both fail."""
    url = FLOW_URL.format(lat=pt["lat"], lon=pt["lon"], key=key())
    try:
        import ssl, urllib.request
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
        with urllib.request.urlopen(url, timeout=8, context=ctx) as r:
            return json.load(r)["flowSegmentData"]
    except Exception as e:
        try:
            out = subprocess.run(["curl", "-sS", "--max-time", "8", url], capture_output=True, text=True, timeout=12)
            if out.returncode == 0 and out.stdout.lstrip().startswith("{"):
                body = json.loads(out.stdout)
                if "flowSegmentData" in body:
                    return body["flowSegmentData"]
                raise RuntimeError(str(body)[:200])
            raise RuntimeError(out.stderr.strip()[:200] or out.stdout.strip()[:200] or "no answer")
        except Exception as e2:
            raise RuntimeError(_scrub(f"{type(e).__name__}: {e}; curl: {e2}"))


FETCH = fetch_point     # the smoke test replaces this (no network)


# ---------- geometry ----------
def _m(a, b) -> float:
    """Metres between (lon, lat) points (equirectangular; fine at corridor scale)."""
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((b[0] - a[0]) * 111320 * k, (b[1] - a[1]) * 110540)


_route_mem: dict = {}


def route():
    """TomTom's route A->B as ([(lon, lat)], cumulative metres), from the Traffic Stats job geometry."""
    if "line" not in _route_mem:
        segs = json.loads(ROUTE_JSON.read_text())["routes"][0]["segmentResults"]
        pts = []
        for s in segs:
            for q in s["shape"]:
                p = (q["longitude"], q["latitude"])
                if not pts or pts[-1] != p:
                    pts.append(p)
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + _m(a, b))
        _route_mem["line"] = (pts, cum)
    return _route_mem["line"]


def _project(line, cum, p, lo=0, hi=None):
    """(offset m, metres along) of p's closest point on line[lo:hi]."""
    best = None
    hi = len(line) - 1 if hi is None else min(hi, len(line) - 1)
    for i in range(max(0, lo), hi):
        a, b = line[i], line[i + 1]
        k = math.cos(math.radians(a[1]))
        bx, by = (b[0] - a[0]) * 111320 * k, (b[1] - a[1]) * 110540
        px, py = (p[0] - a[0]) * 111320 * k, (p[1] - a[1]) * 110540
        L2 = bx * bx + by * by
        t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, (px * bx + py * by) / L2))
        d = math.hypot(px - t * bx, py - t * by)
        if best is None or d < best[0]:
            best = (d, cum[i] + t * math.sqrt(L2))
    return best or (1e9, 0.0)


def check(pt: dict, raw: dict) -> tuple[bool, str | None, dict]:
    """Is TomTom's answer about the corridor's own carriageway A->B? (ok, reason when not, details)."""
    frc = raw.get("frc")
    coords = [(c["longitude"], c["latitude"]) for c in (raw.get("coordinates") or {}).get("coordinate", [])]
    info = {"frc": frc, "segment_m": round(sum(_m(a, b) for a, b in zip(coords, coords[1:])))}
    if frc not in ("FRC0", "FRC1", "FRC2", "FRC3"):
        return False, f"road class {frc}: not the corridor (FRC0-3)", info
    if len(coords) < 2:
        return False, "no road geometry in the answer", info
    p = (pt["lon"], pt["lat"])
    near = [c for c in coords if _m(c, p) <= NEAR_M]
    if len(near) < 2:      # sparse vertices on a straight road: the two around the point
        i = min(range(len(coords)), key=lambda i: _m(coords[i], p))
        near = coords[max(0, i - 1):i + 2]
    line, cum = route()
    # search the route only around the point (the route crosses itself nowhere, but keeps the check cheap)
    along_p = pt.get("along_m")
    lo = hi = None
    if along_p is not None:
        lo = max(0, next((i for i, c in enumerate(cum) if c >= along_p - 1500), 0) - 1)
        hi = next((i for i, c in enumerate(cum) if c >= along_p + 1500), len(cum) - 1) + 1
    proj = [_project(line, cum, c, lo or 0, hi) for c in near]
    on = [d <= ON_ROUTE_M for d, _ in proj]
    info["near_on_route"] = round(sum(on) / len(on), 2)
    if sum(on) / len(on) < 0.8:
        return False, f"snapped to another road ({sum(on)} of {len(on)} nearby vertices on the corridor)", info
    if proj[-1][1] - proj[0][1] < 5:
        return False, "snapped to the other carriageway (B->A)", info
    return True, None, info


# ---------- inputs from files ----------
def _ja_excess(now: datetime) -> dict:
    """{junction id: {...}} live junction delay of the corridor's A->B approach (TomTom Junction Analytics): the latest
    snapshot's delay_s, usual_delay_s and excess, when at most JA_FRESH_S old. The A->B approach is the one
    calibration.json's tomtom.corridor names for "fwd" (the busiest of that name)."""
    from .corridor import JA_LIVE      # same file (and env override) as GET /corridor/junctions/live
    try:
        fwd = {j: d["fwd"]["road"] for j, d in json.loads(CALIBRATION.read_text())["tomtom"]["corridor"].items() if "fwd" in d}
    except Exception:
        return {}
    if not JA_LIVE.exists() or not fwd:
        return {}
    latest: dict[str, tuple[datetime, list]] = {}
    with JA_LIVE.open() as f:
        for r in csv.DictReader(f):
            j = r["junction_id"]
            if j not in fwd or r["approach"] != fwd[j]:
                continue
            t = datetime.fromisoformat(r["time"])
            cur = latest.get(j)
            if cur is None or t > cur[0]:
                latest[j] = (t, [r])
            elif t == cur[0]:
                cur[1].append(r)
    out = {}
    for j, (t, rows) in latest.items():
        age = (now - t).total_seconds()
        if age > JA_FRESH_S:
            continue
        r = max(rows, key=lambda r: float(r.get("volume_per_hour") or 0))
        d, u = float(r.get("delay_s") or 0), float(r.get("usual_delay_s") or 0)
        out[j] = {"id": j, "approach": r["approach"], "approach_id": r["approach_id"], "delay_s": d, "usual_delay_s": u,
                  "excess_s": round(d - u, 1), "time": r["time"], "age_s": round(age), "label": "measured (TomTom Junction Analytics)"}
    return out


def _july():
    """TomTom Traffic Stats July 2026 hourly leg times (GET /corridor's tomtom.hourly)."""
    from .corridor import tomtom_hourly, corridor_def
    h = tomtom_hourly()
    if not h or "july" not in h["by_day"]:
        raise LiveUnavailable("TomTom's July hourly leg times are missing (data/raw/corridor_legs_tomtom.csv)")
    names = {p["id"]: p["name"] for p in corridor_def()["points"]}
    return h["legs"], {int(k): v for k, v in h["by_day"]["july"].items()}, names


# ---------- estimate ----------
def estimate(samples: list[dict], now: datetime) -> dict:
    """The live trip from checked samples [{point, raw | error}] (see the module docstring)."""
    legs_meta, july, names = _july()
    hour = now.hour
    same = july.get(hour) or july[min(july, key=lambda h: abs(h - hour))]
    quiet = [min(july[h]["legs_s"][k] for h in july) for k in range(len(legs_meta))]
    slowest = [max(july[h]["legs_s"][k] for h in july) for k in range(len(legs_meta))]
    ja = _ja_excess(now)
    by_leg: dict[int, dict] = {}
    pts_out, warnings = [], []
    for s in samples:
        pt, raw = s["point"], s.get("raw")
        row = {"id": pt["id"], "leg": pt["leg"], "lat": pt["lat"], "lon": pt["lon"], "on_flyover": pt.get("on_flyover", False)}
        if raw is None:
            row.update(ok=False, reason=f"TomTom did not answer: {s.get('error', 'unknown')}"[:200])
        else:
            ok, reason, info = check(pt, raw)
            cur, ff = raw.get("currentSpeed"), raw.get("freeFlowSpeed")
            row.update(ok=ok, reason=reason, **info, current_speed_kmh=cur, free_flow_speed_kmh=ff,
                       current_travel_time_s=raw.get("currentTravelTime"), free_flow_travel_time_s=raw.get("freeFlowTravelTime"),
                       confidence=raw.get("confidence"), road_closure=bool(raw.get("roadClosure")))
            if ok and ff:
                sig = (raw.get("currentTravelTime"), raw.get("freeFlowTravelTime"), info["segment_m"])
                by_leg.setdefault(pt["leg"], {})[sig] = row        # same TomTom segment twice in a leg: once
        pts_out.append(row)
    bad = [p for p in pts_out if not p["ok"]]
    if bad:
        warnings.append(f"{len(bad)} of {len(pts_out)} TomTom points not used: " + "; ".join(f"{p['id']} {p['reason']}" for p in bad[:4]))
    legs = []
    for k, lm in enumerate(legs_meta):
        a, b = lm["from_id"], lm["to_id"]
        d = float(lm["distance_m"])
        t_hour = float(same["legs_s"][k])
        f_july = t_hour / quiet[k]
        rows = list(by_leg.get(k, {}).values())
        leg = {"from_id": a, "to_id": b, "from_name": names.get(a, a), "to_name": names.get(b, b), "distance_m": round(d),
               "july_same_hour_s": round(t_hour), "july_quietest_s": round(quiet[k]), "label": TRIP_LABEL}
        if rows:
            w = [max(0.05, float(r["confidence"] or 0)) for r in rows]
            closed = any(r["road_closure"] for r in rows)
            factors = [4.0 if (r["road_closure"] or not r["current_speed_kmh"]) else
                       max(0.5, min(4.0, r["free_flow_speed_kmh"] / r["current_speed_kmh"])) for r in rows]
            f_live = sum(x * y for x, y in zip(w, factors)) / sum(w)
            conf = sum(float(r["confidence"] or 0) for r in rows) / len(rows)
            factor = conf * f_live + (1 - conf) * f_july
            cur = [r["current_speed_kmh"] for r in rows if r["current_speed_kmh"]]
            ffs = [r["free_flow_speed_kmh"] for r in rows]
            v_cur = sum(w) / sum(wi / max(1.0, v) for wi, v in zip(w, [r["current_speed_kmh"] or 1.0 for r in rows]))
            leg["flow"] = {"current_speed_kmh": round(v_cur, 1) if cur else None,
                           "free_flow_speed_kmh": round(sum(w) / sum(wi / v for wi, v in zip(w, ffs)), 1),
                           "confidence": round(conf, 2), "points": len(rows), "road_closure": closed, "label": SPEED_LABEL}
            leg["flow_only_time_s"] = round(d / (v_cur / 3.6)) if cur else None
            basis = "live flow"
        else:
            conf, factor, f_live = 0.0, f_july, None
            leg["flow"] = None
            leg["flow_only_time_s"] = None
            basis = "July same hour (no usable live point)"
        t = quiet[k] * factor
        leg["congestion_factor"] = round(factor, 3)
        leg["july_same_hour_factor"] = round(f_july, 3)
        jx = ja.get(b)
        if jx:
            jx = dict(jx, used=False)
            floor = quiet[k] + jx["delay_s"]       # free-flow running + the junction's live waiting
            if t < floor:
                t, jx["used"] = floor, True
                basis += " + live junction delay"
        leg["junction"] = jx
        t = max(0.6 * quiet[k], min(3 * slowest[k], t))
        leg.update(time_s=round(t), speed_kmh=round(d / t * 3.6, 1), confidence=round(conf, 2), basis=basis)
        legs.append(leg)
    total = sum(l["time_s"] for l in legs)
    conf = sum(l["confidence"] * l["time_s"] for l in legs) / max(1, total)
    hour_total = float(same["total_s"])
    return {
        "corridor_id": "lingampally_lakdikapul", "direction": "A->B", "as_of": now.isoformat(timespec="seconds"),
        "time_label": now.strftime("%H:%M IST"), "hour": hour,
        "trip": {"total_s": total, "total_min": round(total / 60, 1), "distance_m": sum(l["distance_m"] for l in legs),
                 "label": TRIP_LABEL, "confidence": round(conf, 2),
                 "confidence_label": "high" if conf >= 0.8 else "medium" if conf >= 0.5 else "low",
                 "july_same_hour_total_s": round(hour_total), "july_same_hour_min": round(hour_total / 60, 1),
                 "july_same_hour_label": f"Typical July day {hour:02d}:00-{(hour + 1) % 24:02d}:00 (TomTom Traffic Stats, measured)",
                 "vs_july_same_hour": round(total / hour_total, 3), "delta_s": round(total - hour_total),
                 "july_quietest_total_s": round(sum(quiet))},
        "legs": legs, "points": pts_out, "warnings": warnings,
        "labels": {"speeds": SPEED_LABEL, "trip_total": TRIP_LABEL, "leg_times": TRIP_LABEL,
                   "july": "measured (TomTom Traffic Stats, July 2026)", "junction": "measured (TomTom Junction Analytics)"},
        "source": "TomTom Traffic Flow Segment Data (live), points in data/live/flow_points.json; TomTom Traffic Stats July "
                  "2026 hourly leg times; TomTom Junction Analytics (live junction delays)",
        "method": "leg time = July quietest-hour leg time x live congestion (free-flow / current speed), confidence-weighted "
                  "towards the July same-hour congestion; at least the quietest-hour time + the live junction delay; "
                  "a leg without a usable point keeps its July same-hour time (backend/app/live_trip.py)",
    }


# ---------- budget, cache, log ----------
_lock = threading.Lock()          # one refresh at a time; callers during a refresh wait for its answer
_mem: dict = {}


def _now() -> datetime:
    return datetime.now(IST)


def _budget(add: int = 0) -> dict:
    """Requests sent today (IST), kept in LIVE_DIR/budget.json; `add` counts new ones."""
    path = LIVE_DIR / "budget.json"
    today = _now().date().isoformat()
    try:
        b = json.loads(path.read_text())
    except Exception:
        b = {}
    if b.get("date") != today:
        b = {"date": today, "requests": 0, "refreshes": 0}
    if add:
        b["requests"] += add
        b["refreshes"] += 1
        try:
            LIVE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(b))
        except OSError:
            pass
    return b


def _log(payload: dict):
    """One line per refresh in LIVE_DIR/flow_log.jsonl (gitignored): what TomTom said, for later calibration."""
    try:
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        with (LIVE_DIR / "flow_log.jsonl").open("a") as f:
            f.write(json.dumps({"as_of": payload["as_of"], "total_s": payload["trip"]["total_s"],
                                "confidence": payload["trip"]["confidence"],
                                "legs_s": [l["time_s"] for l in payload["legs"]],
                                "points": [{k: p.get(k) for k in ("id", "ok", "current_speed_kmh", "free_flow_speed_kmh",
                                                                  "confidence", "frc", "segment_m", "road_closure")}
                                           for p in payload["points"]]}, separators=(",", ":")) + "\n")
    except OSError:
        pass


def refresh() -> dict:
    """Ask TomTom now (len(points) requests, in parallel) and build the estimate. LiveUnavailable when nothing is usable."""
    if not key():
        raise LiveUnavailable("TOMTOM_MAPS_KEY is not set (.env)")
    if not POINTS.exists():
        raise LiveUnavailable("data/live/flow_points.json is missing (python data/live/build_flow_points.py)")
    pts = points()
    used = _budget()
    if used["requests"] + len(pts) > DAILY_CAP:
        raise LiveUnavailable(f"today's TomTom budget is spent ({used['requests']} of {DAILY_CAP} requests); serving no new data until tomorrow")
    now = _now()

    def one(pt):
        try:
            return {"point": pt, "raw": FETCH(pt)}
        except Exception as e:
            return {"point": pt, "raw": None, "error": _scrub(str(e))[:200]}

    with ThreadPoolExecutor(6) as pool:
        samples = list(pool.map(one, pts))
    b = _budget(add=len(pts))
    if not any(s["raw"] for s in samples):
        raise LiveUnavailable("TomTom live flow could not be reached: " + (samples[0].get("error") or "no answer"))
    payload = estimate(samples, now)
    if not any(p["ok"] for p in payload["points"]):
        raise LiveUnavailable("TomTom answered, but no point matched the corridor's road (all snapped elsewhere)")
    payload["requests"] = {"this_refresh": len(pts), "per_refresh_max": MAX_PER_REFRESH, "today": b["requests"],
                           "daily_cap": DAILY_CAP, "refresh_s": REFRESH_S}
    _log(payload)
    return payload


def live_trip(force: bool = False) -> dict:
    """The live trip estimate, cached for REFRESH_S; stale-while-error. LiveUnavailable when there is nothing to serve."""
    with _lock:
        hit = _mem.get("trip")
        if hit and not force and time.time() - hit["at"] < REFRESH_S:
            return hit["payload"] | {"cached": True, "stale": False, "age_s": round(time.time() - hit["at"])}
        try:
            payload = refresh()
        except LiveUnavailable as e:
            if hit:
                return hit["payload"] | {"cached": True, "stale": True, "age_s": round(time.time() - hit["at"]),
                                         "warnings": hit["payload"]["warnings"] + [f"live data not refreshed: {e}"]}
            raise
        _mem["trip"] = {"at": time.time(), "payload": payload}
        return payload | {"cached": False, "stale": False, "age_s": 0}


# ---------- now-cast buckets ----------
def bucket_of(now: datetime) -> str:
    """The 10-minute bucket a time falls in, e.g. '2026-10-10T10:20+05:30'."""
    b = now.replace(minute=now.minute - now.minute % (BUCKET_S // 60), second=0, microsecond=0)
    return b.isoformat(timespec="minutes")


_frozen: dict = {}


def frozen(now: datetime | None = None) -> dict:
    """The live estimate now-cast runs use in this 10-minute bucket (the first one asked for in it, kept for the bucket,
    also across API restarts: LIVE_DIR/buckets.json). LiveUnavailable when there is none."""
    now = now or _now()
    b = bucket_of(now)
    with _lock:
        if b in _frozen:
            return _frozen[b]
        path = LIVE_DIR / "buckets.json"
        try:
            disk = json.loads(path.read_text())
        except Exception:
            disk = {}
        if b in disk:
            _frozen[b] = disk[b]
            return disk[b]
    est = live_trip()
    if est.get("stale") and est.get("age_s", 0) > BUCKET_S * 3:
        raise LiveUnavailable(f"the last live estimate is {est['age_s'] // 60} min old and TomTom cannot be reached now")
    keep = {k: est.get(k) for k in ("as_of", "hour", "trip", "legs", "warnings", "labels", "method", "source", "stale", "age_s")}
    keep["bucket"] = b
    with _lock:
        _frozen.setdefault(b, keep)
        try:
            disk = json.loads(path.read_text()) if path.exists() else {}
        except Exception:
            disk = {}
        disk[b] = _frozen[b]
        for old in sorted(disk)[:-36]:
            disk.pop(old)
        try:
            LIVE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(disk))
        except OSError:
            pass
        return _frozen[b]
