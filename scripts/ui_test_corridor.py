"""Headless browser test of the corridor view (frontend/corridor.html), clicked the way a user does.

Cases
  A  Load: no errors, 13 markers (A, 1..11, B), header card (Lingampally → Lakdikapul, 22.4 km through 11 junctions)
     above the controls, bar "Real data · typical day" (REAL, 58.2 min, junction ticks), route drawn wide and coloured by real speeds,
     4 quick demo buttons with tooltips, "Start engine" / "Run with changes", the weather slider (As measured), the live
     junction panel always shown (accordion, or a note when there is no data), layers (live traffic off, queues and delay
     badges on); the 6 junctions the main road already crosses on a flyover marked in the picker ("(flyover exists)") and
     on the map; the removed controls (day, hour, modes, rain strip, weather chip, Live now link) are gone; no "TomTom" or
     "July" in the visible text (map attribution aside)
  P  One screen: no modes; a #mode=live hash is ignored (also after a reload); live and simulated controls side by side
  C  Changes: kind chips (flyover, underpass, signal, widening, one-way, U-turn "(soon)" disabled, aria-pressed) and
     controls per kind match sim/templates/corridor.py (flyover lanes/length, signal cycle + main-road share slider,
     widening, one-way with its note); add, update (same junction and kind), add another, remove; markers highlight
     changed junctions; flyovers at Nanal Nagar and Rethibowli merge into one 1.2 km flyover (note), and the "one flyover
     over both" button; a flyover/underpass (or signal change) where the main road already runs on a flyover gets a short
     note before simulating, and can still be added
  D  Start engine: no second bar, a line "Simulated today: X min (real data Y)" from the API or the sample fallback,
     junction table, sample tag when sample
  E  Run with changes: a second bar "Simulated with your changes", "With your changes: X min · ±D min vs the simulation
     of today's roads", per-leg deltas, knock-on, before/after table, warnings
  F  Camera: table row, map marker, strip block and "Whole corridor" move the map
  G  Layers: route on/off, live traffic off by default and on/off, delay badges on/off
  H  API path (corridor endpoints mocked in the browser): request body (no day / hour), no sample tag, vehicle playback
     from WS frames, play/pause, scrub; route drawn side by side (today + with changes) with a dark casing
  I  Real route line from GET /corridor (route geometry + measured legs per period): legs cut along the road,
     coloured by real speed before a run and by simulated speed after
  J  Live junctions (GET /corridor/junctions/live mocked): an accordion, one row per junction (worst delay badge, Live
     time, old data flagged); expanding one shows worst approaches, delay vs usual, last hour, queue, flies there with a
     popup (Real data · live) and collapses the others; again: collapses and flies back; LIVE map badges, queues,
     refresh; no "TomTom"/"July" with a junction open
  L  Long runs: presets fill the list and simulate; elapsed counter + "usually under 2 minutes" while waiting; the rest of
     the page stays usable; preset bodies (DLF 30% main road, one flyover j08 1200 m, flyovers j01 and j02 600 m);
     a flyover where one exists: note before, then the result's warning in plain words in the trip panel, nothing drawn
  M  Errors: HTTP 500 plain text and FastAPI {"detail"} shown as the message (no silent fallback), buttons back
  O  3D: pitched camera, buildings loaded per junction in view (mocked GET /corridor/buildings/{id}), vehicles culled to the
     view and raised on the flyover (z), flyover structure drawn with ramps and piers, follow a test car, orbit, night,
     dots instead of boxes from the whole-corridor view
  N  Narrow screen (390 px): header card on top, then the map, panels stacked under it, no sideways scroll, live panel
     from flat snapshot rows, GET /corridor in the backend's real shape (tomtom.periods, per-leg route features); live
     junctions on a phone without approach shapes (404: queues stay in the panel); no day / hour ever sent
  Q  Playback pill, one timeline: 0 .. sim_minutes_total of the measured period, the recorded minutes drawn on the track;
     scrubbing inside them plays from there, outside them asks POST /corridor/runs
     for the same run with frames_from_min / frames_minutes 5 (progress while waiting), plays it, keeps it (no second request)
  R  Follow a car: a test car's whole trip from Lingampally (GET /runs/{id}/probes mocked), A -> B progress bar with 11 junction
     ticks, direction toggle (Lakdikapul -> Lingampally), Stop; clicking a car follows it; highlighted car (colour, halo, trail), info
     card (speed, stretch, minutes since Lingampally, flyover), test cars listed with direction and departure, click a vehicle
     to follow it; the ride runs Lingampally -> Lakdikapul at 10-60x with other traffic only inside the recorded window
  S  Labels: two bars "Real data · typical day" (REAL) and "Simulated with your changes" (SIMULATED), footnote with the
     route lengths (GET /corridor/calibration tomtom_basis_detail) saying the change is measured against today's
     simulation, clock "Minute M:SS of N · Simulated typical day" (no clock time); the page never probes the API with
     an hour; no "TomTom"/"July" after a run
  W  Weather (GET /corridor sim.weather, /weather/factors, /weather/now mocked with backend/app/weather.py): a slider
     Dry / As measured (default) / Light rain / Heavy rain under the changes; a what-if is explained with its estimate and
     95% range (estimated), sent as `weather` with every run, quick demo and re-recorded window, named in today's line, the changes bar,
     clock and result line; changing it re-simulates once; the header shows the weather now ("Real data · live"), hidden
     on 503
  WL Water-logging (GET /weather/factors waterlogging mocked): Heavy / Light rain on the slider names the reported points
     ("reported, not measured by us") and drops a droplet per point on the map (exact spot when given), none when dry or
     as measured; a rain run's result line names the slower lanes and compares with the as-measured run (trip, stretches,
     queues). The junction advisor (GET /agent/advice/{jid} 404 -> POST /agent/advise/{jid}?async=1, polled; or 200
     pre-computed): progress with a clock, headline, SIMULATED, the ranked options table, Show on map loads the run
     (GET /runs/{id}); another junction hides it. Chat suggestions from GET /agent/suggestions
  V  Now-cast (GET /corridor sim.live, /corridor/live_trip and POST /corridor/runs?async=1 day "live" mocked): the right panel
     shows the live trip (minutes vs typical day same hour, confidence, as of, STALE badge, 12 stretches coloured by live
     speed); Simulate now posts day "live", polls, shows elapsed time, then time.label, the night badge, the legend (cars
     SIMULATED, roads REAL) and plays the vehicles on the same map (vehicles / vehicle-dots, playback pill "Now" / "With the
     change") with the live queues on; Try a change now sends live_bucket (410: run again); 503 hides it
  Z  View (frontend/viewguard.js): ctrl+wheel (trackpad pinch) over a panel is cancelled so the page cannot zoom, over the
     map it still zooms the map; viewport meta maximum-scale=1; at 1280x700 every panel fits the window with its own scroll;
     collapse / expand the controls, live and trip panels; the Reset view pill (and R, not while typing) brings back the
     whole-corridor camera from above, stops follow and orbit, reopens and scrolls up every panel; Esc stops following;
     "Whole corridor" still works; a zoomed page shows a toast (dismissable); at 390 px the pill stays on screen
  K  No page errors at any point

The first page talks to the real API on :8000 (if running) except POST /corridor/runs, which is answered 404 so the
sample fallback is tested deterministically; the other pages mock every corridor endpoint in the browser.

Usage (API on :8000 if available; repo root served on :5180):
    python3 -m http.server 5180 &        # from the repo root
    PLAYWRIGHT_BROWSERS_PATH=~/Library/Caches/ms-playwright .venv/bin/python scripts/ui_test_corridor.py [url]
Screenshots: sim/out/corridor_<case>.png. Exit code 1 if any check fails.
"""
import csv
import json
import math
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5180/frontend/corridor.html"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app import weather as WX  # noqa: E402  (the weather endpoints' own code answers the mocked GET /weather*)
OUT = ROOT / "sim/out"
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = json.loads((ROOT / "contracts/samples/corridor_results.sample.json").read_text())
CORRIDOR = json.loads((ROOT / "data/corridor/corridor.json").read_text())
PTS = {p["id"]: p for p in CORRIDOR["points"]}
ORDER = [p["id"] for p in CORRIDOR["points"]]
TT_ROWS = list(csv.DictReader((ROOT / "data/raw/corridor_legs_tomtom.csv").open()))
TYPICAL = "2026-07-01..2026-07-31 6:00-23:00"
RUN_MSG = "Simulating 21 km of traffic, usually under 2 minutes"
errors, results = [], []
case = ""


def check(ok, what):
    results.append((case, bool(ok), what))
    print(("  ok   " if ok else "  FAIL ") + what)


def wait_status(pg, words, seconds=120):
    t0 = time.time()
    while time.time() - t0 < seconds:
        st = pg.inner_text("#status")
        if any(w in st for w in words):
            return st, time.time() - t0
        pg.wait_for_timeout(300)
    return pg.inner_text("#status"), time.time() - t0


def layer(pg, lid):
    return pg.evaluate(f"() => {{ const l = overlay._deck.props.layers.find(l => l.id === '{lid}'); return l ? l.props.data.length : -1; }}")


def route_data(pg):
    return pg.evaluate("() => { const l = overlay._deck.props.layers.find(l => l.id === 'route'); return l ? l.props.data.map(d => [d.path.length, d.kmh]) : []; }")


def strips(pg):
    return pg.eval_on_selector_all("#strips .strip[data-strip]", "els => els.map(e => [e.dataset.strip, e.querySelectorAll('.leg').length, e.querySelector('.total').textContent, e.querySelector('.name').textContent])")


def center_near(pg, pid, tol_px=40):
    """The point sits where the page puts a junction it flies to: map centre shifted by VIEW_OFFSET (clear of the panels)."""
    p = PTS[pid]
    xy = pg.evaluate(f"() => {{ const q = map.project([{p['lon']}, {p['lat']}]), c = map.getContainer(); return [q.x - c.clientWidth / 2 - VIEW_OFFSET[0], q.y - c.clientHeight / 2 - VIEW_OFFSET[1]]; }}")
    return abs(xy[0]) < tol_px and abs(xy[1]) < tol_px, {"lng": xy[0], "lat": xy[1]}


def pick_kind(pg, kind):
    """The kind of change is a row of chips (the hidden #iv-kind select follows them): click the chip, as a user does."""
    pg.click(f"#iv-kinds [data-kind={kind}]")
    pg.wait_for_timeout(100)


def set_weather(pg, v):
    """The weather slider: 0 Dry, 1 As measured (default), 2 Light rain, 3 Heavy rain."""
    pg.eval_on_selector("#weather", "(e, v) => { e.value = v; e.dispatchEvent(new Event('input')); e.dispatchEvent(new Event('change')); }", str(v))


def banned_text(pg):
    """'TomTom' / 'July' in the visible text, the map attribution ("© TomTom") left out: [word: context, ...]."""
    return pg.evaluate("""() => { const a = [...document.querySelectorAll('.maplibregl-ctrl-attrib')], old = a.map(e => e.style.display);
        a.forEach(e => { e.style.display = 'none'; }); const t = document.body.innerText; a.forEach((e, i) => { e.style.display = old[i]; });
        const out = []; for (const w of ['TomTom', 'July']) { let i = t.indexOf(w); while (i >= 0 && out.length < 8) { out.push(w + ': ' + t.slice(Math.max(0, i - 50), i + 30).replace(/\\s+/g, ' ')); i = t.indexOf(w, i + 1); } }
        return out; }""")


def add_iv(pg, jid, kind, params=None):
    pg.select_option("#iv-j", jid)
    pick_kind(pg, kind)
    for k, v in (params or {}).items():
        sel = f"#iv-params [data-k={k}]"
        if pg.eval_on_selector(sel, "e => e.tagName") == "INPUT":
            pg.fill(sel, str(v))
        else:
            pg.select_option(sel, str(v))
    pg.click("#iv-add")
    pg.wait_for_timeout(200)


def ivs(pg):
    return pg.eval_on_selector_all("#iv-list .iv span", "els => els.map(e => e.textContent)")


def live_rows(pg, jid):
    return pg.eval_on_selector_all(f"#live .lj[data-id={jid}] tr.ap", "els => els.map(e => [...e.cells].map(c => c.textContent))")


def has_pins(pg):
    return pg.eval_on_selector_all(".pin.has", "els => els.map(e => e.textContent)")


def clear_ivs(pg):
    while pg.locator("#iv-list .iv button").count():
        pg.locator("#iv-list .iv button").first.click()
        pg.wait_for_timeout(100)


def simulate(pg, button, label):
    pg.click(button)
    pg.wait_for_timeout(50)
    st, dt = wait_status(pg, ["simulated", "rror", "failed", "answered"], 600)
    check("simulated" in st and label in st, f"{label}: {st} ({dt:.0f} s)")
    check(not pg.is_disabled("#sim-today") and not pg.is_disabled("#sim-changes"), "simulate buttons usable again")
    return st


def frames_3d(n_frames=40):
    """frames_along(j07, j08) plus: 3 cars on the Tolichowki flyover (z 6 m), a test car (probe_fwd_1) driving from Shaikpet
    to Nanal Nagar, and 20 vehicles far away at Lingampally (must not be drawn when the camera is at Tolichowki)."""
    out = frames_along("j07", "j08", n_frames)
    p6, p7, p8, pa = PTS["j06"], PTS["j07"], PTS["j08"], PTS["A_lingampally"]
    for t, fr in enumerate(out):
        for i in range(3):
            fr["vehicles"].append({"id": f"fly{i}", "type": "car", "lon": p7["lon"] + 0.0004 * (i - 1) + t * 0.00001, "lat": p7["lat"] - 0.0001 * (i - 1), "z": 6.0, "angle": 100.0, "speed": 15.0})
        f = t / (n_frames - 1)
        a, z = (p6, p7) if f < 0.5 else (p7, p8)
        g = f * 2 if f < 0.5 else (f - 0.5) * 2
        fr["vehicles"].append({"id": "probe_fwd_1", "type": "car", "lon": a["lon"] + (z["lon"] - a["lon"]) * g, "lat": a["lat"] + (z["lat"] - a["lat"]) * g, "z": 0.0, "angle": 120.0, "speed": 9.0})
        for i in range(20):
            fr["vehicles"].append({"id": f"far{i}", "type": "two_wheeler", "lon": pa["lon"] + i * 0.00005, "lat": pa["lat"] - i * 0.00005, "z": 0.0, "angle": 160.0, "speed": 5.0})
    return out


def building_fc():
    sq = lambda dx, dy, s=0.0002: [[[PTS["j07"]["lon"] + dx, PTS["j07"]["lat"] + dy], [PTS["j07"]["lon"] + dx + s, PTS["j07"]["lat"] + dy],
                                     [PTS["j07"]["lon"] + dx + s, PTS["j07"]["lat"] + dy + s], [PTS["j07"]["lon"] + dx, PTS["j07"]["lat"] + dy + s], [PTS["j07"]["lon"] + dx, PTS["j07"]["lat"] + dy]]]
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"height": 15, "num_floors": 5}, "geometry": {"type": "Polygon", "coordinates": sq(0.0006, 0.0006)}},
        {"type": "Feature", "properties": {"height": None, "num_floors": 4}, "geometry": {"type": "Polygon", "coordinates": sq(-0.0009, 0.0005)}},
        {"type": "Feature", "properties": {"height": None, "num_floors": None}, "geometry": {"type": "Polygon", "coordinates": sq(0.0005, -0.0009)}},
        {"type": "Feature", "properties": {"height": 30}, "geometry": {"type": "MultiPolygon", "coordinates": [sq(-0.0012, -0.0012), sq(-0.0016, -0.0012)]}}]}


def layer_props(pg, lid, js):
    return pg.evaluate(f"() => {{ const l = overlay._deck.props.layers.find(l => l.id === '{lid}'); return l ? ({js})(l) : null; }}")


def frames_along(a, b, n_frames=40, n_veh=30):
    """Synthetic C1 frames: vehicles driving from point a to point b (for the playback test only)."""
    pa, pb = PTS[a], PTS[b]
    ang = math.degrees(math.atan2((pb["lon"] - pa["lon"]) * math.cos(math.radians(pa["lat"])), pb["lat"] - pa["lat"])) % 360
    types = ["two_wheeler", "two_wheeler", "car", "auto", "bus"]
    out = []
    for t in range(n_frames):
        vs = []
        for i in range(n_veh):
            f = min(1.0, (i / n_veh) * 0.6 + t * 0.006)
            vs.append({"id": f"v{i}", "type": types[i % 5], "lon": pa["lon"] + (pb["lon"] - pa["lon"]) * f,
                       "lat": pa["lat"] + (pb["lat"] - pa["lat"]) * f + (i % 3 - 1) * 0.00002, "z": 0, "angle": ang, "speed": 6.0})
        out.append({"t": float(t), "vehicles": vs})
    return out


def route_geojson():
    """A bendy stand-in for the backend's route: each leg bows ~40 m off the straight line, 12 vertices per leg; plus B -> A."""
    ab = []
    for a, b in zip(ORDER, ORDER[1:]):
        pa, pb = PTS[a], PTS[b]
        for k in range(12):
            t = k / 12
            dx, dy = pb["lon"] - pa["lon"], pb["lat"] - pa["lat"]
            n = math.hypot(dx, dy) or 1
            off = math.sin(math.pi * t) * 0.0004
            ab.append([pa["lon"] + dx * t - dy / n * off, pa["lat"] + dy * t + dx / n * off])
    ab.append([PTS[ORDER[-1]]["lon"], PTS[ORDER[-1]]["lat"]])
    ba = [[x + 0.00005, y + 0.00005] for x, y in reversed(ab)]
    return {"type": "FeatureCollection", "features": [  # B -> A first, to check the page picks the A -> B line itself
        {"type": "Feature", "properties": {"direction": "B->A"}, "geometry": {"type": "LineString", "coordinates": ba}},
        {"type": "Feature", "properties": {"direction": "A->B"}, "geometry": {"type": "LineString", "coordinates": ab}}]}


API_PERIODS = [TYPICAL, "2026-07-05..2026-07-05 8:00-20:00", "2026-07-08..2026-07-08 8:00-20:00"]
API_LEGS = [{"period": r["period"], "from_id": r["from_id"], "to_id": r["to_id"], "from_name": r["from"], "to_name": r["to"],
             "distance_m": float(r["distance_m"]), "time_s": float(r["time_s"]), "speed_kmh": float(r["speed_kmh"])}
            for r in TT_ROWS if r["period"] in API_PERIODS]
TYPICAL_KMH = [x["speed_kmh"] for x in API_LEGS if x["period"] == TYPICAL]


def live_nested(counts):
    """GET /corridor/junctions/live, nested shape (latest per approach + a 60-minute mean). Once counts["v2"] is set, NH163 changes."""
    v2 = counts.get("v2", False)
    t = "2026-10-09T17:18:58+05:30" if v2 else "2026-10-09T17:17:58+05:30"
    ap = lambda name, d, u, q, v, m=None: {"approach_id": name, "name": name, "delay_s": d, "usual_delay_s": u, "queue_m": q, "volume_per_hour": v, "time": t, "stale": False,
                                           **({"last_60min": {"samples": 44, "delay_s": m, "queue_m": q}} if m is not None else {})}
    return {"source": "TomTom Junction Analytics (test)", "window_minutes": 60,
            "labels": {"delay_s": "measured", "usual_delay_s": "measured", "queue_m": "estimated", "volume_per_hour": "estimated"}, "junctions": [
        {"id": "j07", "name": "Tolichowki", "time": t, "age_s": 20, "approaches": [
            ap("Mumbai Road East Bound", 19, 15, 0, 3586, 17), ap("Moti Darwaja Road North Bound", 33, 19, 105.67, 70, 25),
            ap("Seven Tombs Road East Bound", 23, 20, 59.11, 900), ap("Hakimpet Road South Bound", 20, 20, 106.46, 1183), ap("North Bound", 0, 0, 0, 0)]},
        {"id": "j08", "name": "Nanal Nagar jn", "time": t, "age_s": 20, "approaches": [
            ap("Mehdipatnam Road West Bound", 47, 36, 750.58, 4036, 40), ap("NH163 North Bound", 131 if v2 else 108, 80, 148.96, 1911, 95),
            ap("Mumbai Road East Bound", 73, 17, 131.05, 4933, 60), ap("Inner Ring Road North Bound", 52, 9, 5.11, 1681), ap("North Bound", 0, 0, 0, 0)]},
        {"id": "j09", "name": "Rethibowli jn", "time": t, "age_s": 1500, "approaches": [
            ap("Mehdipatnam Road West Bound", 60, 17, 1100.31, 4921), ap("Mandela Gudem Road North Bound", 178, 131, 297.32, 341),
            ap("Mumbai Road East Bound", 103, 88, 378.92, 4540), ap("Inner Ring Road North Bound", 50, 15, 62.11, 2008)]}]}


def live_flat():
    """The same data as flat CSV-like rows, two snapshots: the page shows the latest and averages the last hour itself."""
    rows = []
    for t, k in (("2026-10-09T16:50:00+05:30", 0.5), ("2026-10-09T17:20:00+05:30", 1.0)):
        rows += [{"time": t, "junction_id": "j08", "junction": "Nanal Nagar jn", "approach_id": "a1", "approach": "NH163 North Bound",
                  "delay_s": 100 * k, "usual_delay_s": 80, "queue_m": 150, "volume_per_hour": 1900, "label": "measured (volume, queue: estimated)"},
                 {"time": t, "junction_id": "j08", "junction": "Nanal Nagar jn", "approach_id": "a2", "approach": "Mumbai Road East Bound",
                  "delay_s": 70 * k, "usual_delay_s": 17, "queue_m": 130, "volume_per_hour": 4900, "label": "measured (volume, queue: estimated)"}]
    return rows


def approach_line(jid, k, length=2000, n=20):
    """A straight 2 km approach into a junction, ordered towards it (GET /corridor/junctions/geometry)."""
    p = PTS[jid]
    ang = math.radians(k * 72 + 10)
    dlat, dlon = math.cos(ang) / 111320, math.sin(ang) / (111320 * math.cos(math.radians(p["lat"])))
    return [[p["lon"] + dlon * length * (1 - i / n), p["lat"] + dlat * length * (1 - i / n)] for i in range(n + 1)]


def geometry_body():
    return [{"junction_id": j["id"], "approaches": [{"approach_id": a["approach_id"], "name": a["name"], "coordinates": approach_line(j["id"], k)}
                                                     for k, a in enumerate(j["approaches"])]} for j in live_nested({})["junctions"]]


def probe_tracks():
    """GET /runs/{id}/probes: one test car each way over the whole corridor (12 legs, 10 points a leg)."""
    fwd, n = [], len(ORDER) - 1
    for k, (a, z) in enumerate(zip(ORDER, ORDER[1:])):
        pa, pz = PTS[a], PTS[z]
        for i in range(10):
            f = i / 10
            fwd.append({"t": 600 + 3300 * (k + f) / n, "lon": pa["lon"] + (pz["lon"] - pa["lon"]) * f, "lat": pa["lat"] + (pz["lat"] - pa["lat"]) * f,
                        "z": 0.0, "speed": 7.0, "leg": k})
    fwd.append({"t": 3900, "lon": PTS[ORDER[-1]]["lon"], "lat": PTS[ORDER[-1]]["lat"], "z": 0.0, "speed": 0.0, "leg": n - 1})
    rev = [dict(q, t=660 + (3900 - q["t"])) for q in reversed(fwd)]
    return [{"id": "probe_fwd_1", "direction": "fwd", "depart_s": 600, "arrive_s": 3900, "total_s": 3300, "points": fwd},
            {"id": "probe_rev_1", "direction": "rev", "depart_s": 660, "arrive_s": 3960, "total_s": 3300, "points": rev}]


CALIBRATION = {"tomtom_basis": "test", "tomtom_basis_detail": {"simulated_route_km": 21.65, "calibration_tomtom_min": 56.2, "tomtom_route_km": 22.42,
                                                               "tomtom_route_min": 58.2, "tomtom_period": "Typical July day (06-23)", "data_label": "measured speeds, simulated distances"}}
FOOT = ("Our simulated route is 21.6 km (the measured route: 22.4 km). Over the same 21.6 km real data measured 56 min; the simulation gives 98 min. "
        "The change is measured against the simulation of today's roads, not against real data.")
BASE_MIN = f"{SAMPLE['baseline']['journey']['total_s'] / 60:.1f}"   # today's simulation (the sample / the mocked API), one decimal
GONE = ("#when", "#hour", "#hour-box", "#hour-note", "#hour-spark", "#rain-strip", "#wx-chip", "#when-note", "#live-link",
        "#mode-live", "#mode-july", "#mode-head", "#status-live", "#see-live")   # controls the one-screen page no longer has
HF = {"july": lambda h: 0.7 + 0.03 * h, "2026-07-08": lambda h: 0.8 + 0.03 * h, "2026-07-20": lambda h: 0.75 + 0.02 * h}   # trip time by hour (test profile)
HSRC = {"july": TYPICAL, "2026-07-08": "2026-07-08..2026-07-08 8:00-20:00", "2026-07-20": TYPICAL}


def hourly_body():
    """GET /corridor tomtom.hourly, as the backend sends it: legs, days, hours, by_day {day: {"h": {total_s, legs_s}}}."""
    legs = lambda d: [x for x in API_LEGS if x["period"] == HSRC[d]]
    prof = lambda d: {str(h): {"total_s": sum(x["time_s"] for x in legs(d)) * HF[d](h), "legs_s": [x["time_s"] * HF[d](h) for x in legs(d)]} for h in range(24)}
    return {"source": "test", "data_label": "measured", "legs": [{"from_id": x["from_id"], "to_id": x["to_id"], "distance_m": x["distance_m"]} for x in legs("july")],
            "days": [{"day": "july", "label": "Typical July day"}, {"day": "2026-07-08", "label": "Wed 8 Jul"}, {"day": "2026-07-20", "label": "Mon 20 Jul"}],
            "hours": list(range(24)), "by_day": {d: prof(d) for d in HF}}


def hourly_min(d, h):
    return round(sum(x["time_s"] for x in API_LEGS if x["period"] == HSRC[d]) * HF[d](h) / 60)


WX_TRIP = {"dry": 1.0, "light_rain": 1.04, "heavy_rain": 1.079}   # rain what-if: trip time factor vs dry (as in rain_factors.json)
WX_CI = {"dry": [1.0, 1.0], "light_rain": [1.005, 1.069], "heavy_rain": [0.961, 1.161]}
WX_NOW_RAIN = {"time": "2026-10-10T00:15", "interval_s": 900, "rain_mm": 0.2, "rain_mm_per_hour": 0.8, "is_raining": True, "rain_class": "light",
               "what_if": "light_rain", "temperature_c": 24.2, "is_day": False, "weather_code": 61, "text": "Light rain",
               "location": {"name": "Khajaguda X Roads (corridor midpoint by distance)"}, "cached": False, "age_s": 0,
               "rain_effect": {"what_if": "light_rain", "trip_time_pct": 4.0, "trip_time_pct_ci95": [0.5, 6.9], "label": "estimated"},
               "source": "Open-Meteo forecast API (test)", "label": "modelled (Open-Meteo forecast), not a rain gauge"}


def wx_day(day, hour=None):
    """GET /weather as backend/app/weather.py answers it (July 2026 hourly CSV)."""
    return WX.get_weather(day=day, hour=hour)


FLY_J07 = [{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2, "length_m": 600}}]
NC_BUCKET = "2026-10-10T01:40+05:30"


def live_trip_body(stale=False):
    """GET /corridor/live_trip as backend/app/live_trip.py answers it: the trip vs July same hour and 12 legs with live flow."""
    kmh = [34, 38, 38, 38, 30, 36, 40, 22, 12, 28, 30, 26]
    legs = [{"from_id": a, "to_id": z, "from_name": PTS[a]["name"], "to_name": PTS[z]["name"], "distance_m": 1800, "time_s": round(1800 / k * 3.6),
             "speed_kmh": k, "confidence": 1.0, "basis": "live flow", "label": "estimated",
             "flow": {"current_speed_kmh": k, "free_flow_speed_kmh": 40, "confidence": 1.0, "label": "measured (TomTom live flow)"}}
            for (a, z), k in zip(zip(ORDER, ORDER[1:]), kmh)]
    return {"corridor_id": "lingampally_lakdikapul", "as_of": "2026-10-10T01:49:25+05:30", "time_label": "01:49 IST", "hour": 1, "stale": stale, "age_s": 1200 if stale else 30,
            "trip": {"total_s": 2020, "total_min": 33.7, "label": "estimated", "confidence": 1.0, "confidence_label": "high",
                     "july_same_hour_total_s": 2334, "july_same_hour_min": 38.9, "delta_s": -314}, "legs": legs, "warnings": []}


def nowcast_result(ivs, run_id):
    """A now-cast result (POST /corridor/runs day "live"): time.label / bucket, inputs.live_trip, journey vs the live estimate."""
    r = json.loads(json.dumps(SAMPLE["flyover_j07" if ivs else "baseline"]))
    r.pop("sample", None)
    r.update(run_id=run_id, interventions=ivs, frames_path="test", frames_window={"from_s": 900, "to_s": 1200, "step_s": 4, "sim_minutes_total": 54})
    r["time"] = {"label": "Now-cast 01:49 IST (TomTom live; July 06:00 calibration adjusted; 01:00 is outside the calibrated 06-23, nearest hour used)",
                 "day": "live", "hour": 6, "as_of": "2026-10-10T01:49:25+05:30", "bucket": NC_BUCKET}
    r["inputs"] = {"counts_source": "test", "label": "estimated", "volume_scale": 1.0,
                   "live_trip": {"as_of": "2026-10-10T01:49:25+05:30", "bucket": NC_BUCKET, "total_s": 2020, "hour": 6, "now_hour": 1, "hour_clamped": True, "stale": False}}
    r["journey"]["total_s"] = 1900 if ivs else 2050
    r["journey"]["tomtom_total_s"] = 2020
    return r
WATERLOG = {"label": "reported in public sources, not measured by us", "what_this_is": "Spots news reports name as water-logged in rain (test).",
            "by_what_if": {"light_rain": ["Lakdikapul", "Shaikpet", "Tolichowki"],
                           "heavy_rain": ["Gachibowli", "Biodiversity jn", "Shaikpet", "Tolichowki", "Nanal Nagar", "Masab Tank", "Lakdikapul"]},
            "points": [{"junction_id": "j03", "short": "Gachibowli", "severity": "medium", "what_reported": "test", "sources": []},
                       {"junction_id": "j04", "short": "Biodiversity jn", "severity": "medium", "what_reported": "test", "sources": []},
                       {"junction_id": "j06", "short": "Shaikpet", "severity": "high", "lat": 17.4135, "lon": 78.3950, "spot": "Shaikpet Nala", "what_reported": "test", "sources": []},
                       {"junction_id": "j07", "short": "Tolichowki", "severity": "high", "spot": "Galaxy Theatre", "what_reported": "test", "sources": []},
                       {"junction_id": "j08", "short": "Nanal Nagar", "severity": "medium", "what_reported": "test", "sources": []},
                       {"junction_id": "j11", "short": "Masab Tank", "severity": "medium", "what_reported": "test", "sources": []},
                       {"junction_id": "B_lakdikapul", "short": "Lakdikapul", "severity": "high", "what_reported": "test", "sources": []}]}


def wl_run(run_id, minutes, q07, ivs):
    """A C2 result taking `minutes` (legs scaled), the Tolichowki queue q07 m, with the given changes (water-logging case)."""
    r = json.loads(json.dumps(SAMPLE["baseline"]))
    r.pop("sample", None)
    k = minutes * 60 / r["journey"]["total_s"]
    for leg in r["journey"]["legs"]:
        leg["time_s"] = round(leg["time_s"] * k, 1)
    r["journey"]["total_s"] = round(minutes * 60, 1)
    r["journey"]["tomtom_total_s"] = 3373
    for j in r["junctions"]:
        if j["id"] == "j07":
            j["max_queue_m"] = q07
    r.update(run_id=run_id, interventions=ivs, frames_path="test", frames_window={"from_s": 900, "to_s": 1200, "step_s": 4, "sim_minutes_total": 54},
             inputs={"counts_source": "test", "label": "estimated", "volume_scale": 1.0})
    return r


CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}
STREAM_JS = """(() => {
  const FRAMES = %s, Real = window.WebSocket;
  class FakeStream {
    constructor(url) {
      if (!url.includes('/stream/')) return new Real(url);
      this.url = url; window.__streams = (window.__streams || []).concat(url);
      setTimeout(() => { FRAMES.forEach(f => this.onmessage && this.onmessage({ data: JSON.stringify(f) })); this.onclose && this.onclose({}); }, 50);
    }
    close() {}
  }
  window.WebSocket = FakeStream;
  window.LIVE_REFRESH_MS = %d;
  const realFetch = window.fetch;   // long runs: hold POST /corridor/runs for window.__delayRuns ms
  window.fetch = async (u, o) => { if (window.__delayRuns && String(u).includes('/corridor/runs')) await new Promise(r => setTimeout(r, window.__delayRuns)); return realFetch(u, o); };
})();"""


def mock_api(pg, live_body, bodies, mode, counts, real_shape=False, geometry=False, probes=False, weather=False, live_now=False):
    """Corridor endpoints answered in the browser: GET /corridor (route + TomTom legs), live junctions (and their approach
    shapes), calibration, runs (frames_window; another recorded window; `hour` 422 unless mode["hour_ok"]; `weather` echoed),
    roads, probes; GET /weather, /weather/factors (backend/app/weather.py on the repo's files) and /weather/now
    (mode["wx_now"], else 503). weather=True: GET /corridor lists sim.weather (and sim.hours), so the page offers the what-if."""
    def corridor_runs(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        body = json.loads(route.request.post_data or "{}")
        if "hour" in body:   # the page asks once whether the API takes `day` + `hour`
            counts["hour"] = counts.get("hour", 0) + 1
            if not mode.get("hour_ok"):
                return route.fulfill(status=422, headers=CORS, content_type="application/json", body=json.dumps({"detail": "hourly data not available yet"}))
        bodies.append(body)
        if mode["fail"] == "plain":
            return route.fulfill(status=500, headers=CORS, body="simulation failed: test")
        if mode["fail"] == "json":
            return route.fulfill(status=500, headers=CORS, content_type="application/json", body=json.dumps({"detail": "netconvert failed at j08: test"}))
        r = json.loads(json.dumps(SAMPLE["flyover_j07" if body.get("interventions") else "baseline"]))
        r.pop("sample", None)
        r["run_id"] = "r_test_" + r["variant_id"]
        r["interventions"] = body.get("interventions", [])
        dup = [iv for iv in r["interventions"] if iv["junction_id"] == "j06" and iv["kind"] in ("flyover", "underpass")]
        if dup:   # as sim/templates/corridor.py answers at a junction the main road already crosses on a flyover
            r = dict(json.loads(json.dumps(SAMPLE["baseline"])), run_id="r_test_dup", variant_id="dup", interventions=r["interventions"])
            r.pop("sample", None)
            r["warnings"] = [f"j06 {dup[0]['kind']}: j06 already has a flyover: the corridor crosses Narne Rd jn Shaikpet on the Shaikpet Flyover; nothing built"]
        r["frames_path"] = "test"
        r["inputs"] = {"counts_source": "test", "label": "estimated", "volume_scale": 1.0}
        m = body.get("frames_from_min", 15)   # the recorded 5 minutes (frames t count from 0 here: the page adds from_s)
        r["frames_window"] = {"from_s": m * 60, "to_s": m * 60 + 300, "step_s": 4, "sim_minutes_total": 54}
        if "frames_from_min" in body:
            r["run_id"] += f"_w{m}"
        r["journey"]["tomtom_total_s"] = 3373   # TomTom's July speeds over the simulated route (56 min)
        if "hour" in body:   # the simulated day and hour, echoed
            r["time"] = dict(r["time"], day=body.get("day"), hour=body["hour"])
            r["run_id"] += f"_{body.get('day')}_{body['hour']}"
        if "weather" in body:   # the rain what-if, echoed as corridor_runner does (slower legs; the estimate vs dry)
            w = body["weather"]
            for leg in r["journey"]["legs"]:
                leg["time_s"] = round(leg["time_s"] * WX_TRIP[w], 1)
            r["journey"]["total_s"] = round(r["journey"]["total_s"] * WX_TRIP[w], 1)
            r["time"] = dict(r["time"], weather=w)
            r["inputs"]["weather"] = {"weather": w, "label": "estimated (rain factors from TomTom hourly x Open-Meteo, July 2026)",
                                      "expected_trip_time_factor_vs_dry": WX_TRIP[w], "expected_trip_time_factor_vs_dry_ci95": WX_CI[w]}
            r["run_id"] += f"_{w}"
        route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(r))

    def live(route):
        counts["live"] = counts.get("live", 0) + 1
        route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(live_body(counts)))

    if real_shape:   # as the backend sends it: tomtom.periods[].legs, route with whole-route and per-leg features
        per = [{"period": pp, "label": pp, "legs": [{k: v for k, v in x.items() if k != "period"} for x in API_LEGS if x["period"] == pp]} for pp in API_PERIODS]
        rt = route_geojson()["features"][1]["geometry"]["coordinates"]
        feats = [{"type": "Feature", "properties": {"kind": "route", "direction": "A->B"}, "geometry": {"type": "LineString", "coordinates": rt}}]
        feats += [{"type": "Feature", "properties": {"kind": "leg", "direction": "A->B", "from_id": a, "to_id": z}, "geometry": {"type": "LineString", "coordinates": rt[k * 12:k * 12 + 13]}}
                  for k, (a, z) in enumerate(zip(ORDER, ORDER[1:]))]
        corridor = dict(CORRIDOR, tomtom={"source": "test", "periods": per, "hourly": hourly_body()}, route={"type": "FeatureCollection", "features": feats})
    else:            # other shapes the page also accepts: legs rows with a period, one bendy line per direction (cut by the page)
        corridor = dict(CORRIDOR, legs=API_LEGS, route=route_geojson())
    if weather:      # GET /corridor sim: hours and the rain what-if settings (backend/app/corridor.py sim_capabilities)
        corridor["sim"] = {"hours": list(range(6, 24)), "frames_window": True, "probes": True, "weather": ["dry", "light_rain", "heavy_rain"],
                           "weather_label": "estimated (rain factors from TomTom hourly x Open-Meteo, July 2026)"}

    if live_now:     # GET /corridor sim.live: the live trip and Simulate now (backend/app/corridor.py sim_capabilities)
        corridor.setdefault("sim", {})["live"] = {"available": True, "refresh_s": 300, "bucket_s": 600, "endpoint": "GET /corridor/live_trip", "run": {"day": "live"}}

    def wx(route):
        u = urlparse(route.request.url)
        counts.setdefault("wx", []).append(u.path + ("?" + u.query if u.query else ""))
        if u.path == "/weather/now":
            now = mode.get("wx_now")
            return route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(now)) if now else \
                route.fulfill(status=503, content_type="application/json", headers=CORS, body=json.dumps({"detail": "current weather unavailable (test)"}))
        if u.path == "/weather/factors":
            return route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(WX.weather_factors()))
        q = parse_qs(u.query)
        h = q.get("hour", [None])[0]
        route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(wx_day(q.get("day", ["july"])[0], None if h is None else int(h))))
    pg.route("http://localhost:8000/weather**", wx)
    pg.route("http://localhost:8000/corridor/runs", corridor_runs)
    pg.route("http://localhost:8000/corridor/junctions/live", live)
    pg.route("http://localhost:8000/corridor", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(corridor)))
    pg.route("http://localhost:8000/runs/*/roads", lambda r: r.fulfill(status=404, headers=CORS, body="no roads"))
    pg.route("http://localhost:8000/corridor/calibration", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(CALIBRATION)))
    pg.route("http://localhost:8000/corridor/junctions/geometry", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(geometry_body()))
             if geometry else r.fulfill(status=404, headers=CORS, body="not here"))
    pg.route("http://localhost:8000/runs/*/probes", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(probe_tracks()))
             if probes else r.fulfill(status=404, headers=CORS, body="not here"))

    def bld(route):
        pid = route.request.url.rsplit("/", 1)[-1]
        counts.setdefault("bld", []).append(pid)
        if pid == "j07":
            return route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(building_fc()))
        route.fulfill(status=404, headers=CORS, body="no buildings")
    pg.route("http://localhost:8000/corridor/buildings/*", bld)
    # the page falls back to the static files in data/corridor/buildings/; keep the mock the only source
    pg.route("**/data/corridor/buildings/*.geojson", lambda r: r.fulfill(status=404, headers=CORS, body="no buildings"))


def open_page(b, viewport, init_js):
    pg = b.new_page(viewport=viewport)
    pg.on("pageerror", lambda e: errors.append(f"[{case}] {e}"))
    if init_js:
        pg.add_init_script(init_js)
    return pg


def goto(pg, wait=2500):
    pg.goto(URL, wait_until="load", timeout=60000)
    pg.wait_for_function("() => typeof overlay !== 'undefined' && overlay && document.querySelectorAll('.pin').length > 0", timeout=30000)
    pg.wait_for_timeout(wait)


def traffic_vis(pg):
    return pg.evaluate("() => map.getLayer('tomtom-traffic') ? map.getLayoutProperty('tomtom-traffic', 'visibility') : null")


def badges(pg):
    return pg.eval_on_selector_all(".pin[data-badge]", "els => els.map(e => [e.textContent, e.dataset.badge, e.dataset.sev, getComputedStyle(e, '::after').content, getComputedStyle(e, '::after').backgroundColor])")


def set_tl(pg, sec):
    """Move the one timeline to `sec` seconds into the simulated period and let go."""
    pg.evaluate(f"() => {{ const s = document.getElementById('scrub'); s.value = {sec}; s.dispatchEvent(new Event('input')); s.dispatchEvent(new Event('change')); }}")


def set_win(pg, m):
    set_tl(pg, m * 60 + 10)


def settle(pg, ms=6000):
    """Wait for the camera to stop (a busy machine renders flights slowly)."""
    try:
        pg.wait_for_function("() => !map.isMoving()", timeout=ms)
    except Exception:
        pass
    pg.wait_for_timeout(200)


def api_status(path):
    try:
        return urllib.request.urlopen("http://localhost:8000" + path, timeout=3).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])

    # ---------------- the page against whatever API is running (corridor endpoints may 404: sample fallback) ----------------
    pg = open_page(b, {"width": 1500, "height": 950}, None)
    pg.route("http://localhost:8000/corridor/runs", lambda r: r.fulfill(status=404, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type"}, body="not here"))
    goto(pg, 4000)

    case = "A load"; print(case)
    st = pg.inner_text("#status")
    check("API" in st and "error" not in st.lower(), f"status: {st}")
    pins = pg.eval_on_selector_all(".pin.maplibregl-marker", "els => els.map(e => e.textContent)")
    check(pins == ["A"] + [str(i) for i in range(1, 12)] + ["B"], f"13 markers: {pins}")
    gone = [x for x in GONE if pg.locator(x).count()]
    check(not gone, f"day, hour, modes, rain strip, weather chip and the Live now link are gone (still there: {gone})")
    check(pg.inner_text("#hdr-title").strip() == "Lingampally → Lakdikapul" and "22.4 km commute through 11 junctions" in pg.inner_text("#hdr-sub")
          and pg.locator("#hdr-sub a").count() >= 1, f"header card: {pg.inner_text('#hdr-title')!r} / {pg.inner_text('#hdr-sub')!r}")
    mb, mp = pg.evaluate("() => [document.getElementById('modebar').getBoundingClientRect().toJSON(), document.getElementById('left').getBoundingClientRect().toJSON()]")
    check(pg.eval_on_selector("#modebar", "e => e.classList.contains('panel')") and mb["top"] < 70 and mb["left"] < 40 and mb["bottom"] <= mp["top"],
          f"header card top-left, above the controls ({mb['top']:.0f}-{mb['bottom']:.0f} px, panel from {mp['top']:.0f})")
    s = strips(pg)
    check(len(s) == 1 and s[0][0] == "tomtom" and s[0][1] == 12, f"measured strip with 12 legs before any run: {s}")
    check(s and s[0][3].startswith("Real data · typical day") and "REAL" in s[0][3] and s[0][2] == "58.2 min", f"measured strip 'Real data · typical day', REAL, 58.2 min: {s[0][2:] if s else s}")
    check(pg.locator("#strips .ticks span").count() == 13, f"junction ticks (A, 1..11, B) under the real-data bar: {pg.locator('#strips .ticks span').count()}")
    check(pg.evaluate("() => !!document.querySelector('#map canvas')"), "map canvas present")
    check(layer(pg, "route") == 12, f"route drawn as 12 legs: {layer(pg, 'route')}")
    rw = layer_props(pg, "route", "l => [l.props.widthMinPixels || 0, typeof l.props.getWidth === 'number' ? l.props.getWidth : null, l.props.visible !== false, l.props.opacity]")
    check(rw and rw[2] and (rw[0] >= 4 or (rw[1] or 0) >= 8), f"route drawn wide and visible by default (widthMinPixels, getWidth, visible, opacity): {rw}")
    rs = pg.inner_text("#route-src")
    check(rs.startswith("Route coloured by real data, typical day (REAL speeds)") and [round(k, 1) for _, k in route_data(pg)] == TYPICAL_KMH, f"route coloured by real speed: {rs!r}")
    z = pg.evaluate("() => map.getZoom()")
    check(10.5 < z < 13.5, f"map framed on the whole corridor (zoom {z:.1f})")
    pre = pg.eval_on_selector_all("#presets button", "els => els.map(e => [e.id, e.textContent.replace('▶', ''), e.title])")
    check([x[:2] for x in pre] == [["p-nallagandla", "Flyover at Nallagandla"], ["p-dlf", "Flyover at ISB Rd / DLF"],
                                   ["p-nanal", "One flyover over Nanal Nagar + Rethibowli"], ["p-dlf-retime", "Give DLF's side roads more green (watch the ripple)"]],
          f"4 quick demo buttons: {[x[1] for x in pre]}")
    check(all(len(x[2]) > 40 and "Replaces your list of changes" in x[2] for x in pre) and "420 m" in pre[2][2] and "70%" in pre[3][2], "each demo explained in a tooltip")
    check(pg.evaluate("() => Object.keys(PRESETS).length === 4 && !document.getElementById('p-tolichowki') && !document.getElementById('p-khajaguda')"), "Tolichowki and Khajaguda demos gone")
    heads = pg.eval_on_selector_all("#left h2", "els => els.map(e => e.textContent.trim().toLowerCase())")
    order = [next((i for i, h in enumerate(heads) if h.startswith(w)), -1) for w in ("quick actions", "simulated", "junctions", "decision")]
    check(all(i >= 0 for i in order) and order == sorted(order), f"controls in order: Quick actions, Simulated, Junctions, Decision: {heads}")
    check(pg.inner_text("#sim-today").strip() == "Start engine" and pg.inner_text("#sim-changes").strip() == "Run with changes",
          f"run buttons 'Start engine' / 'Run with changes': {pg.inner_text('#sim-today')!r} / {pg.inner_text('#sim-changes')!r}")
    w = pg.eval_on_selector("#weather", "e => [e.type, e.min, e.max, e.step, e.value]")
    ticks = pg.eval_on_selector_all("#weather-ticks span", "els => els.map(e => e.textContent.trim())")
    check(w == ["range", "0", "3", "1", "1"] and ticks == ["Dry", "As measured", "Light rain", "Heavy rain"] and pg.locator("#weather-box #weather").count() == 1,
          f"weather slider Dry / As measured / Light rain / Heavy rain, As measured by default: {w} {ticks}")
    # junctions where the main road already runs on a flyover: marked in the picker, on the map, in the popup
    jopts = dict(pg.eval_on_selector_all("#iv-j option", "els => els.map(e => [e.value, e.textContent])"))
    fly_ids = ["j03", "j04", "j06", "j07", "j10", "j11"]
    check(jopts["j07"] == "7 · Tolichowki (flyover exists)" and all(jopts[j].endswith("(flyover exists)") for j in fly_ids)
          and not any(jopts[j].endswith("(flyover exists)") for j in ("j01", "j02", "j05", "j08", "j09")), f"picker marks the 6 flyover junctions: {list(jopts.values())}")
    check(pg.input_value("#iv-j") == "j02" and pg.is_hidden("#iv-exists"), f"picker starts at a ground signal (ISB Rd / DLF), no note: {pg.input_value('#iv-j')}")
    fly_pins = pg.eval_on_selector_all(".pin.fly", "els => els.map(e => e.textContent)")
    check(fly_pins == ["3", "4", "6", "7", "10", "11"] and "Tolichowki Flyover" in pg.get_attribute(".pin.fly >> nth=3", "title"), f"map pins 3, 4, 6, 7, 10, 11 marked: {fly_pins}")
    check("flyover already built" in pg.inner_text("#right"), "map key explains the mark")
    # layers: live traffic off, queues and delay badges on
    check(not pg.is_checked("#t-traffic") and pg.is_checked("#t-queues") and pg.is_checked("#t-badges") and pg.evaluate("() => document.body.classList.contains('badges-on')")
          and traffic_vis(pg) in (None, "none"), "layers: live traffic off by default, queues and delay badges on")
    check(pg.text_content("#layers-box summary").strip().startswith("Layers") and pg.get_attribute("#layers-box", "open") is not None, "Layers section open")
    # the live junctions panel is always there
    live_st = api_status("/corridor/junctions/live")
    hd = pg.text_content("#live-box h2").strip()
    check(pg.is_visible("#live-box") and hd.startswith("Live junctions") and "Real data · live" in hd and pg.is_visible("#journey") and pg.is_visible("#sim-today"),
          f"live junctions panel always shown next to the simulation: {hd!r}")
    n = pg.eval_on_selector_all("#live .lj", "els => els.length")
    if live_st != 200 or not n:
        check(n == 0 and pg.is_visible("#live-empty") and pg.inner_text("#live-empty").strip(), f"no live data: a note instead ({live_st}): {pg.inner_text('#live-empty')!r}")
    else:
        bs = badges(pg)
        check(len(bs) == n and all(b[3].endswith(' s"') for b in bs) and pg.eval_on_selector_all("#live .lj .hd[aria-expanded=true]", "els => els.length") == 0,
              f"real API: {n} live junctions, collapsed, each pin shows its worst delay now: {[b[:3] for b in bs]}")
    if api_status("/corridor") == 200:
        check("Drawn on the real road" in rs and all(n > 2 for n, _ in route_data(pg)), f"real API: route on the road ({[n for n, _ in route_data(pg)]} vertices)")
    bt = banned_text(pg)
    check(not bt, f"no 'TomTom' or 'July' in the visible text: {bt}")
    pg.screenshot(path=str(OUT / "corridor_A.png"))

    case = "P one screen"; print(case)
    check(pg.evaluate("() => !document.body.classList.contains('mode-live') && !document.body.classList.contains('mode-july')"), "no mode classes on the page")
    pg.goto(URL + "#mode=live", wait_until="load", timeout=60000)
    pg.reload(wait_until="load")   # a hash-only goto does not reload the page
    pg.wait_for_function("() => typeof overlay !== 'undefined' && overlay && document.querySelectorAll('.pin').length > 0", timeout=30000)
    pg.wait_for_timeout(2000)
    vis = [x for x in ("#journey", "#ask-open", "#sim-today", "#sim-changes", "#presets", "#iv-add", "#weather", "#live-box", "#t-vehicles", "#t-roads", "#t-route", "#status") if not pg.is_visible(x)]
    s = strips(pg)
    check(not vis and pg.evaluate("() => !document.body.classList.contains('mode-live')") and s and s[0][0] == "tomtom",
          f"#mode=live is ignored, also after a reload: everything on one screen (hidden: {vis})")
    check(pg.get_attribute("#cr-nav a[data-page=corridor]", "href") == "corridor.html", "the nav link opens the corridor")
    pg.goto(URL, wait_until="load", timeout=60000)
    pg.wait_for_function("() => typeof overlay !== 'undefined' && overlay && document.querySelectorAll('.pin').length > 0", timeout=30000)
    pg.wait_for_timeout(2000)

    case = "C changes"; print(case)
    keys = lambda: pg.eval_on_selector_all("#iv-params [data-k]", "els => els.map(e => e.dataset.k)")
    opts = lambda k: pg.eval_on_selector_all(f"#iv-params select[data-k={k}] option", "els => els.map(e => e.value)")
    chips = lambda: pg.eval_on_selector_all("#iv-kinds [data-kind]", "els => els.map(e => [e.dataset.kind, e.disabled, e.textContent.trim(), e.getAttribute('aria-pressed')])")
    kinds = chips()
    check([k[0] for k in kinds] == ["flyover", "underpass", "signal_retime", "widening", "one_way", "u_turn"] and [k[1] for k in kinds] == [False] * 5 + [True]
          and "(soon)" in kinds[5][2] and pg.is_hidden("#iv-kind"), f"kind chips: flyover, underpass, signal, widening, one-way, U-turn (soon) disabled; the select is hidden: {kinds}")
    check([k[3] for k in kinds] == ["true"] + ["false"] * 5 and pg.input_value("#iv-kind") == "flyover", f"flyover chip pressed by default: {[k[3] for k in kinds]}")
    check(keys() == ["lanes", "length_m"] and opts("lanes") == ["1", "2", "3", "4"] and pg.input_value("#iv-params [data-k=lanes]") == "2",
          f"flyover asks for lanes 1-4 (default 2) and length: {opts('lanes')}")
    check(opts("length_m")[0] == "" and "1200" in opts("length_m"), f"flyover length: auto or 400..2000 m: {opts('length_m')}")
    check("over the junction" in pg.inner_text("#iv-help"), f"flyover help: {pg.inner_text('#iv-help')}")
    pick_kind(pg, "signal_retime")
    check([k[3] for k in chips()] == ["false", "false", "true", "false", "false", "false"] and pg.input_value("#iv-kind") == "signal_retime",
          f"clicking a chip presses it (and only it), the hidden select follows: {[k[3] for k in chips()]}")
    check(keys() == ["cycle_s", "corridor_green_share"] and opts("cycle_s") == ["60", "90", "120", "150", "180"] and pg.input_value("#iv-params [data-k=cycle_s]") == "120",
          f"signal timing: cycle 60-180 s (default 120) and main-road share: {keys()}")
    check("50%" in pg.inner_text("#iv-params .share"), f"share slider shows 50%: {pg.inner_text('#iv-params .share')}")
    pg.fill("#iv-params [data-k=corridor_green_share]", "70"); pg.wait_for_timeout(100)
    check("70% of green to the main road, 30% to side roads" in pg.inner_text("#iv-params .share"), f"slider at 70%: {pg.inner_text('#iv-params .share')}")
    pg.click("#iv-kinds [data-kind=u_turn]", force=True); pg.wait_for_timeout(100)
    check(pg.input_value("#iv-kind") == "signal_retime" and chips()[5][3] != "true", "the U-turn chip cannot be picked")
    pick_kind(pg, "widening")
    check(keys() == ["add_lanes", "length_m"] and opts("add_lanes") == ["1", "2"] and pg.input_value("#iv-params [data-k=length_m]") == "300", f"widening: add_lanes 1-2, length 300 m: {keys()}")
    pick_kind(pg, "one_way")
    check(keys() == [] and "closes the smallest side road in one direction" in pg.inner_text("#iv-help").lower(), f"one-way: no choices, note: {pg.inner_text('#iv-help')}")

    # a flyover where the main road already has one: a note before simulating (still allowed)
    pick_kind(pg, "flyover"); pg.select_option("#iv-j", "j07"); pg.wait_for_timeout(100)
    check(pg.is_visible("#iv-exists") and pg.inner_text("#iv-exists") == "The main road already crosses Tolichowki on the Tolichowki Flyover; this would duplicate it.",
          f"duplicate-flyover note: {pg.inner_text('#iv-exists')}")
    pick_kind(pg, "underpass")
    check("would duplicate it" in pg.inner_text("#iv-exists"), "same note for an underpass")
    pick_kind(pg, "signal_retime")
    check("meets no signal here" in pg.inner_text("#iv-exists"), f"signal note at a flyover junction: {pg.inner_text('#iv-exists')}")
    pick_kind(pg, "widening")
    check(pg.is_hidden("#iv-exists"), "no note for widening")
    pick_kind(pg, "flyover"); pg.select_option("#iv-j", "j04"); pg.wait_for_timeout(100)
    check("Bio-Diversity Park Level 1 Flyover" in pg.inner_text("#iv-exists"), f"Biodiversity note: {pg.inner_text('#iv-exists')}")
    pg.select_option("#iv-j", "j05"); pg.wait_for_timeout(100)
    check(pg.is_hidden("#iv-exists"), "no note at a ground signal (Khajaguda)")
    add_iv(pg, "j07", "flyover", {"lanes": 3, "length_m": 400})
    check(pg.is_visible("#iv-exists") and ivs(pg) == ["7 · Tolichowki: Flyover, 3 lanes, 400 m"], "still allowed to add it")
    add_iv(pg, "j03", "signal_retime", {"cycle_s": 150, "corridor_green_share": 70})
    add_iv(pg, "j07", "flyover", {"lanes": 2, "length_m": 600})
    v = ivs(pg)
    check(len(v) == 2 and "3 · Gachibowli Circle: Signal timing, 150 s cycle, 70% green to main road" in v[0] and "2 lanes, 600 m" in v[1],
          f"list in corridor order, j07 updated not duplicated: {v}")
    check(has_pins(pg) == ["3", "7"], "markers 3 and 7 highlighted")
    add_iv(pg, "j05", "widening", {"add_lanes": 2})
    add_iv(pg, "j06", "one_way")
    v = ivs(pg)
    check(any("Road widening, +2 lanes, 300 m" in x for x in v) and any("One-way, smallest side road, inbound only" in x for x in v), f"widening and one-way listed: {v}")
    sent = pg.evaluate("() => interventions.map(i => [i.junction_id, i.kind, i.params])")
    check(["j03", "signal_retime", {"cycle_s": 150, "corridor_green_share": 0.7}] in sent and ["j05", "widening", {"add_lanes": 2, "length_m": 300}] in sent
          and ["j06", "one_way", {}] in sent, f"params as the templates take them: {sent}")
    for name in ("Gachibowli", "Khajaguda", "Shaikpet"):
        pg.locator("#iv-list .iv", has_text=name).locator("button").click(); pg.wait_for_timeout(150)
    check(len(ivs(pg)) == 1 and has_pins(pg) == ["7"], f"removed: {ivs(pg)}")

    # Nanal Nagar + Rethibowli
    pg.select_option("#iv-j", "j07")
    check(pg.is_hidden("#iv-nanal"), "one-flyover button hidden away from Nanal Nagar / Rethibowli")
    add_iv(pg, "j08", "flyover", {"lanes": 3})
    check(pg.is_visible("#iv-nanal") and pg.is_hidden("#iv-merge"), "one flyover alone at Nanal Nagar: no merge yet, button offered")
    add_iv(pg, "j09", "flyover", {"lanes": 3})
    v = ivs(pg)
    sent = pg.evaluate("() => interventions.filter(i => i.junction_id !== 'j07')")
    check(sent == [{"junction_id": "j08", "kind": "flyover", "params": {"lanes": 3, "length_m": 1200}}], f"two flyovers became one at j08, 1200 m: {sent}")
    check(any("Flyover, 3 lanes, 1200 m, over Nanal Nagar + Rethibowli" in x for x in v), f"listed as one flyover over both: {v}")
    check("420 m apart" in pg.inner_text("#iv-merge") and pg.is_visible("#iv-merge"), f"merge note: {pg.inner_text('#iv-merge')}")
    check(has_pins(pg) == ["7", "8", "9"], f"markers 8 and 9 both highlighted: {has_pins(pg)}")
    pg.locator("#iv-list .iv", has_text="Nanal").locator("button").click(); pg.wait_for_timeout(150)
    check(pg.is_hidden("#iv-merge"), "note gone after removing it")
    add_iv(pg, "j09", "underpass")
    pg.click("#iv-nanal"); pg.wait_for_timeout(150)
    sent = pg.evaluate("() => interventions.filter(i => i.junction_id !== 'j07')")
    check(sent == [{"junction_id": "j08", "kind": "flyover", "params": {"lanes": 2, "length_m": 1200}}], f"button replaces the Rethibowli underpass with one flyover: {sent}")
    pg.locator("#iv-list .iv", has_text="Nanal").locator("button").click(); pg.wait_for_timeout(150)
    check(ivs(pg) == ["7 · Tolichowki: Flyover, 2 lanes, 600 m"], f"back to the Tolichowki flyover: {ivs(pg)}")

    case = "D today"; print(case)
    simulate(pg, "#sim-today", "today's roads")
    s = strips(pg)
    check([x[0] for x in s] == ["tomtom"] and s[0][1] == 12 and s[0][3].startswith("Real data · typical day"), f"Start engine adds no bar: the real-data bar only: {[(x[0], x[2]) for x in s]}")
    sample = "SAMPLE DATA" in pg.inner_text("#journey")
    print("      (results are", "sample data)" if sample else "from the API)")
    if sample:
        check("SAMPLE DATA" in pg.inner_text("#src") and "SAMPLE DATA" in pg.inner_text("#journey-tags"), "sample tag in the header and on the trip panel")
    st_ = pg.inner_text("#deltas #sim-today.headline") if pg.locator("#deltas #sim-today.headline").count() else ""
    m_ = re.match(r"Simulated today: (\d+\.\d) min \(real data (\d+\.\d)\)", st_)
    check(m_ and "SIMULATED" in st_ and (not sample or m_.group(1) == BASE_MIN), f"the trip panel says today's simulation vs real data: {st_!r}")
    check(pg.locator("#deltas small").count() >= 1, f"with a hint to run a change: {pg.inner_text('#deltas')[-100:]!r}")
    check(pg.eval_on_selector_all("#jt tr.j", "els => els.length") == 11, "junction table: 11 rows")
    check("traffic input" in pg.inner_text("#run-note"), f"input label shown: {pg.inner_text('#run-note')[:90]}")
    check(pg.is_hidden("#busy"), "no waiting note once done")
    pg.wait_for_timeout(800)
    check(pg.inner_text("#playinfo") != "", f"playback note: {pg.inner_text('#playinfo')}")

    case = "E changes"; print(case)
    simulate(pg, "#sim-changes", "with 1 change")
    s = strips(pg)
    check([x[0] for x in s] == ["tomtom", "changed"] and s[1][1] == 12, f"second bar for the changed trip: {[(x[0], x[2]) for x in s]}")
    check(s[1][3].startswith("Simulated with your changes") and "SIMULATED" in s[1][3] and re.fullmatch(r"\d+\.\d min", s[1][2]), f"with-changes bar: {s[1][2:]!r}")
    head = pg.inner_text("#deltas .headline")
    check(re.match(r"With your changes: \d+\.\d min · [−+±]\d+\.\d min vs the simulation of today's roads \(\d+\.\d\)", head) and "· with flyover" in head.lower(),
          f"total delta vs today's simulation: {head[:160]!r}")
    chips = pg.eval_on_selector_all("#deltas .delta", "els => els.map(e => [e.className, e.textContent])")
    print("     ", chips)
    check(len(chips) >= 1 and all(("up" in c) == ("+" in t) for c, t in chips), "per-leg deltas coloured: red slower, green faster")
    if sample:
        check(f"−3.7 min vs the simulation of today's roads ({BASE_MIN})" in head, f"sample: −3.7 min vs today's {BASE_MIN} min")
        check(any("Narne Rd jn Shaikpet → Tolichowki −7.6 min" in t for _, t in chips), "sample: approach to Tolichowki −7.6 min")
        check(any("Tolichowki → Nanal Nagar jn +4.0 min" in t and "knock-on" in t for _, t in chips), "sample: Tolichowki → Nanal Nagar +4.0 min, knock-on")
        check("flyover lanes land" in pg.inner_text("#warnings"), "warning in the red box")
        row = pg.inner_text("#jt tr[data-id=j08]")
        check("85 → 120 s" in row and pg.eval_on_selector("#jt tr[data-id=j08] .d", "e => e.classList.contains('bad')"), f"Nanal Nagar delay worse, red: {row!r}")
        check(pg.eval_on_selector("#jt tr[data-id=j07] .d", "e => e.classList.contains('ok')"), "Tolichowki delay better, green")
    check(pg.eval_on_selector_all("#strips [data-strip=changed] .leg.changed", "els => els.length") >= 1, "changed legs outlined on the strip")
    pg.screenshot(path=str(OUT / "corridor_E.png"))
    add_iv(pg, "j03", "underpass")
    check("edited after this run" in pg.inner_text("#deltas"), "editing the list marks the result as out of date")
    pg.locator("#iv-list .iv", has_text="Gachibowli").locator("button").click(); pg.wait_for_timeout(200)
    check("edited after this run" not in pg.inner_text("#deltas"), "back to the simulated list: note gone")

    case = "F camera"; print(case)
    pg.click("#jt tr[data-id=j08]"); pg.wait_for_timeout(2200)
    ok, c = center_near(pg, "j08")
    check(ok and pg.evaluate("() => map.getZoom()") > 15, f"table row flies to Nanal Nagar (off by {c['lng']:.0f}, {c['lat']:.0f} px)")
    check(pg.input_value("#iv-j") == "j08" and pg.eval_on_selector_all(".pin.sel", "els => els.map(e => e.textContent)") == ["8"], "junction selected in step 2 and on the map")
    check("Nanal Nagar" in pg.inner_text(".maplibregl-popup") and "Flyover exists" not in pg.inner_text(".maplibregl-popup"), f"popup: {pg.inner_text('.maplibregl-popup')[:80]}")
    pg.click("#jt tr[data-id=j06]"); pg.wait_for_timeout(600)
    check("Flyover exists: the main road crosses on the Shaikpet Flyover" in pg.inner_text(".maplibregl-popup") and pg.input_value("#iv-j") == "j06"
          and "(flyover exists)" in pg.inner_text("#jt tr[data-id=j06]"), f"popup and table mark the existing flyover: {pg.inner_text('.maplibregl-popup')[:120]!r}")
    pg.click("#overview"); pg.wait_for_timeout(1600)
    pg.locator(".pin", has_text="3").first.click(); pg.wait_for_timeout(2200)
    ok, c = center_near(pg, "j03")
    check(ok, f"marker 3 flies to Gachibowli (off by {c['lng']:.0f}, {c['lat']:.0f} px)")
    pg.screenshot(path=str(OUT / "corridor_F.png"))
    pg.click("#strips [data-strip=tomtom] .leg[data-leg='6']"); pg.wait_for_timeout(1800)
    settle(pg)
    c = pg.evaluate("() => map.getCenter()")
    mid = ((PTS["j06"]["lon"] + PTS["j07"]["lon"]) / 2, (PTS["j06"]["lat"] + PTS["j07"]["lat"]) / 2)
    check(abs(c["lng"] - mid[0]) < 0.02 and abs(c["lat"] - mid[1]) < 0.02, f"strip block 6 shows Shaikpet → Tolichowki ({c['lng']:.4f}, {c['lat']:.4f})")
    pg.click("#overview"); pg.wait_for_timeout(1600)
    settle(pg)
    check(pg.evaluate("() => map.getZoom()") < 13.5, "Whole corridor returns to the overview")

    case = "G layers"; print(case)
    pg.uncheck("#t-route"); pg.wait_for_timeout(200); off = layer(pg, "route")
    pg.check("#t-route"); pg.wait_for_timeout(200); on = layer(pg, "route")
    check(off == -1 and on == 12, f"route off/on: {off} / {on}")
    tl = pg.evaluate("() => document.getElementById('t-traffic').closest('label')?.innerText || ''")
    check(pg.is_visible("#t-traffic") and not pg.is_checked("#t-traffic") and traffic_vis(pg) in (None, "none") and "Live traffic" in tl and "TomTom" not in tl,
          f"live traffic offered next to the simulated layers, off by default: {tl!r}")
    if not pg.is_disabled("#t-traffic"):
        pg.check("#t-traffic"); pg.wait_for_timeout(300)
        check(traffic_vis(pg) == "visible" and layer(pg, "route") == 12, "live traffic on, drawn with the simulated route")
        pg.uncheck("#t-traffic"); pg.wait_for_timeout(200)
        check(traffic_vis(pg) == "none", "live traffic off again")
    pg.uncheck("#t-badges"); pg.wait_for_timeout(200)
    off = pg.evaluate("() => document.body.classList.contains('badges-on')")
    pg.check("#t-badges"); pg.wait_for_timeout(200)
    check(off is False and pg.evaluate("() => document.body.classList.contains('badges-on')"), "delay badges off / on")
    pg.close()

    # ---------------- corridor API answering (mocked in the browser): route, live junctions, runs, frames ----------------
    bodies, mode, counts = [], {"fail": None}, {}
    pg = open_page(b, {"width": 1500, "height": 950}, STREAM_JS % (json.dumps(frames_3d()), 2000))
    mock_api(pg, live_nested, bodies, mode, counts, geometry=True, probes=True)
    goto(pg)

    case = "I route"; print(case)
    rd = route_data(pg)
    check(len(rd) == 12 and all(n >= 10 for n, _ in rd), f"12 legs cut along the road geometry (vertices per leg: {[n for n, _ in rd]})")
    rs = pg.inner_text("#route-src")
    check(rs.startswith("Route coloured by real data, typical day (REAL speeds)") and "Drawn on the real road" in rs, f"route note: {rs!r}")
    check([round(k, 1) for _, k in rd] == TYPICAL_KMH, "before a run: legs coloured by real speed (typical day)")
    check(layer(pg, "route-base") == -1, "one route line before any run (no side-by-side line)")
    ends = pg.evaluate("() => { const p = legPaths['j07|j08']; return [p[0], p[p.length - 1]]; }")
    check(all(abs(ends[0][i] - [PTS["j07"]["lon"], PTS["j07"]["lat"]][i]) < 1e-4 and abs(ends[1][i] - [PTS["j08"]["lon"], PTS["j08"]["lat"]][i]) < 1e-4 for i in (0, 1)),
          f"leg 7 → 8 starts at Tolichowki and ends at Nanal Nagar: {ends}")
    s = strips(pg)
    check(s and s[0][2] == "58.2 min" and s[0][3].startswith("Real data · typical day"), f"measured legs of the typical day from GET /corridor: {s[0][2:] if s else s}")

    case = "J live"; print(case)
    hd = pg.text_content("#live-box h2").strip()
    check(pg.is_visible("#live-box") and hd.startswith("Live junctions") and "Real data · live" in hd and pg.is_hidden("#live-empty"),
          f"live panel shown next to the simulation, tagged Real data · live: {hd!r}")
    lj = lambda: pg.eval_on_selector_all("#live .lj", """els => els.map(e => { const h = e.querySelector('.hd'), s = e.querySelector('.sev'), b = e.querySelector('.lj-body');
        return [e.dataset.id, e.querySelectorAll('tr.ap').length, h ? h.innerText : '', h ? h.getAttribute('aria-expanded') : null, s ? s.className : '', s ? s.textContent.trim() : '',
                b ? !!(b.hidden || b.offsetParent === null) : null, h ? h.tagName : '']; })""")
    cards = lj()
    check([c[0] for c in cards] == ["j07", "j08", "j09"] and all(c[1] == 3 for c in cards), f"3 live junctions, worst 3 approaches each: {[(c[0], c[1]) for c in cards]}")
    check(all(c[7] == "BUTTON" and c[3] == "false" and c[6] is True for c in cards), f"an accordion, every junction collapsed at first: {[(c[0], c[3], c[6], c[7]) for c in cards]}")
    check([c[2].split("\n")[0].strip() for c in cards][:1] and "7 · Tolichowki" in cards[0][2] and "8 · Nanal Nagar" in cards[1][2] and "9 · Rethibowli" in cards[2][2],
          f"each row: number · name: {[c[2][:40] for c in cards]}")
    check([(c[5], [k for k in ("ok", "mid", "bad") if k in c[4].split()]) for c in cards] == [("33 s", ["mid"]), ("108 s", ["bad"]), ("178 s", ["bad"])],
          f"worst delay badge per row, coloured vs usual: {[(c[5], c[4]) for c in cards]}")
    check("Live 17:17" in cards[1][2] and "25 min old" in cards[2][2] and "min old" not in cards[1][2], f"live time on each row, old data flagged: {cards[1][2]!r} / {cards[2][2]!r}")
    j8 = live_rows(pg, "j08")
    check([r[0] for r in j8] == ["NH163 N-bound", "Mumbai Rd E-bound", "Inner Ring Rd N-bound"], f"worst first (by delay), short names: {[r[0] for r in j8]}")
    check(j8[0] == ["NH163 N-bound", "108 s", "80 s", "95 s", "149 m"], f"delay now, usual, last hour, queue: {j8[0]}")
    check(live_rows(pg, "j09")[2][-1] == "1.1 km", f"long queues in km: {live_rows(pg, 'j09')}")
    check(pg.eval_on_selector_all("#live .lj[data-id=j08] th", "els => els.map(e => e.textContent)") == ["Worst approaches", "Delay", "Usual", "Last hr", "Queue"], "column heads")
    check(pg.eval_on_selector("#live .lj[data-id=j08] .ap b", "e => e.classList.contains('bad')"), "much worse than usual: red")
    ln = pg.inner_text("#live-note")
    check(ln.startswith("Delay per approach now vs usual, real data · live (queue and volume estimated).") and re.search(r"Updated \d\d:\d\d", ln) and "every 2 s" in ln, f"note: {ln!r}")
    bs = badges(pg)
    check([b[:3] for b in bs] == [["7", "33 s", "mid"], ["8", "108 s", "bad"], ["9", "178 s", "bad"]], f"pins 7, 8, 9 carry their worst delay now, coloured vs usual: {[b[:3] for b in bs]}")
    check(bs and bs[0][3] == '"33 s"' and bs[0][4] == "rgb(245, 136, 50)" and bs[1][4] == "rgb(226, 61, 39)", f"badge drawn on the pin (delay badges on by default): {bs[0][3:] if bs else bs} / {bs[1][3:] if len(bs) > 1 else ''}")
    check("Mehdipatnam Road West Bound" not in pg.get_attribute(".pin[data-id=j08]", "title") and "worst delay 108 s on NH163 North Bound (usually 80 s)" in pg.get_attribute(".pin[data-id=j08]", "title"),
          f"pin tooltip: {pg.get_attribute('.pin[data-id=j08]', 'title')}")
    pg.uncheck("#t-badges"); pg.wait_for_timeout(200)
    check(all(b[3] in ("none", "normal") for b in badges(pg)), "delay badges off: no badge on the pins")
    pg.check("#t-badges"); pg.wait_for_timeout(200)
    check([b[3] for b in badges(pg)] == ['"33 s"', '"108 s"', '"178 s"'], "delay badges on again")
    q = pg.evaluate("() => { const l = overlay._deck.props.layers.find(l => l.id === 'live-queues'); return l ? l.props.data.map(d => [d.jid, d.name, Math.round(d.path.slice(1).reduce((s, p, i) => s + metres(d.path[i], p), 0)), d.path[d.path.length - 1]]) : null; }")
    mq = [x for x in (q or []) if x[0] == "j08" and x[1] == "Mehdipatnam Road West Bound"]
    check(q and len(q) == 11 and mq and abs(mq[0][2] - 751) <= 3, f"11 measured queues drawn on the road (approaches with no queue skipped); Mehdipatnam Rd into Nanal Nagar 751 m: {mq}")
    check(mq and abs(mq[0][3][0] - PTS["j08"]["lon"]) < 1e-6 and abs(mq[0][3][1] - PTS["j08"]["lat"]) < 1e-6, "each queue line ends at its junction")
    check(layer(pg, "live-queues-casing") == 11 and pg.is_hidden("#geo-note"), "white casing under the red queue lines")
    check(layer(pg, "route") == 12, "live queues drawn together with the route (no mode switch)")
    pg.uncheck("#t-queues"); pg.wait_for_timeout(200)
    check(layer(pg, "live-queues") == -1, "queues layer toggles off")
    pg.check("#t-queues"); pg.wait_for_timeout(200)
    n_live = counts.get("live", 0); counts["v2"] = True
    pg.wait_for_timeout(2600)
    check(counts.get("live", 0) > n_live and live_rows(pg, "j08")[0][1] == "131 s", f"refreshed ({counts.get('live')} calls): new NH163 delay shown")
    # the accordion: open one (fly there, popup), the others close; open it again: closed, camera back
    cam0 = pg.evaluate("() => [map.getZoom(), map.getCenter().lng, map.getCenter().lat]")
    pg.click("#live .lj[data-id=j09] .hd"); pg.wait_for_timeout(2200)
    cards = lj()
    pop = pg.inner_text(".maplibregl-popup") if pg.locator(".maplibregl-popup").count() else ""
    check([c[3] for c in cards] == ["false", "false", "true"] and cards[2][6] is False and pg.is_visible("#live .lj[data-id=j09] tr.ap >> nth=0"),
          f"clicking a junction expands it: {[(c[0], c[3], c[6]) for c in cards]}")
    check(center_near(pg, "j09")[0] and "Real data · live: 178 s delay (usual 131 s)" in pop and "REAL" in pop and "SIMULATED" not in pop, f"flies to Rethibowli, popup: {pop[:140]!r}")
    bt = banned_text(pg)
    check(not bt, f"no 'TomTom' or 'July' with a live junction open: {bt}")
    pg.screenshot(path=str(OUT / "corridor_J.png"))
    pg.click("#live .lj[data-id=j09] .hd"); pg.wait_for_timeout(2200)
    cam1 = pg.evaluate("() => [map.getZoom(), map.getCenter().lng, map.getCenter().lat]")
    check([c[3] for c in lj()] == ["false", "false", "false"] and abs(cam1[0] - cam0[0]) < 0.1 and abs(cam1[1] - cam0[1]) < 2e-3 and abs(cam1[2] - cam0[2]) < 2e-3,
          f"clicking it again collapses it and flies back to the camera from before: {[round(x, 4) for x in cam1]} vs {[round(x, 4) for x in cam0]}")
    pg.click("#live .lj[data-id=j08] .hd"); pg.wait_for_timeout(1200)
    pg.click("#live .lj[data-id=j07] .hd"); pg.wait_for_timeout(1500)
    cards = lj()
    check([c[3] for c in cards] == ["true", "false", "false"] and cards[1][6] is True and center_near(pg, "j07")[0], f"opening another closes the first: {[(c[0], c[3]) for c in cards]}")
    pg.click("#live .lj[data-id=j07] .hd"); pg.wait_for_timeout(1500)
    pg.click("#overview"); pg.wait_for_timeout(1300)

    case = "H api + playback"; print(case)
    add_iv(pg, "j07", "flyover", {"lanes": 2, "length_m": 600})
    simulate(pg, "#sim-changes", "with 1 change")
    check(len(bodies) == 2 and {json.dumps(x["interventions"]) for x in bodies} == {"[]", json.dumps([{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2, "length_m": 600}}])},
          f"POST /corridor/runs bodies (today + with changes): {bodies}")
    check(all(set(x) == {"interventions", "volume_scale"} and x["volume_scale"] == 1.0 for x in bodies), f"volume_scale 1.0; no window, day, hour or weather sent: {[sorted(x) for x in bodies]}")
    check("SAMPLE DATA" not in pg.inner_text("body"), "no sample tag for API results")
    check([x[0] for x in strips(pg)] == ["tomtom", "changed"], "two bars from API results: real data, with your changes")
    sim_kmh = [l["speed_kmh"] for l in SAMPLE["flyover_j07"]["journey"]["legs"]]
    base_kmh = [l["speed_kmh"] for l in SAMPLE["baseline"]["journey"]["legs"]]
    rs = pg.inner_text("#route-src")
    check([k for _, k in route_data(pg)] == sim_kmh and "(SIMULATED speeds)" in rs, f"after the run: legs coloured by simulated speed (the run with changes): {rs!r}")
    rb = layer_props(pg, "route-base", "l => l.props.data.map(d => d.kmh)")
    check(rb == base_kmh and layer(pg, "route-casing") > 0, f"today's run drawn beside it (route-base), dark casing under both: {rb}, casing {layer(pg, 'route-casing')}")
    check(layer(pg, "live-queues") == 11 and [b[1] for b in badges(pg)] == ["33 s", "131 s", "178 s"] and pg.evaluate("() => document.body.classList.contains('badges-on')"),
          f"live queues and delay badges stay on with the simulated runs: {layer(pg, 'live-queues')} / {[b[1] for b in badges(pg)]}")
    check("traffic input: estimated" in pg.inner_text("#run-note"), f"input label: {pg.inner_text('#run-note')[:80]}")
    case = "S labels"; print(case)
    names = [x[3] for x in strips(pg)]
    check(len(names) == 2 and names[0].startswith("Real data · typical day") and "REAL" in names[0] and names[1].startswith("Simulated with your changes") and "SIMULATED" in names[1],
          f"row labels: {names}")
    check(pg.inner_text("#trip-foot") == FOOT, f"footnote from the result and the calibration: {pg.inner_text('#trip-foot')!r}")
    check(counts.get("hour", 0) == 0 and not any("day" in x or "hour" in x for x in bodies), f"never asks the API for an hour ({counts.get('hour', 0)} probes); no day / hour sent")
    bt = banned_text(pg)
    check(not bt, f"no 'TomTom' or 'July' in the visible text after a simulation: {bt}")

    case = "H api + playback"
    pg.wait_for_timeout(3500)
    try:   # playback starts ~1.5 s after the frames, then the camera flies to the changed junction (1.8 s)
        pg.wait_for_function("() => map.getZoom() > 14 && !map.isMoving()", timeout=8000)
    except Exception:
        pass
    t0 = time.time()
    while layer(pg, "vehicles") <= 0 and time.time() - t0 < 5:
        pg.wait_for_timeout(250)
    v = layer(pg, "vehicles")
    check(v > 0, f"vehicles drawn from WS frames: {v}")
    check(pg.evaluate("() => map.getZoom()") > 14 and center_near(pg, "j07", 80)[0], "camera flew to the changed junction for playback")
    ck = pg.inner_text("#clock")
    check(ck.startswith("Minute 15:") and ck.endswith("of 54 · Simulated typical day") and "frames" in pg.inner_text("#playinfo"),
          f"clock: minute of the simulated period, no clock time: {ck} · {pg.inner_text('#playinfo')}")
    pb = pg.evaluate("() => Object.fromEntries(['pb', 'modebar', 'right', 'ask-open', 'reset-view'].map(id => { const r = document.getElementById(id).getBoundingClientRect(); return [id, [r.left, r.top, r.right, r.bottom]]; }))")
    check(pb["pb"][0] >= pb["modebar"][2] and pb["pb"][2] <= pb["right"][0] and pb["pb"][1] < 80 and pg.locator("#right #play, #right #scrub, #win, #follow-pick, #ride").count() == 0,
          f"playback is a pill at the top of the map, between the header card and the right panel; no Playback section in the layers panel: {pb['pb']}")
    check(abs(pb["ask-open"][2] - pb["reset-view"][2]) < 1 and pb["ask-open"][3] <= pb["reset-view"][1] and pb["reset-view"][1] - pb["ask-open"][3] < 20,
          f"Ask Terascope AI sits just above Reset view, same right edge: {pb['ask-open']} / {pb['reset-view']}")
    pg.screenshot(path=str(OUT / "corridor_H.png"))
    if pg.get_attribute("#play", "aria-label") != "Pause":
        pg.click("#play")
    pg.click("#play"); pg.wait_for_timeout(400)
    c1 = pg.inner_text("#clock"); pg.wait_for_timeout(1200)
    check(pg.get_attribute("#play", "aria-label") == "Play" and c1 == pg.inner_text("#clock"), f"pause holds the clock: {c1}")
    set_tl(pg, 920); pg.wait_for_timeout(300)
    check(abs(pg.evaluate("() => pos") - 20) < 0.6 and pg.inner_text("#clock").startswith("Minute 15:20 of 54") and pg.inner_text("#tl-time") == "15:20 / 54:00",
          f"the timeline inside the recorded minutes scrubs: {pg.inner_text('#clock')} / {pg.inner_text('#tl-time')}")
    check(not pg.is_disabled("#sim-today") and not pg.is_disabled("#iv-add"), "panel usable during playback")

    case = "Q window"; print(case)
    band = pg.evaluate("() => document.getElementById('scrub').style.getPropertyValue('--tl-bg')")
    check(pg.get_attribute("#scrub", "max") == "3240" and "27.78%" in band and "37.04%" in band and "Recorded minutes 15–20" in pg.get_attribute("#scrub", "title"),
          f"one timeline 0..54 min, the recorded minutes 15-20 on its track: {band[:120]!r}")
    totals = [x[2] for x in strips(pg)]
    n0 = len(bodies)
    pg.evaluate("() => { window.__delayRuns = 2500; }")
    set_tl(pg, 30 * 60 + 30); pg.wait_for_timeout(700)
    check(pg.is_visible("#tl-busy") and "Recording minutes 30–35" in pg.inner_text("#tl-busy") and pg.is_disabled("#scrub"), f"outside the recorded minutes: records them, progress inline: {pg.inner_text('#tl-busy')!r}")
    pg.wait_for_timeout(3000)
    pg.evaluate("() => { window.__delayRuns = 0; }")
    check(len(bodies) == n0 + 1 and bodies[-1] == {"interventions": FLY_J07, "volume_scale": 1.0, "frames_from_min": 30, "frames_minutes": 5}, f"the same run asked for minutes 30-35: {bodies[n0:]}")
    pg.wait_for_timeout(1500)
    ck = pg.inner_text("#clock")
    check((ck.startswith("Minute 30:3") or ck.startswith("Minute 30:4")) and pg.is_hidden("#tl-busy") and not pg.is_disabled("#scrub"),
          f"plays on from minute 30:30: {ck}")
    check([x[2] for x in strips(pg)] == totals and layer(pg, "vehicles") > 0, "results unchanged, vehicles of the new window drawn")
    set_win(pg, 15); pg.wait_for_timeout(1800)
    check(len(bodies) == n0 + 1 and pg.inner_text("#clock").startswith("Minute 15:"), f"back to minute 15: no new request ({pg.inner_text('#clock')})")
    set_win(pg, 30); pg.wait_for_timeout(1800)
    check(len(bodies) == n0 + 1 and pg.inner_text("#clock").startswith("Minute 30:"), "minute 30 again: kept from before, no new request")
    set_win(pg, 15); pg.wait_for_timeout(1500)
    case = "H api + playback"
    wt = pg.inner_text("#watch").split()
    check(pg.is_visible("#watch") and wt == ["Watch", "Today", "With", "changes"] and pg.get_attribute("#watch-changed", "aria-selected") == "true", f"Watch: Today | With changes in the pill: {wt}")
    pg.click("#watch-base"); pg.wait_for_timeout(3000)
    check(layer(pg, "vehicles") > 0 and "r_test" not in pg.inner_text("#status") and pg.get_attribute("#watch-base", "aria-selected") == "true", f"watch today's run: {pg.inner_text('#playinfo')}")

    case = "O 3D"; print(case)
    pg.click("#watch-changed"); pg.wait_for_timeout(1000)
    pg.locator(".pin", has_text="7").first.click(); pg.wait_for_timeout(2400)
    check(pg.evaluate("() => map.getZoom()") > 15 and 50 <= pg.evaluate("() => map.getPitch()") <= 62, f"pitched 3D view at the junction (pitch {pg.evaluate('() => map.getPitch()'):.0f})")
    req = counts.get("bld", [])
    check("j07" in req and "A_lingampally" not in req and len(req) <= 5, f"buildings fetched only for points in view: {req}")
    hs = layer_props(pg, "buildings", "l => l.props.data.map(d => d.h)")
    check(hs == [15, 12.8, 9, 30, 30], f"5 building blocks, heights (null -> floors x 3.2, else 9 m): {hs}")
    check("5 buildings around 7" in pg.inner_text("#bld-note"), f"note: {pg.inner_text('#bld-note')}")
    pg.uncheck("#t-buildings"); pg.wait_for_timeout(200); off = layer(pg, "buildings")
    pg.check("#t-buildings"); pg.wait_for_timeout(200)
    check(off == -1 and layer(pg, "buildings") == 5, "buildings layer toggles")
    ids = layer_props(pg, "vehicles", "l => l.props.data.map(v => v.id)")
    check(ids and not any(i.startswith("far") for i in ids) and "fly0" in ids, f"only vehicles in view drawn as 3D boxes ({len(ids or [])} of 54)")
    zs = pg.evaluate("() => { const l = overlay._deck.props.layers.find(l => l.id === 'vehicles'); const v = l.props.data.find(v => v.id === 'fly1'); return [v.z, box(v)[0][2], l.props.extruded]; }")
    check(zs[0] == 6 and zs[1] == 6 and zs[2], f"car on the flyover raised to z 6 m, extruded: {zs}")
    st = layer_props(pg, "structures", "l => l.props.data.map(d => [d.kind, d.junction_id, d.length_m, Math.max(...d.path.map(q => q[2])), d.path[0][2], d.path[d.path.length - 1][2]])")
    check(st and st[0][:2] == ["flyover", "j07"] and abs(st[0][2] - 600) < 25 and st[0][3] == 6 and st[0][4] == 0 and st[0][5] == 0,
          f"flyover drawn in 3D at Tolichowki: 600 m, deck 6 m, ramps to the ground: {st}")
    check(layer(pg, "piers") > 5, f"piers under the deck: {layer(pg, 'piers')}")
    pg.screenshot(path=str(OUT / "corridor_O.png"))
    case = "R follow"; print(case)
    check(pg.evaluate("() => [dirOf({direction: 'A->B'}), dirOf({direction: 'B->A'}), dirOf({id: 'probe_rev_3.1'}), dirOf({id: 'probe_fwd_0.2'})]") == ["fwd", "rev", "rev", "fwd"],
          "the API's A->B / B->A directions read (they were read as 'towards Lakdikapul' both ways)")
    pg.click("#follow"); pg.wait_for_timeout(1200)
    st = pg.evaluate("() => ride && [ride.probe.id, ride.t, ride.inWin]")
    check(st and st[0] == "probe_fwd_1" and 600 <= st[1] < 700 and st[2] is False and pg.input_value("#speed") == "3",
          f"Follow a car: test car fwd-1's whole trip from Lingampally, at the fixed 3x: {st}")
    card = pg.inner_text("#follow-card")
    check(pg.inner_text("#follow") == "Stop following" and pg.inner_text("#fc-title") == "Test car fwd-1 · Lingampally → Lakdikapul" and "Lingampally → Nallagandla Rd jn" in card
          and "min since Lingampally" in card and "of ~55" in card and "km/h" in card and "SIMULATED" in card and "drives alone" in card, f"follow card: {card!r}")
    bar = pg.evaluate("() => { const b = document.querySelector('#follow-card .fbar'); return b ? [b.querySelectorAll('.tick').length, Number(b.getAttribute('aria-valuenow')), b.querySelectorAll('.tick.past').length] : null; }")
    check(bar and bar[0] == 11 and bar[1] <= 3 and bar[2] == 0, f"A -> B progress bar with the 11 junctions, at the start: {bar}")
    check(layer(pg, "vehicles") == -1 and layer(pg, "vehicle-dots") == -1 and layer(pg, "ride-car") == 1 and layer(pg, "follow-halo") == 1, "outside the recorded minutes: the test car alone, highlighted")
    cam = pg.evaluate("() => { const v = probeAt(ride.probe, ride.t), c = map.getCenter(); return [v.lon - c.lng, v.lat - c.lat, map.getPitch()]; }")
    check(abs(cam[0]) < 3e-4 and abs(cam[1]) < 3e-4 and cam[2] > 55, f"camera rides with the car: {cam}")
    pg.evaluate("() => { ride.t = 1000; }"); pg.wait_for_timeout(500)
    ids = layer_props(pg, "vehicles", "l => l.props.data.map(v => v.id)") or []
    card = pg.inner_text("#follow-card")
    check(pg.evaluate("() => ride.inWin") and layer(pg, "vehicles") >= 0 and "probe_fwd_1" not in ids and layer(pg, "ride-car") == 1 and "Other traffic shown" in card,
          f"inside the recorded minutes: other traffic shown ({len(ids)}), the test car drawn once")
    check(pg.inner_text("#clock").startswith("Minute 16:") and pg.evaluate("() => playing"), f"the timeline follows the car: {pg.inner_text('#clock')}")
    pg.click("#follow-dir"); pg.wait_for_timeout(600)
    bar = pg.evaluate("() => Number(document.querySelector('#follow-card .fbar')?.getAttribute('aria-valuenow'))")
    check(pg.evaluate("() => ride && ride.probe.id") == "probe_rev_1" and pg.inner_text("#fc-title") == "Test car rev-1 · Lakdikapul → Lingampally" and "Lakdikapul → Lingampally" in pg.inner_text("#follow-dir")
          and bar <= 3 and "min since Lakdikapul" in pg.inner_text("#follow-card"), f"direction toggle: follows a test car from Lakdikapul ({bar}%)")
    pg.click("#follow-dir"); pg.wait_for_timeout(300)
    pg.evaluate("() => { ride.t = ride.probe.arrive_s - 2; }"); pg.wait_for_timeout(800)
    check(pg.evaluate("() => ride === null") and "arrived at Lakdikapul after 55 min" in pg.inner_text("#playinfo") and pg.inner_text("#follow") == "Follow a car" and pg.is_hidden("#follow-card"),
          f"arrives: {pg.inner_text('#playinfo')!r}")
    pg.click("#follow"); pg.wait_for_timeout(400); pg.click("#follow-stop"); pg.wait_for_timeout(200)
    check(pg.evaluate("() => ride === null && following === null") and pg.is_hidden("#follow-card") and layer(pg, "follow-halo") == -1, "Stop: card and highlight gone")
    # a test car in the recorded frames (the API without whole trips, or clicked): highlighted, trail, card
    pg.evaluate("() => startFollow('probe_fwd_1')"); pg.wait_for_timeout(1000)
    pr = pg.evaluate("() => { const v = vehicleAt('probe_fwd_1'), c = map.getCenter(); return v ? [v.lon, v.lat, c.lng, c.lat, map.getPitch()] : null; }")
    check(pr and abs(pr[0] - pr[2]) < 2e-4 and abs(pr[1] - pr[3]) < 2e-4 and pr[4] > 55, f"camera follows the test car in the frames: {pr}")
    hl = layer_props(pg, "vehicles", "l => { const v = l.props.data.find(v => v.id === 'probe_fwd_1'); return v ? l.props.getFillColor(v) : null; }")
    trail = pg.evaluate("() => { const l = overlay._deck.props.layers.find(l => l.id === 'follow-trail'); return l ? l.props.data[0].path.length : 0; }")
    check(hl == [255, 252, 254] and layer(pg, "follow-halo") == 1 and trail >= 2 and "Following test car fwd-1" in pg.inner_text("#playinfo"), f"followed car highlighted: colour {hl}, halo, trail of {trail} points")
    pg.click("#follow"); pg.wait_for_timeout(200)
    check(pg.inner_text("#follow") == "Follow a car" and pg.is_hidden("#follow-card") and layer(pg, "follow-halo") == -1, "stop following: card and highlight gone")
    # click any vehicle on the map to follow it
    if pg.get_attribute("#play", "aria-label") == "Pause":
        pg.click("#play")
    pg.wait_for_timeout(300)
    pg.evaluate("() => { flyToPoint('j07'); }"); pg.wait_for_timeout(2200)
    pg.evaluate("() => { if (popup) popup.remove(); }")
    hit = pg.evaluate("""() => { const vp = overlay._deck.getViewports()[0], r = map.getCanvas().getBoundingClientRect(), W = r.width, H = r.height;
        const l = overlay._deck.props.layers.find(l => l.id === 'vehicles'); if (!l) return [0, 0, null];
        const cands = l.props.data.map(v => { const [x, y] = vp.project([v.lon, v.lat, (v.z || 0) + 0.8]); return { v, x, y }; })
          .filter(c => c.x > 420 && c.x < W - 300 && c.y > 80 && c.y < H - 280 && document.elementFromPoint(c.x + r.left, c.y + r.top) === map.getCanvas()).sort((a, b) => (b.v.z || 0) - (a.v.z || 0));
        for (const c of cands) { const o = overlay.pickObject({ x: c.x, y: c.y, radius: 2 }); if (o && o.object && o.object.id === c.v.id) return [c.x + r.left, c.y + r.top, c.v.id]; }
        return [0, 0, null]; }""")
    pg.mouse.click(hit[0], hit[1]); pg.wait_for_timeout(700)
    fol = pg.evaluate("() => following")
    card = pg.inner_text("#follow-card") if pg.is_visible("#follow-card") else ""
    check(hit[2] and fol == hit[2], f"clicking a vehicle follows it: picked {hit[2]}, following {fol}")
    if fol and fol.startswith("fly"):
        check(card.startswith("Car " + fol) and "on the Tolichowki Flyover" in card, f"card for an ordinary car on the existing flyover: {card!r}")
    pg.click("#follow"); pg.wait_for_timeout(200)

    case = "O 3D"
    b0 = pg.evaluate("() => map.getBearing()"); pg.click("#orbit"); pg.wait_for_timeout(1200); b1 = pg.evaluate("() => map.getBearing()")
    pg.click("#orbit"); pg.wait_for_timeout(300); b2 = pg.evaluate("() => map.getBearing()"); pg.wait_for_timeout(500)
    check(3 < (b1 - b0) % 360 < 20 and abs(pg.evaluate("() => map.getBearing()") - b2) < 0.5, f"orbit turns the camera slowly and stops: {b0:.1f} → {b1:.1f}")
    if not pg.is_disabled("#t-night"):
        pg.check("#t-night"); pg.wait_for_timeout(800)
        fill = layer_props(pg, "buildings", "l => l.props.getFillColor")
        check(fill == [74, 74, 74], f"night view: darker buildings {fill}")
        pg.screenshot(path=str(OUT / "corridor_O_night.png"))
        pg.uncheck("#t-night"); pg.wait_for_timeout(800)
    pg.click("#overview"); pg.wait_for_timeout(1500)
    try:
        pg.wait_for_function("() => map.getZoom() < 13.5 && !map.isMoving()", timeout=6000)
    except Exception:
        pass
    pg.wait_for_timeout(500)
    dots = layer_props(pg, "vehicle-dots", "l => l.props.data.length")
    cam = pg.evaluate("() => [map.getZoom(), map.isMoving(), following, orbiting, !!ride, playing]")
    check(layer(pg, "vehicles") == -1 and dots == 54, f"whole corridor: every vehicle as a dot ({dots}), no 3D boxes (zoom, moving, following, orbiting, ride, playing: {cam})")
    check(layer(pg, "buildings") == -1, "no buildings drawn from the overview")

    case = "L long runs"; print(case)
    pg.evaluate("() => { window.__delayRuns = 3500; }")
    n0 = len(bodies)
    pg.click("#p-dlf-retime"); pg.wait_for_timeout(300)
    check(pg.is_visible("#busy") and RUN_MSG in pg.inner_text("#busy"), f"waiting note: {pg.inner_text('#busy')}")
    e1 = pg.inner_text("#elapsed"); pg.wait_for_timeout(2100); e2 = pg.inner_text("#elapsed")
    check(e1 == "0:00" and e2 in ("0:02", "0:03"), f"elapsed counter ticks: {e1} → {e2}")
    check(all(pg.is_disabled(x) for x in ("#sim-today", "#sim-changes", "#p-nallagandla", "#p-dlf", "#p-nanal", "#p-dlf-retime")), "run buttons wait while simulating")
    check(not pg.is_disabled("#iv-add") and not pg.is_disabled("#overview") and not pg.is_disabled("#t-route"), "the rest stays usable")
    check(ivs(pg) == ["2 · ISB Rd / DLF jn: Signal timing, 120 s cycle, 30% green to main road"] and pg.input_value("#iv-j") == "j02", f"preset filled the list: {ivs(pg)}")
    pg.uncheck("#t-route"); pg.wait_for_timeout(200); off = layer(pg, "route")
    pg.check("#t-route"); pg.wait_for_timeout(200)
    pg.click("#live .lj[data-id=j08] .hd"); pg.wait_for_timeout(300)
    opened = pg.get_attribute("#live .lj[data-id=j08] .hd", "aria-expanded")
    pg.click("#live .lj[data-id=j08] .hd"); pg.wait_for_timeout(300)
    check(off == -1 and layer(pg, "route") == 12 and opened == "true", "toggled a layer and opened a live junction while waiting")
    st, dt = wait_status(pg, ["simulated", "failed"], 30)
    check("simulated in 0:0" in st and pg.is_hidden("#busy"), f"done, time taken shown, note gone: {st}")
    check(len(bodies) == n0 + 1 and bodies[-1]["interventions"] == [{"junction_id": "j02", "kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.3}}],
          f"DLF side-road green body (today's run reused): {bodies[n0:]}")
    pg.evaluate("() => { window.__delayRuns = 0; }")
    pg.click("#p-nanal"); wait_status(pg, ["simulated", "failed"], 30); pg.wait_for_timeout(300)
    check(bodies[-1]["interventions"] == [{"junction_id": "j08", "kind": "flyover", "params": {"lanes": 2, "length_m": 1200}}], f"Nanal Nagar + Rethibowli body: {bodies[-1]}")
    pg.wait_for_timeout(300)
    mid = pg.evaluate("() => { const d = structures(changed)[0]; if (!d) return null; const q = d.path[Math.floor(d.path.length / 2)]; return [d.length_m, q[0]]; }")
    check(mid and abs(mid[0] - 1200) < 30 and PTS["j08"]["lon"] < mid[1] < PTS["j09"]["lon"], f"one 1.2 km flyover drawn centred between Nanal Nagar and Rethibowli: {mid}")
    check("420 m apart" in pg.inner_text("#iv-merge") and has_pins(pg) == ["8", "9"], "one flyover note, markers 8 and 9")
    check("flyover, 2 lanes, 1200 m, over nanal nagar + rethibowli" in pg.inner_text("#deltas").lower(), f"headline names the change: {pg.inner_text('#deltas .headline')[:120]}")
    for pid, jid in (("#p-nallagandla", "j01"), ("#p-dlf", "j02")):
        pg.click(pid); wait_status(pg, ["simulated", "failed"], 30); pg.wait_for_timeout(200)
        check(bodies[-1]["interventions"] == [{"junction_id": jid, "kind": "flyover", "params": {"lanes": 2, "length_m": 600}}] and pg.input_value("#iv-j") == jid
              and pg.is_hidden("#iv-merge") and pg.is_hidden("#iv-exists"), f"{pid} body: {bodies[-1]}")
    # a flyover where one already exists: note first, then the result's warning, readable, in the trip panel and step 3
    pg.wait_for_timeout(2500); settle(pg)   # playback's own camera flight selects a junction in the picker ~1.5 s after a run
    clear_ivs(pg)
    pick_kind(pg, "flyover"); pg.select_option("#iv-j", "j06"); pg.wait_for_timeout(100)
    check(pg.inner_text("#iv-exists") == "The main road already crosses Narne Rd jn Shaikpet on the Shaikpet Flyover; this would duplicate it.", f"note: {pg.inner_text('#iv-exists')}")
    pg.click("#iv-add"); pg.wait_for_timeout(100)
    simulate(pg, "#sim-changes", "with 1 change")
    want = "6 · Narne Rd jn Shaikpet, flyover: already has a flyover. The corridor crosses Narne Rd jn Shaikpet on the Shaikpet Flyover; nothing built"
    check(pg.is_visible("#run-warn .warn") and want in pg.inner_text("#run-warn") and "Warnings for this run" in pg.inner_text("#run-warn"), f"warning in the trip panel: {pg.inner_text('#run-warn')!r}")
    check(want in pg.inner_text("#warnings") and "j06" not in pg.inner_text("#warnings"), f"and under the junction table, junction named: {pg.inner_text('#warnings')!r}")
    check("±0.0 min" in pg.inner_text("#deltas .headline") and not pg.evaluate("() => structures(changed).length"), "nothing built: no change, no structure drawn")
    pg.screenshot(path=str(OUT / "corridor_L_dup.png"))

    case = "M errors"; print(case)
    mode["fail"] = "plain"
    pg.click("#sim-today")
    st, _ = wait_status(pg, ["failed", "simulated"], 30)
    check("HTTP 500" in st and "simulation failed: test" in st and "SAMPLE DATA" not in pg.inner_text("body"), f"a failed simulation is shown, not replaced by the sample: {st[:100]}")
    check("last results stay" in pg.inner_text("#run-note") and pg.is_hidden("#busy") and not pg.is_disabled("#sim-today"), "error in step 3, buttons back")
    mode["fail"] = "json"
    pg.click("#p-dlf-retime")
    st, _ = wait_status(pg, ["failed", "simulated"], 30)
    check("netconvert failed at j08: test" in st and "{" not in st, f"FastAPI detail shown as plain text: {st[:100]}")
    pg.close()

    # ---------------- weather: the slider (rain what-if), the weather now in the header ----------------
    case = "W weather"; print(case)
    bodies, mode, counts = [], {"fail": None, "hour_ok": True, "wx_now": WX_NOW_RAIN}, {}
    pg = open_page(b, {"width": 1500, "height": 950}, STREAM_JS % (json.dumps(frames_along("j07", "j08")), 60000))
    mock_api(pg, lambda c: live_flat(), bodies, mode, counts, real_shape=True, weather=True)
    goto(pg)
    w = pg.eval_on_selector("#weather", "e => [e.type, e.min, e.max, e.step, e.value]")
    ticks = pg.eval_on_selector_all("#weather-ticks span", "els => els.map(e => e.textContent.trim())")
    check(pg.is_visible("#weather") and w == ["range", "0", "3", "1", "1"] and ticks == ["Dry", "As measured", "Light rain", "Heavy rain"],
          f"weather slider in the Simulated section, As measured by default: {w} {ticks}")
    wb = pg.evaluate("() => { const r = id => document.getElementById(id).getBoundingClientRect().top; return [r('iv-list'), r('weather-box'), r('jt')]; }")
    check(wb[0] < wb[1] < wb[2], f"the slider sits under the list of changes, above the junction table: {wb}")
    check("As measured" in pg.inner_text("#weather-note") and "rain that actually fell" in pg.inner_text("#weather-note"), f"as measured explained: {pg.inner_text('#weather-note')[:120]!r}")
    now = pg.inner_text("#wx-now") if pg.locator("#wx-now").count() else ""
    src = pg.inner_text("#wx-now .wx-src") if pg.locator("#wx-now .wx-src").count() else ""
    check(pg.is_visible("#wx-now") and pg.locator("#modebar #wx-now").count() == 1 and now.startswith("Weather now:") and "Light rain" in now and "24°C" in now,
          f"header: the weather now (GET /weather/now): {now!r}")
    check(src.strip() == "Real data · live" and pg.locator("#wx-now b").count() >= 1, f"labelled Real data · live: {src!r}")
    check(not any("/weather?" in u or u == "/weather" for u in counts.get("wx", [])), f"no day / hour weather lookups any more: {counts.get('wx')}")
    set_weather(pg, 3); pg.wait_for_timeout(400)
    note = pg.inner_text("#weather-note")
    check(note.startswith("Heavy rain what-if:") and "Trip time vs dry: +7.9% (95% range −3.9% to +16.1%)" in note and "estimated" in note,
          f"heavy rain explained with the estimate and its range (GET /weather/factors): {note!r}")
    check(not bodies, f"moving the slider before any run simulates nothing: {bodies}")
    n0 = len(bodies)
    simulate(pg, "#sim-today", "heavy rain (what-if)")
    check(bodies[n0:] == [{"interventions": [], "volume_scale": 1.0, "weather": "heavy_rain"}], f"weather sent with the run: {bodies[n0:]}")
    pg.wait_for_timeout(2000)
    s = strips(pg)
    rn = pg.inner_text("#run-note")
    st_ = pg.inner_text("#deltas #sim-today.headline") if pg.locator("#deltas #sim-today.headline").count() else ""
    check(len(s) == 1 and s[0][3].startswith("Real data · typical day") and st_.startswith(f"Simulated today: {WX_TRIP['heavy_rain'] * SAMPLE['baseline']['journey']['total_s'] / 60:.1f} min, heavy rain (what-if) (real data 56.2)"),
          f"today's line says the weather (simulated) and the measured row stays as measured: {[x[3][:60] for x in s]} / {st_!r}")
    check("Weather what-if: heavy rain" in rn and "+7.9% (95% range −3.9% to +16.1%)" in rn and pg.locator("#run-note .tag.est").count() == 1,
          f"result line: estimate, range, estimated tag: {rn[-120:]!r}")
    check(pg.inner_text("#clock").startswith("Minute ") and pg.inner_text("#clock").endswith(" · Simulated typical day, heavy rain"), f"clock: {pg.inner_text('#clock')!r}")
    n0 = len(bodies)
    set_win(pg, 20); pg.wait_for_timeout(2500)
    check(bodies[n0:] == [{"interventions": [], "volume_scale": 1.0, "frames_from_min": 20, "frames_minutes": 5, "weather": "heavy_rain"}],
          f"re-recording another window keeps the weather: {bodies[n0:]}")
    n0 = len(bodies)
    pg.click("#p-nanal"); wait_status(pg, ["simulated", "failed"], 30); pg.wait_for_timeout(1500)
    check(bodies[n0:] == [{"interventions": [{"junction_id": "j08", "kind": "flyover", "params": {"lanes": 2, "length_m": 1200}}], "volume_scale": 1.0, "weather": "heavy_rain"}]
          and "both in heavy rain (what-if)" in pg.inner_text("#deltas") and strips(pg)[1][3].startswith("Simulated with your changes, heavy rain"),
          f"a quick demo in heavy rain: {bodies[n0:]} / {pg.inner_text('#deltas')[:120]!r}")
    bt = banned_text(pg)
    check(not bt, f"no 'TomTom' or 'July' in the visible text with a weather what-if: {bt}")
    pg.screenshot(path=str(OUT / "corridor_W_weather.png"))
    n0 = len(bodies)
    set_weather(pg, 0)
    st, _ = wait_status(pg, ["dry (what-if): simulated", "failed"], 30); pg.wait_for_timeout(800)
    check(sorted(x.get("weather") for x in bodies[n0:]) == ["dry", "dry"] and len(bodies[n0:]) == 2 and strips(pg)[1][3].startswith("Simulated with your changes, dry") and "both in dry (what-if)" in pg.inner_text("#deltas"),
          f"another weather re-simulates both rows once: {[x.get('weather') for x in bodies[n0:]]} / {st}")
    n0 = len(bodies)
    set_weather(pg, 1)
    t0 = time.time()
    while time.time() - t0 < 30 and (len(bodies) < n0 + 2 or "simulated" not in pg.inner_text("#status") or pg.is_visible("#busy")):
        pg.wait_for_timeout(300)
    pg.wait_for_timeout(800)
    check(len(bodies[n0:]) == 2 and all("weather" not in x for x in bodies[n0:]) and re.match(r"Simulated with your changes(SIMULATED)?$", strips(pg)[1][3])
          and "what-if" not in pg.inner_text("#deltas") and "Weather what-if" not in pg.inner_text("#run-note") and "rain that actually fell" in pg.inner_text("#weather-note"),
          f"As measured: no weather sent, no weather in the labels: {bodies[n0:]} / {pg.inner_text('#status')!r}")
    mode["wx_now"] = None
    pg.evaluate("() => loadWxNow()"); pg.wait_for_timeout(500)
    check(pg.is_hidden("#wx-now"), "GET /weather/now 503: the chip is hidden")
    pg.close()

    # ---------------- water-logging points, the junction advisor, the assistant's suggested questions ----------------
    case = "WL waterlog+advice"; print(case)
    bodies, mode, counts = [], {"fail": None}, {}
    pg = open_page(b, {"width": 1500, "height": 950}, STREAM_JS % (json.dumps(frames_along("j07", "j08")), 60000) + "\nwindow.ADV_POLL_MS = 300;")
    mock_api(pg, lambda c: live_flat(), bodies, mode, counts, real_shape=True, weather=True)
    wl_body = dict(WX.weather_factors(), waterlogging=WATERLOG)
    pg.route("http://localhost:8000/weather/factors", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(wl_body)))

    def wl_runs(route):   # as measured 56.6 min, heavy rain 63.8 (Tolichowki queue 150 -> 320 m), light rain 58.1
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        body = json.loads(route.request.post_data or "{}")
        bodies.append(body)
        w = body.get("weather")
        r = wl_run("r_wl_" + (w or "measured"), {"heavy_rain": 63.8, "light_rain": 58.1}.get(w, 56.6), 320 if w == "heavy_rain" else 150, body.get("interventions", []))
        if w:
            r["time"] = dict(r["time"], weather=w)
            r["inputs"]["weather"] = {"weather": w, "label": "estimated", "expected_trip_time_factor_vs_dry": WX_TRIP[w], "expected_trip_time_factor_vs_dry_ci95": WX_CI[w],
                                      "affected_junctions": ["Gachibowli Circle", "Tolichowki"],
                                      "waterlogging": [{"junction_id": "j07", "name": "Galaxy Theatre", "junction_name": "Tolichowki", "severity": "high", "extra_speed_factor": 0.8, "label": "reported"}]}
        route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(r))
    pg.route("http://localhost:8000/corridor/runs", wl_runs)
    adv = {"get": 0, "post": 0, "poll": 0}
    ADV_OPTS = [{"rank": 1, "kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.3}, "trip_change_min": -3.1, "noise_min": 0.8, "beyond_noise": True,
                 "ripple": {"worse": []}, "rain_change_min": -2.4, "at_110_change_min": -4.0, "cost_class": "low", "run_id": "r_adv_1", "applicable": True},
                {"rank": 2, "kind": "flyover", "params": {"lanes": 2, "length_m": 600}, "trip_change_min": -0.5, "noise_min": 0.8, "beyond_noise": False,
                 "ripple": {"worse": []}, "rain_change_min": -0.2, "at_110_change_min": -0.9, "cost_class": "high", "run_id": "r_adv_2", "applicable": True},
                {"rank": 3, "kind": "one_way", "params": {}, "trip_change_min": 0.4, "noise_min": 0.8, "beyond_noise": False, "cost_class": "low", "run_id": None, "applicable": False}]
    ADV_ROW = {"status": "done", "stale": False, "advice": {"verdict": "retime", "verdict_code": "retime_signal", "headline": "Retime the DLF signal: about 3 min faster, beyond the noise",
                                                          "options": ADV_OPTS, "reasons": ["The side roads get too much green."], "caveats": ["Typical day only."], "brief_id": None,
                                                          "baseline": {"run_id": "r_adv_base"}}}

    def adv_route(route):
        u = urlparse(route.request.url).path
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if u.startswith("/agent/advice/id/"):
            adv["poll"] += 1
            row = dict(ADV_ROW, advice_id="adv1") if adv["poll"] >= 3 else {"advice_id": "adv1", "status": "running"}
            return route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(row))
        if u.startswith("/agent/advise/"):
            adv["post"] += 1
            return route.fulfill(status=202, content_type="application/json", headers=CORS, body=json.dumps({"advice_id": "adv1", "status": "queued"}))
        adv["get"] += 1
        if u.endswith("/j07"):   # pre-computed
            return route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(ADV_ROW))
        route.fulfill(status=404, content_type="application/json", headers=CORS, body=json.dumps({"detail": "no advice yet"}))
    pg.route(re.compile(r"http://localhost:8000/agent/advi(c|s)e/.*"), adv_route)
    SUGG = ["Why is Nanal Nagar slow at 6 pm?", "What would a flyover at DLF change?", "Is the Tolichowki queue getting worse?"]
    pg.route("http://localhost:8000/agent/suggestions", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps({"questions": SUGG})))
    pg.route("http://localhost:8000/runs/r_adv_*", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(
        wl_run("r_adv_1", 53.5, 150, [{"junction_id": "j02", "kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.3}}])
        if r.request.url.endswith("r_adv_1") else wl_run("r_adv_base", 56.6, 150, []))))
    goto(pg)
    sg = pg.eval_on_selector_all("#chat-sugg .sugg", "els => els.map(e => e.textContent)")
    check(sg == SUGG, f"chat suggestions from GET /agent/suggestions: {sg}")
    drops = lambda: pg.eval_on_selector_all(".drop[data-jid]", "els => els.map(e => [e.dataset.jid, e.dataset.sev, e.title])")
    check(pg.is_hidden("#wl-note") and not drops(), "As measured: no water-logging note, no droplets")
    set_weather(pg, 3); pg.wait_for_timeout(300)
    wn = pg.inner_text("#wl-note") if pg.is_visible("#wl-note") else ""
    d = drops()
    check(wn.startswith("Heavy rain: expect longer queues at Gachibowli, Biodiversity jn, Shaikpet, Tolichowki, Nanal Nagar, Masab Tank and Lakdikapul (reported water-logging points)")
          and "reported, not measured by us" in wn, f"heavy rain: where queues grow, reported points: {wn!r}")
    sh = [x for x in d if x[0] == "j06"]
    ll = pg.evaluate("() => { const m = [...document.querySelectorAll('.drop[data-jid=j06]')][0]; if (!m) return null; const r = m.getBoundingClientRect(), p = map.project([78.3950, 17.4135]), c = map.getContainer().getBoundingClientRect(); return [r.left + r.width / 2 - c.left - p.x, r.top + r.height / 2 - c.top - p.y]; }")
    check(len(d) == 7 and sorted(x[0] for x in d) == sorted(["j03", "j04", "j06", "j07", "j08", "j11", "B_lakdikapul"]) and sh and sh[0][1] == "high" and "Shaikpet · Shaikpet Nala" in sh[0][2]
          and ll and abs(ll[0]) < 12 and abs(ll[1]) < 16, f"7 droplets on the map, severity, title, Shaikpet at its exact spot ({ll}): {[x[:2] for x in d]}")
    set_weather(pg, 2); pg.wait_for_timeout(300)
    wn = pg.inner_text("#wl-note") if pg.is_visible("#wl-note") else ""
    check(wn.startswith("Light rain: expect longer queues at Shaikpet, Tolichowki and Lakdikapul") and sorted(x[0] for x in drops()) == ["B_lakdikapul", "j06", "j07"], f"light rain: 3 points: {wn!r}")
    set_weather(pg, 0); pg.wait_for_timeout(300)
    check(pg.is_hidden("#wl-note") and not drops(), "Dry: no note, no droplets")
    set_weather(pg, 1); pg.wait_for_timeout(300)
    check(pg.is_hidden("#wl-note") and not drops() and not bodies, "As measured again: none (nothing simulated yet)")
    simulate(pg, "#sim-today", "today's roads")
    n0 = len(bodies)
    set_weather(pg, 3)
    st, _ = wait_status(pg, ["heavy rain (what-if): simulated", "failed"], 30); pg.wait_for_timeout(500)
    rn = pg.inner_text("#run-note")
    check([x.get("weather") for x in bodies[n0:]] == ["heavy_rain"], f"heavy rain re-simulates today once: {bodies[n0:]} / {st}")
    check(re.search(r"Water-logging: slower lanes around Gachibowli[^\n]*Tolichowki", rn) and rn.count("reported, not measured by us") >= 1, f"result line: water-logging, reported: {rn!r}")
    check("Rain vs as measured: trip +7.2 min (63.8 vs 56.6)" in rn and "slower stretches:" in rn and "Tolichowki 150 → 320 m" in rn, f"rain vs as measured: trip, stretches, queues: {rn[-260:]!r}")
    # the advisor: none stored (404) -> POST ?async=1 and poll, then the ranked options; Show on map loads the run
    pg.wait_for_timeout(2500)   # playback flies to (and selects) a junction first
    pg.select_option("#iv-j", "j02"); pg.wait_for_timeout(100)
    pg.click("#advise"); pg.wait_for_timeout(250)
    busy = pg.inner_text("#advice") if pg.is_visible("#advice") else ""
    check("Terascope AI is testing options at ISB Rd / DLF" in busy and pg.locator("#adv-el").count() == 1, f"while the advisor runs: {busy[:100]!r}")
    pg.wait_for_selector("#advice table.adv", timeout=10000); pg.wait_for_timeout(200)
    th = pg.eval_on_selector_all("#advice table.adv th", "els => els.map(e => e.textContent.trim())")
    rows = pg.eval_on_selector_all("#advice table.adv tr[data-kind]", "els => els.map(e => [...e.cells].slice(0, 7).map(c => c.textContent.trim()))")
    check(adv["get"] == 1 and adv["post"] == 1 and adv["poll"] >= 3, f"GET (404), POST ?async=1, polled: {adv}")
    check("Retime the DLF signal" in pg.inner_text("#advice .adv-hd") and "SIMULATED" in pg.inner_text("#advice .adv-hd") and th[:7] == ["#", "Option", "Trip min", "Beyond noise?", "Rain", "110%", "Cost"],
          f"headline, SIMULATED, columns: {th}")
    check(rows == [["1", "Signal timing, 120 s cycle, 30% green to main road", "−3.1", "yes", "−2.4", "−4.0", "low"], ["2", "Flyover, 2 lanes, 600 m", "−0.5", "no (±0.8)", "−0.2", "−0.9", "high"]],
          f"one row per applicable option: {rows}")
    pg.click("#advice .adv-show >> nth=0"); pg.wait_for_timeout(1500)
    check([x[0] for x in strips(pg)] == ["tomtom", "changed"] and ivs(pg) == ["2 · ISB Rd / DLF jn: Signal timing, 120 s cycle, 30% green to main road"], f"Show on map loads the run: {[x[0] for x in strips(pg)]} / {ivs(pg)}")
    pg.select_option("#iv-j", "j07"); pg.wait_for_timeout(200)
    check(pg.is_hidden("#advice"), "another junction: the advice is hidden")
    pg.click("#advise"); pg.wait_for_selector("#advice table.adv", timeout=5000)
    check(adv["post"] == 1 and adv["get"] == 2, f"pre-computed advice (GET 200): shown at once, nothing run: {adv}")
    bt = banned_text(pg)
    check(not bt, f"no 'TomTom' or 'July' with the advice and the rain line on screen: {bt}")
    pg.screenshot(path=str(OUT / "corridor_WL.png"))
    pg.close()

    # ---------------- the live trip and Simulate now (a now-cast on the same map) ----------------
    case = "V now-cast"; print(case)
    bodies, mode, counts = [], {"fail": None, "hour_ok": True, "lt": 200, "stale": False, "gone": False}, {}
    pg = open_page(b, {"width": 1500, "height": 950}, STREAM_JS % (json.dumps(frames_along("j07", "j08")), 60000))
    pg.add_init_script("window.NC_POLL_MS = 300; window.LT_REFRESH_MS = 600000;")
    mock_api(pg, lambda c: live_flat(), bodies, mode, counts, real_shape=True, geometry=True, live_now=True)
    nc_bodies = []

    def lt_route(route):
        counts["lt"] = counts.get("lt", 0) + 1
        if mode["lt"] != 200:
            return route.fulfill(status=503, headers=CORS, content_type="application/json", body=json.dumps({"detail": "live trip unavailable (test)"}))
        route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps(live_trip_body(mode["stale"])))

    def nc_post(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        body = json.loads(route.request.post_data or "{}")
        nc_bodies.append(body)
        if body.get("live_bucket"):   # a variant fitted to its baseline's bucket: cached, answered at once (or 410 once the bucket is gone)
            if mode["gone"]:
                return route.fulfill(status=410, headers=CORS, content_type="application/json", body=json.dumps({"detail": "live bucket gone (test)"}))
            res = nowcast_result(body["interventions"], "r_nc_chg")
            return route.fulfill(status=202, headers=CORS, content_type="application/json", body=json.dumps({"run_id": res["run_id"], "status": "done", "cached": True, "result": res}))
        counts["poll"] = 0
        route.fulfill(status=202, headers=CORS, content_type="application/json", body=json.dumps({"run_id": "r_nc_base", "status": "queued"}))

    def nc_poll(route):
        counts["poll"] = counts.get("poll", 0) + 1
        if counts["poll"] < 4:
            return route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps({"run_id": "r_nc_base", "status": "running", "elapsed_s": counts["poll"]}))
        route.fulfill(status=200, headers=CORS, content_type="application/json", body=json.dumps({"run_id": "r_nc_base", "status": "done", "result": nowcast_result([], "r_nc_base")}))
    pg.route("http://localhost:8000/corridor/live_trip", lt_route)
    pg.route(re.compile(r".*/corridor/runs\?async=1$"), nc_post)
    pg.route(re.compile(r".*/corridor/runs/r_nc_[a-z]+$"), nc_poll)
    goto(pg)
    check(pg.is_visible("#nc-box") and pg.locator("#right #nc-box").count() == 1, "the live trip card and Simulate now in the right panel, from the start")
    nb = pg.evaluate("() => [document.getElementById('nc-box').getBoundingClientRect().top, document.getElementById('live-box').getBoundingClientRect().top, document.getElementById('layers-box').getBoundingClientRect().top]")
    check(nb[0] < nb[1] < nb[2], f"right panel: live trip, then live junctions, then layers: {nb}")
    check(pg.is_visible("#lt-box") and pg.inner_text("#lt-total") == "33.7 min" and "Real data · live" in pg.inner_text("#lt-box h2"), f"live trip card, 33.7 min: {pg.inner_text('#lt-box')[:80]!r}")
    vs, asof = pg.inner_text("#lt-vs"), pg.inner_text("#lt-asof")
    check("Typical day, same hour 38.9 min" in vs and "−5.2 min" in vs and "high" in asof and "as of 01:49 IST" in asof, f"vs typical day same hour, confidence, as of: {vs!r} / {asof!r}")
    strip = pg.eval_on_selector_all("#lt-strip span", "els => els.map(e => [e.style.backgroundColor, e.title])")
    check(len(strip) == 12 and "12 km/h now" in strip[8][1] and strip[8][0] == "rgb(226, 61, 39)", f"12 stretches coloured by live speed: {strip[8] if len(strip) > 8 else strip}")
    check(pg.is_hidden("#lt-stale"), "fresh data: no stale badge")
    mode["stale"] = True; pg.evaluate("() => loadLiveTrip()"); pg.wait_for_timeout(400)
    check(pg.is_visible("#lt-stale") and pg.inner_text("#lt-stale") == "STALE", "stale data: STALE badge")
    mode["stale"] = False; pg.evaluate("() => loadLiveTrip()"); pg.wait_for_timeout(400)
    check(pg.is_visible("#nc-run") and pg.inner_text("#nc-run").lower() == "simulate now" and pg.is_hidden("#nc-change"), "Simulate now pill shown (no change button before a now-cast)")
    check(layer(pg, "vehicles") == -1 and layer(pg, "vehicle-dots") == -1 and pg.is_hidden("#pb"), "nothing simulated on the map before Simulate now")
    pg.click("#nc-run"); pg.wait_for_timeout(500)
    busy = pg.inner_text("#nc-busy") if pg.is_visible("#nc-busy") else ""
    check("Simulating the corridor now" in busy and "0:0" in busy and pg.is_disabled("#nc-run"), f"progress with elapsed time while it runs: {busy[:90]!r}")
    pg.wait_for_selector("#nc-result:not([hidden])", timeout=15000); pg.wait_for_timeout(2500)
    check(nc_bodies[:1] == [{"interventions": [], "day": "live", "volume_scale": 1.0}] and counts.get("poll", 0) >= 4, f"POST ?async=1 day live, then polled: {nc_bodies[:1]} / {counts.get('poll')} polls")
    lab = pg.inner_text("#nc-label")
    check(lab.startswith("Now-cast 01:49 IST (real data · live") and "SIMULATED" in lab and pg.is_visible("#nc-clamped"), f"time.label in plain words, SIMULATED, night badge: {lab[:100]!r}")
    res = pg.inner_text("#nc-result")
    check("Simulated trip now 34.2 min" in res and "live estimate 33.7 min" in res, f"simulated trip vs live estimate: {res[:140]!r}")
    leg = pg.inner_text("#nc-legend")
    check(pg.is_visible("#nc-legend") and "Cars: SIMULATED now-cast, tuned to real data · live at 01:49" in leg and "REAL" in leg, f"legend: {leg[:140]!r}")
    nv = max(layer(pg, "vehicles"), layer(pg, "vehicle-dots"))
    check(nv > 0 and pg.evaluate("() => playing && nowcastOn() && playingRun === ncBase") and layer(pg, "live-queues") > 0,
          f"simulated vehicles drawn on the same map ({nv}), playing, live queues still on ({layer(pg, 'live-queues')})")
    check(all(layer(pg, x) == -1 for x in ("nc-vehicles", "nc-vehicle-dots", "nc-structures")), "no separate now-cast layers any more")
    wt = pg.inner_text("#watch").split() if pg.is_visible("#watch") else []
    check(pg.is_visible("#pb") and pg.is_visible("#clock"), f"the playback pill shows for the now-cast: {pg.inner_text('#clock')!r}")
    check("vehicles" in pg.inner_text("#nc-clock"), f"now-cast clock: {pg.inner_text('#nc-clock')!r}")
    pg.screenshot(path=str(OUT / "corridor_V_nowcast.png"))
    check(pg.is_visible("#nc-change") and "ISB Rd / DLF" in pg.inner_text("#nc-change"), f"Try a change now offered: {pg.inner_text('#nc-change')!r}")
    pg.click("#nc-change"); pg.wait_for_selector("#nc-cmp", timeout=10000); pg.wait_for_timeout(800)
    check(nc_bodies[-1].get("live_bucket") == NC_BUCKET and nc_bodies[-1]["interventions"][0]["junction_id"] == "j02" and nc_bodies[-1]["day"] == "live",
          f"the change runs with the baseline's live_bucket: {nc_bodies[-1]}")
    cmp_ = pg.inner_text("#nc-cmp")
    check("31.7 min" in cmp_ and "−2.5 min" in cmp_ and "WITH CHANGES" in cmp_ and pg.evaluate("() => playingRun === ncChanged"), f"now-cast vs with the change: {cmp_!r}")
    wt = pg.inner_text("#watch").split() if pg.is_visible("#watch") else []
    check(wt == ["Watch", "Now", "With", "the", "change"] and pg.get_attribute("#watch-changed", "aria-selected") == "true", f"the pill's Watch: Now | With the change: {wt}")
    pg.click("#watch-base"); pg.wait_for_timeout(500)
    check(pg.evaluate("() => playingRun === ncBase"), "the pill's Now plays the now-cast")
    pg.click("#nc-watch-chg"); pg.wait_for_timeout(300)
    check(pg.evaluate("() => playingRun === ncChanged"), "Watch with the change (in the card)")
    pg.click("#nc-watch-base"); pg.wait_for_timeout(300)
    check(pg.evaluate("() => playingRun === ncBase"), "watch the now-cast again")
    bt = banned_text(pg)
    check(not bt, f"no 'TomTom' or 'July' with the now-cast on screen: {bt}")
    mode["gone"] = True; pg.click("#nc-change"); pg.wait_for_timeout(1200)
    check("moved on" in pg.inner_text("#nc-result") and pg.is_hidden("#nc-change"), f"410 (bucket gone): asks to Simulate now again: {pg.inner_text('#nc-result')[:90]!r}")
    mode["lt"] = 503; pg.evaluate("() => loadLiveTrip()"); pg.wait_for_timeout(400)
    check(pg.is_hidden("#lt-box") and pg.is_hidden("#nc-run") and "unavailable" in pg.inner_text("#lt-off").lower(), f"503: live trip card hidden, 'unavailable': {pg.inner_text('#lt-off')!r}")
    check(pg.is_visible("#live-box") and pg.is_visible("#sim-today"), "the rest of the page stays")
    pg.close()

    # ---------------- view: no accidental page zoom, Reset view, panels reachable and collapsible ----------------
    case = "Z view"; print(case)
    bodies, mode, counts = [], {"fail": None, "hour_ok": True}, {}
    pg = open_page(b, {"width": 1280, "height": 700}, STREAM_JS % (json.dumps(frames_along("j07", "j08")), 60000))
    mock_api(pg, lambda c: live_flat(), bodies, mode, counts, real_shape=True)
    goto(pg)
    check("maximum-scale=1" in pg.get_attribute("meta[name=viewport]", "content"), "viewport meta: no touch pinch-zoom of the page")
    wheel = "(id, ctrl) => !document.getElementById(id).dispatchEvent(new WheelEvent('wheel', { ctrlKey: ctrl, deltaY: -120, bubbles: true, cancelable: true }))"
    check(pg.evaluate(f"() => ({wheel})('left', true)") and pg.evaluate(f"() => ({wheel})('right', true)") and pg.evaluate(f"() => ({wheel})('journey', true)"),
          "ctrl+wheel (trackpad pinch) over a panel is cancelled: it cannot zoom the page")
    check(not pg.evaluate(f"() => ({wheel})('left', false)"), "a plain wheel over a panel is not cancelled: the panel still scrolls")
    z0 = pg.evaluate("() => map.getZoom()")
    pg.keyboard.down("Control"); pg.mouse.move(200, 400); pg.mouse.wheel(0, -400); pg.wait_for_timeout(200)
    pg.mouse.move(800, 300); pg.mouse.wheel(0, -400); pg.keyboard.up("Control"); pg.wait_for_timeout(900)
    vv = pg.evaluate("() => [visualViewport.scale, devicePixelRatio, window.innerWidth]")
    check(vv == [1, 1, 1280] and pg.evaluate("() => map.getZoom()") > z0 + 0.2, f"real ctrl+wheel: the page keeps its zoom {vv}, over the map it zooms the map ({z0:.2f} -> {pg.evaluate('() => map.getZoom()'):.2f})")
    # panels inside the window at 1280 x 700, each with its own scroll; the pill between the right panel and the trip panel
    rc = pg.evaluate("() => Object.fromEntries(['left', 'right', 'journey', 'reset-view', 'ask-open'].map(id => { const e = document.getElementById(id), r = e.getBoundingClientRect(); return [id, [r.top, r.bottom, r.left, r.right, e.scrollHeight > e.clientHeight, getComputedStyle(e).overflowY]]; }))")
    check(rc["left"][1] <= 700 and rc["left"][4] and rc["left"][5] == "auto" and rc["right"][1] <= rc["ask-open"][0] and rc["ask-open"][1] <= rc["reset-view"][0] and rc["reset-view"][1] <= rc["journey"][0] and rc["journey"][1] <= 700,
          f"1280x700: left panel scrolls inside the window, the right panel ends above Ask Terascope AI, then Reset view, then the trip: {rc}")
    pg.evaluate("() => { $('left').scrollTop = 400; }")
    check(pg.evaluate("() => $('left').scrollTop") > 100, "the controls panel scrolls")
    # collapse / expand
    pg.click("#left > .pcollapse"); pg.wait_for_timeout(200)
    st = pg.evaluate("() => { const l = $('left'), c = l.querySelector('.pcollapse'); return [l.classList.contains('collapsed'), l.getBoundingClientRect().height, getComputedStyle(l.querySelector('#presets')).display, c.getAttribute('aria-expanded'), c.innerText]; }")
    check(st[0] and st[1] < 50 and st[2] == "none" and st[3] == "false" and st[4].strip().lower() == "controls", f"collapse the controls panel: the map is clear, a small 'Controls' button stays: {st}")
    pg.click("#left > .pcollapse"); pg.wait_for_timeout(200)
    check(not pg.evaluate("() => $('left').classList.contains('collapsed')") and pg.is_visible("#sim-today") and pg.get_attribute("#left > .pcollapse", "aria-expanded") == "true", "expand it again")
    pg.click("#right > .pcollapse"); pg.click("#journey > .pcollapse"); pg.wait_for_timeout(200)
    lbl = pg.evaluate("() => ['right', 'journey'].map(id => $(id).querySelector('.pcollapse').innerText.trim().toLowerCase())")
    check(pg.evaluate("() => ['right', 'journey'].every(id => $(id).classList.contains('collapsed'))") and pg.is_hidden("#t-route") and pg.is_hidden("#live-box") and pg.is_hidden("#strips")
          and lbl == ["live", "trip"], f"the live / layers and trip panels collapse too ('Live', 'Trip' buttons stay): {lbl}")
    # Reset view: camera back to the whole corridor, follow / orbit stopped, panels open and at the top
    simulate(pg, "#sim-today", "today's roads"); pg.wait_for_timeout(2500)
    pg.evaluate("() => overview(false)"); pg.wait_for_timeout(300)
    home = pg.evaluate("() => [map.getZoom(), map.getCenter().lng, map.getCenter().lat, map.getPitch(), map.getBearing()]")
    pg.evaluate("() => { $('left').scrollTop = 400; startFollow('v3'); }"); pg.wait_for_timeout(600)
    away = pg.evaluate("() => [following, map.getZoom(), map.getPitch()]")
    check(away[0] == "v3" and away[1] > home[0] + 1 and away[2] > 30, f"following a car, zoomed in and pitched: {away}")
    pg.click("#reset-view"); pg.wait_for_timeout(1600)
    cam = pg.evaluate("() => [map.getZoom(), map.getCenter().lng, map.getCenter().lat, map.getPitch(), map.getBearing(), following, orbiting, !!ride]")
    check(abs(cam[0] - home[0]) < 0.05 and abs(cam[1] - home[1]) < 1e-3 and abs(cam[2] - home[2]) < 1e-3 and abs(cam[3]) < 0.5 and abs(cam[4]) < 0.5 and cam[5] is None and cam[6] is False and cam[7] is False,
          f"Reset view: the whole corridor from above, follow and orbit stopped: {[round(x, 3) if isinstance(x, float) else x for x in cam]} (overview {[round(x, 3) for x in home]})")
    check(pg.evaluate("() => ['left', 'right', 'journey'].every(id => !$(id).classList.contains('collapsed')) && $('left').scrollTop === 0") and pg.is_visible("#strips"),
          "Reset view reopens every panel and scrolls it to the top")
    # keys: R resets (not while typing), Esc stops following
    pg.evaluate("() => startFollow('v3')"); pg.wait_for_timeout(300)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    check(pg.evaluate("() => following") is None, "Esc stops following")
    pg.click("#case-title"); pg.keyboard.type("Ring road"); pg.wait_for_timeout(300)
    check(pg.input_value("#case-title") == "Ring road" and pg.evaluate("() => map.getZoom()") > 14.5, "typing an R in a text box does not reset the view")
    pg.click("#orbit"); pg.wait_for_timeout(300)
    check(pg.evaluate("() => orbiting"), "orbiting")
    pg.evaluate("() => document.activeElement.blur()"); pg.keyboard.press("r"); pg.wait_for_timeout(1600)
    check(abs(pg.evaluate("() => map.getZoom()") - home[0]) < 0.05 and abs(pg.evaluate("() => map.getPitch()")) < 0.5 and pg.evaluate("() => orbiting") is False,
          "R resets the view and stops the orbit")
    pg.evaluate("() => map.jumpTo({ center: [78.43, 17.39], zoom: 15 })"); pg.click("#overview"); pg.wait_for_timeout(1600)
    check(abs(pg.evaluate("() => map.getZoom()") - home[0]) < 0.05, "Whole corridor still works")
    # the page zoomed anyway (browser zoom): a toast says how to undo it
    pg.evaluate("() => { Object.defineProperty(window, 'devicePixelRatio', { get: () => 1.5, configurable: true }); window.dispatchEvent(new Event('resize')); }"); pg.wait_for_timeout(300)
    t = pg.inner_text("#zoom-toast") if pg.is_visible("#zoom-toast") else ""
    check("The page is zoomed in" in t and ("⌘0" in t and "Ctrl+0" in t) and pg.locator("#zoom-toast .zt-reset").count() == 1, f"zoom toast: {t!r}")
    pg.screenshot(path=str(OUT / "corridor_Z_view.png"))
    pg.click("#zoom-toast .zt-x"); pg.wait_for_timeout(200)
    check(pg.is_hidden("#zoom-toast"), "the toast can be dismissed")
    pg.evaluate("() => { Object.defineProperty(window, 'devicePixelRatio', { get: () => 1, configurable: true }); window.dispatchEvent(new Event('resize')); }"); pg.wait_for_timeout(200)
    check(pg.is_hidden("#zoom-toast"), "back at 100%: no toast")
    pg.close()
    # a phone: panels stacked under the map, the page scrolls, the pill stays on screen and brings everything back
    pg = open_page(b, {"width": 390, "height": 844}, STREAM_JS % (json.dumps(frames_along("j07", "j08")), 60000))
    mock_api(pg, lambda c: live_flat(), bodies, mode, counts, real_shape=True)
    goto(pg)
    pg.evaluate("() => window.scrollTo(0, 1500)"); pg.wait_for_timeout(300)
    r = pg.evaluate("() => { const r = $('reset-view').getBoundingClientRect(); return [r.top, r.bottom, r.left, r.right, window.scrollY, document.documentElement.scrollWidth - innerWidth]; }")
    check(r[4] > 500 and 0 <= r[0] and r[1] <= 844 and r[2] >= 0 and r[3] <= 390 and r[5] <= 0, f"390 px: page scrolls, Reset view stays on screen, no sideways scroll: {r}")
    lp = pg.evaluate("() => { const l = $('left').getBoundingClientRect(), c = $('left').querySelector('.pcollapse').getBoundingClientRect(); return [l.left, l.right, c.left >= l.left && c.right <= l.right && c.top >= l.top]; }")
    check(lp[0] >= 0 and lp[1] <= 390 and lp[2], f"390 px: panels full width, the chevron inside its panel: {lp}")
    pg.click("#reset-view"); pg.wait_for_timeout(1500)
    check(pg.evaluate("() => window.scrollY") == 0, "390 px: Reset view scrolls back to the map")
    pg.close()

    # ---------------- narrow screen ----------------
    case = "N narrow"; print(case)
    bodies, mode, counts = [], {"fail": None, "hour_ok": True}, {}
    pg = open_page(b, {"width": 390, "height": 844}, STREAM_JS % (json.dumps(frames_along("j07", "j08")), 60000))
    mock_api(pg, lambda c: live_flat(), bodies, mode, counts, real_shape=True)
    goto(pg)
    mb = pg.evaluate("() => [document.getElementById('modebar').getBoundingClientRect().toJSON(), document.getElementById('map').getBoundingClientRect().top]")
    check(mb[0]["top"] < 120 and mb[0]["bottom"] <= mb[1] + 1 and mb[0]["width"] > 340 and pg.is_visible("#hdr-title"),
          f"phone: header card on top, above the map, full width ({mb[0]['top']:.0f}-{mb[0]['bottom']:.0f}, map at {mb[1]:.0f})")
    check(counts.get("hour", 0) == 0 and not bodies and not any(pg.locator(x).count() for x in GONE), f"no hour probe, no day / hour controls ({counts.get('hour', 0)} probes, {bodies})")
    s = strips(pg)
    check(s and s[0][0] == "tomtom" and s[0][3].startswith("Real data · typical day") and s[0][2] == "58.2 min", f"measured row: the typical day (all-day average): {s[0][2:] if s else s}")
    n0 = len(bodies)
    simulate(pg, "#sim-today", "today's roads")
    check(bodies[n0:] == [{"interventions": [], "volume_scale": 1.0}], f"the simulation sends no day / hour: {bodies[n0:]}")
    pg.wait_for_timeout(2500)
    st_ = pg.inner_text("#deltas #sim-today.headline") if pg.locator("#deltas #sim-today.headline").count() else ""
    check(st_.startswith(f"Simulated today: {BASE_MIN} min (real data 56.2)") and pg.inner_text("#clock").startswith("Minute 15:") and pg.inner_text("#clock").endswith(" · Simulated typical day"),
          f"labelled the typical day: {st_!r} / {pg.inner_text('#clock')!r}")
    over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    check(over <= 0, f"no sideways scroll ({over} px over)")
    box = pg.evaluate("() => { const m = $('map').getBoundingClientRect(), j = $('journey').getBoundingClientRect(), l = $('left').getBoundingClientRect(), r = $('right').getBoundingClientRect(); return [m.height, m.bottom, j.top, l.top, l.width, r.top, r.width]; }")
    check(box[0] > 300 and box[2] >= box[1] - 1 and box[3] > box[1] and box[5] > box[1] and box[4] > 340 and box[6] > 340, f"map on top, journey, controls and the live panel stacked below, full width: {box}")
    check(pg.evaluate("() => Object.keys(legPaths).length === 12 && Object.values(legPaths).every(p => p.length === 13)"),
          "real GET /corridor shape: per-leg route features used as they are, tomtom.periods read")
    j8 = live_rows(pg, "j08")
    hd8 = pg.inner_text("#live .lj[data-id=j08] .hd")
    check(j8 and j8[0] == ["NH163 N-bound", "100 s", "80 s", "75 s", "150 m"] and "Live 17:20" in hd8, f"flat rows: latest shown, hour averaged: {j8} / {hd8!r}")
    check(pg.is_visible("#live-box") and pg.is_visible("#journey") and [b[:3] for b in badges(pg)] == [["8", "100 s", "bad"]], f"live junctions on a phone with the trip: pin 8 badge {[b[:3] for b in badges(pg)]}")
    check(pg.is_visible("#geo-note") and layer(pg, "live-queues") == -1, "no approach shapes (404): queues stay in the panel, said so")
    pg.click("#live .lj[data-id=j08] .hd"); pg.wait_for_timeout(800)
    over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    check(pg.get_attribute("#live .lj[data-id=j08] .hd", "aria-expanded") == "true" and pg.is_visible("#live .lj[data-id=j08] tr.ap >> nth=0") and over <= 0,
          f"a live junction opens on a phone, no sideways scroll ({over})")
    pg.screenshot(path=str(OUT / "corridor_N_live.png"), full_page=True)
    pg.click("#live .lj[data-id=j08] .hd"); pg.wait_for_timeout(600)
    pg.click("#p-dlf"); wait_status(pg, ["simulated", "failed"], 30); pg.wait_for_timeout(2500)
    check([x[0] for x in strips(pg)] == ["tomtom", "changed"], "presets work on a phone")
    pb = pg.evaluate("() => { const p = $('pb').getBoundingClientRect(), m = $('map').getBoundingClientRect(); return [p.left, p.right, p.top >= m.bottom - 1, document.documentElement.scrollWidth - innerWidth]; }")
    check(pg.is_visible("#pb") and pb[0] >= 0 and pb[1] <= 390 and pb[2] and pb[3] <= 0, f"390 px: the playback pill wraps under the map, no sideways scroll: {pb}")
    pg.evaluate("() => { followCar(); }"); pg.wait_for_timeout(400)
    check(pg.evaluate("() => ride === null"), "no GET /runs/{id}/probes (404): Follow uses the test cars in the recorded frames (no whole trip)")
    check(counts.get("hour", 0) == 0 and not any("day" in x or "hour" in x for x in bodies), f"never a day or an hour sent: {bodies}")
    pg.evaluate("() => window.scrollTo(0, 0)")
    pg.screenshot(path=str(OUT / "corridor_N.png"), full_page=True)

    b.close()

case = "K overall"
check(not errors, f"page errors: {errors or 'none'}")
print("\nSUMMARY")
for c in dict.fromkeys(r[0] for r in results):
    rs = [r for r in results if r[0] == c]
    print(f"  {c:18} {sum(r[1] for r in rs)}/{len(rs)} {'PASS' if all(r[1] for r in rs) else 'FAIL: ' + '; '.join(r[2] for r in rs if not r[1])}")
failed = [r for r in results if not r[1]]
print("RESULT:", "PASS" if not failed else f"FAIL ({len(failed)} of {len(results)} checks)")
sys.exit(1 if failed else 0)
