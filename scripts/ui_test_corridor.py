"""Headless browser test of the corridor view (frontend/corridor.html), clicked the way a user does.

Cases
  A  Load: no errors, 13 markers (A, 1..11, B), time choices with weekday names, TomTom strip (REAL), route drawn,
     3 quick demo buttons, live junction panel hidden when the API has no /corridor/junctions/live
  B  When: choosing a Sunday shortens the measured trip
  C  Changes: controls per kind match sim/templates/corridor.py (flyover lanes/length, signal cycle + main-road share
     slider, widening, one-way with its note, U-turn disabled); add, update (same junction and kind), add another, remove;
     markers highlight changed junctions; flyovers at Nanal Nagar and Rethibowli merge into one 1.2 km flyover (note),
     and the "one flyover over both" button
  D  Simulate today: journey strip from the API or the sample fallback, junction table, sample tag when sample
  E  Simulate with changes: third strip, total and per-leg deltas, knock-on, before/after table, warnings
  F  Camera: table row, map marker, strip block and "Whole corridor" move the map
  G  Layers: route and TomTom traffic on/off
  H  API path (corridor endpoints mocked in the browser): request body, no sample tag, vehicle playback from
     WS frames, play/pause, scrub
  I  Real route line from GET /corridor (route geometry + TomTom legs per period): legs cut along the road,
     coloured by TomTom speed before a run and by simulated speed after
  J  Live junctions (GET /corridor/junctions/live mocked): worst approaches, delay vs usual, queue, REAL, LIVE map
     badges, refresh, popup
  L  Long runs: presets fill the list and simulate; elapsed counter + "usually under 2 minutes" while waiting; the rest of
     the page stays usable; preset bodies (Khajaguda 70% main road, one flyover j08 1200 m)
  M  Errors: HTTP 500 plain text and FastAPI {"detail"} shown as the message (no silent fallback), buttons back
  O  3D: pitched camera, buildings loaded per junction in view (mocked GET /corridor/buildings/{id}), vehicles culled to the
     view and raised on the flyover (z), flyover structure drawn with ramps and piers, follow a test car, orbit, night,
     dots instead of boxes from the whole-corridor view
  N  Narrow screen (390 px): panels stacked under the map, no sideways scroll, live panel from flat snapshot rows,
     GET /corridor in the backend's real shape (tomtom.periods, per-leg route features)
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
import sys
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5180/frontend/corridor.html"
ROOT = Path(__file__).resolve().parent.parent
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


def add_iv(pg, jid, kind, params=None):
    pg.select_option("#iv-j", jid)
    pg.select_option("#iv-kind", kind)
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


def mock_api(pg, live_body, bodies, mode, counts, real_shape=False):
    """Corridor endpoints answered in the browser: GET /corridor (route + TomTom legs), live junctions, runs, roads."""
    def corridor_runs(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        body = json.loads(route.request.post_data or "{}")
        bodies.append(body)
        if mode["fail"] == "plain":
            return route.fulfill(status=500, headers=CORS, body="simulation failed: test")
        if mode["fail"] == "json":
            return route.fulfill(status=500, headers=CORS, content_type="application/json", body=json.dumps({"detail": "netconvert failed at j08: test"}))
        r = json.loads(json.dumps(SAMPLE["flyover_j07" if body.get("interventions") else "baseline"]))
        r.pop("sample", None)
        r["run_id"] = "r_test_" + r["variant_id"]
        r["interventions"] = body.get("interventions", [])
        r["frames_path"] = "test"
        r["inputs"] = {"counts_source": "test", "label": "estimated", "volume_scale": 1.0}
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
        corridor = dict(CORRIDOR, tomtom={"source": "test", "periods": per}, route={"type": "FeatureCollection", "features": feats})
    else:            # other shapes the page also accepts: legs rows with a period, one bendy line per direction (cut by the page)
        corridor = dict(CORRIDOR, legs=API_LEGS, route=route_geojson())
    pg.route("http://localhost:8000/corridor/runs", corridor_runs)
    pg.route("http://localhost:8000/corridor/junctions/live", live)
    pg.route("http://localhost:8000/corridor", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(corridor)))
    pg.route("http://localhost:8000/runs/*/roads", lambda r: r.fulfill(status=404, headers=CORS, body="no roads"))

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
    whens = pg.eval_on_selector_all("#when option", "els => els.map(e => e.textContent)")
    if True:   # measured legs from GET /corridor, else the CSV / embedded copy: the same 16 periods
        check(len(whens) == 16 and whens[0].startswith("Typical July day") and pg.input_value("#when").startswith("2026-07-01..2026-07-31"), f"16 time choices, typical first: {whens[0]}")
    check(any(w.startswith("Sun 5 Jul") for w in whens) and any(w.startswith("Wed 1 Jul") or w.startswith("Wed 8 Jul") for w in whens), f"weekday names: {whens[1:3]}")
    s = strips(pg)
    check(len(s) == 1 and s[0][0] == "tomtom" and s[0][1] == 12, f"TomTom strip with 12 legs before any run: {s}")
    check("REAL" in s[0][3] and s[0][2] == "58 min", f"measured strip tagged REAL, 58 min: {s[0][2]}")
    check(pg.evaluate("() => !!document.querySelector('#map canvas')"), "map canvas present")
    check(layer(pg, "route") == 12, f"route drawn as 12 legs: {layer(pg, 'route')}")
    check("REAL speeds" in pg.inner_text("#route-src") and [round(k, 1) for _, k in route_data(pg)] == TYPICAL_KMH, f"route coloured by TomTom speed: {pg.inner_text('#route-src')}")
    z = pg.evaluate("() => map.getZoom()")
    check(10.5 < z < 13.5, f"map framed on the whole corridor (zoom {z:.1f})")
    pre = pg.eval_on_selector_all("#presets button", "els => els.map(e => e.textContent)")
    check(len(pre) == 3 and "Flyover at Tolichowki" in pre[0] and "Retime Khajaguda signal (70% main road)" in pre[1]
          and "One flyover over Nanal Nagar + Rethibowli" in pre[2], f"3 quick demo buttons: {pre}")
    if api_status("/corridor/junctions/live") != 200:
        check(pg.is_hidden("#live-box") and not pg.eval_on_selector_all(".pin.live", "els => els.length"), "no live endpoint: live panel and badges hidden")
    else:
        n = pg.eval_on_selector_all("#live .lj", "els => els.length")
        check(pg.is_visible("#live-box") and n >= 1 and pg.eval_on_selector_all(".pin.live", "els => els.length") == n, f"real API: {n} live junctions shown and marked on the map")
    if api_status("/corridor") == 200:
        check("Drawn on the real road" in pg.inner_text("#route-src") and all(n > 2 for n, _ in route_data(pg)), f"real API: route on the road ({[n for n, _ in route_data(pg)]} vertices)")
    pg.screenshot(path=str(OUT / "corridor_A.png"))

    case = "B when"; print(case)
    pg.select_option("#when", "2026-07-05..2026-07-05 8:00-20:00"); pg.wait_for_timeout(300)
    s = strips(pg)
    check(s[0][2] == "49 min" and "Sun 5 Jul" in s[0][3], f"Sunday 5 Jul: {s[0][2]}, {s[0][3]}")
    check("Sundays (5 and 12 Jul)" in pg.inner_text("#when-note"), f"note: {pg.inner_text('#when-note')[:110]}")
    pg.select_option("#when", "2026-07-08..2026-07-08 8:00-20:00"); pg.wait_for_timeout(300)
    check(strips(pg)[0][2] == "65 min", f"Wed 8 Jul weekday: {strips(pg)[0][2]}")

    case = "C changes"; print(case)
    keys = lambda: pg.eval_on_selector_all("#iv-params [data-k]", "els => els.map(e => e.dataset.k)")
    opts = lambda k: pg.eval_on_selector_all(f"#iv-params select[data-k={k}] option", "els => els.map(e => e.value)")
    check(keys() == ["lanes", "length_m"] and opts("lanes") == ["1", "2", "3", "4"] and pg.input_value("#iv-params [data-k=lanes]") == "2",
          f"flyover asks for lanes 1-4 (default 2) and length: {opts('lanes')}")
    check(opts("length_m")[0] == "" and "1200" in opts("length_m"), f"flyover length: auto or 400..2000 m: {opts('length_m')}")
    check("over the junction" in pg.inner_text("#iv-help"), f"flyover help: {pg.inner_text('#iv-help')}")
    pg.select_option("#iv-kind", "signal_retime"); pg.wait_for_timeout(100)
    check(keys() == ["cycle_s", "corridor_green_share"] and opts("cycle_s") == ["60", "90", "120", "150", "180"] and pg.input_value("#iv-params [data-k=cycle_s]") == "120",
          f"signal timing: cycle 60-180 s (default 120) and main-road share: {keys()}")
    check("50%" in pg.inner_text("#iv-params .share"), f"share slider shows 50%: {pg.inner_text('#iv-params .share')}")
    pg.fill("#iv-params [data-k=corridor_green_share]", "70"); pg.wait_for_timeout(100)
    check("70% of green to the main road, 30% to side roads" in pg.inner_text("#iv-params .share"), f"slider at 70%: {pg.inner_text('#iv-params .share')}")
    kinds = pg.eval_on_selector_all("#iv-kind option", "els => els.map(e => [e.value, e.disabled, e.textContent])")
    check([k[1] for k in kinds] == [False, False, False, False, False, True] and "soon" in kinds[5][2], f"widening and one-way enabled, U-turn (soon): {kinds}")
    pg.select_option("#iv-kind", "widening"); pg.wait_for_timeout(100)
    check(keys() == ["add_lanes", "length_m"] and opts("add_lanes") == ["1", "2"] and pg.input_value("#iv-params [data-k=length_m]") == "300", f"widening: add_lanes 1-2, length 300 m: {keys()}")
    pg.select_option("#iv-kind", "one_way"); pg.wait_for_timeout(100)
    check(keys() == [] and "closes the smallest side road in one direction" in pg.inner_text("#iv-help").lower(), f"one-way: no choices, note: {pg.inner_text('#iv-help')}")

    add_iv(pg, "j07", "flyover", {"lanes": 3, "length_m": 400})
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
    check([x[0] for x in s] == ["base", "tomtom"] and s[0][1] == 12, f"simulated strip above the TomTom strip: {[(x[0], x[2]) for x in s]}")
    sample = "SAMPLE DATA" in pg.inner_text("#journey")
    print("      (results are", "sample data)" if sample else "from the API)")
    if sample:
        check("SAMPLE DATA" in pg.inner_text("#src") and "SAMPLE DATA" in s[0][3], "sample tag in the header and on the strip")
    check(pg.eval_on_selector_all("#jt tr.j", "els => els.length") == 11, "junction table: 11 rows")
    check("vs TomTom" in pg.inner_text("#deltas"), f"model vs TomTom line: {pg.inner_text('#deltas')[:90]}")
    check("traffic input" in pg.inner_text("#run-note"), f"input label shown: {pg.inner_text('#run-note')[:90]}")
    check(pg.is_hidden("#busy"), "no waiting note once done")
    pg.wait_for_timeout(800)
    check(pg.inner_text("#playinfo") != "", f"playback note: {pg.inner_text('#playinfo')}")

    case = "E changes"; print(case)
    simulate(pg, "#sim-changes", "with 1 change")
    s = strips(pg)
    check([x[0] for x in s] == ["base", "tomtom", "changed"], f"third strip for the changed trip: {[(x[0], x[2]) for x in s]}")
    head = pg.inner_text("#deltas .headline")
    check("Whole trip:" in head and "→" in head and " min, " in head, f"total delta: {head[:90]}")
    chips = pg.eval_on_selector_all("#deltas .delta", "els => els.map(e => [e.className, e.textContent])")
    print("     ", chips)
    check(len(chips) >= 1 and all(("up" in c) == ("+" in t) for c, t in chips), "per-leg deltas coloured: red slower, green faster")
    if sample:
        check("98 → 94 min, −3.7 min" in head, "sample: 98 → 94 min, −3.7 min")
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
    check("Nanal Nagar" in pg.inner_text(".maplibregl-popup"), f"popup: {pg.inner_text('.maplibregl-popup')[:80]}")
    pg.click("#overview"); pg.wait_for_timeout(1600)
    pg.locator(".pin", has_text="3").first.click(); pg.wait_for_timeout(2200)
    ok, c = center_near(pg, "j03")
    check(ok, f"marker 3 flies to Gachibowli (off by {c['lng']:.0f}, {c['lat']:.0f} px)")
    pg.screenshot(path=str(OUT / "corridor_F.png"))
    pg.click("#strips [data-strip=base] .leg[data-leg='6']"); pg.wait_for_timeout(1800)
    c = pg.evaluate("() => map.getCenter()")
    mid = ((PTS["j06"]["lon"] + PTS["j07"]["lon"]) / 2, (PTS["j06"]["lat"] + PTS["j07"]["lat"]) / 2)
    check(abs(c["lng"] - mid[0]) < 0.02 and abs(c["lat"] - mid[1]) < 0.02, f"strip block 6 shows Shaikpet → Tolichowki ({c['lng']:.4f}, {c['lat']:.4f})")
    pg.click("#overview"); pg.wait_for_timeout(1600)
    check(pg.evaluate("() => map.getZoom()") < 13.5, "Whole corridor returns to the overview")

    case = "G layers"; print(case)
    pg.uncheck("#t-route"); pg.wait_for_timeout(200); off = layer(pg, "route")
    pg.check("#t-route"); pg.wait_for_timeout(200); on = layer(pg, "route")
    check(off == -1 and on == 12, f"route off/on: {off} / {on}")
    if not pg.is_disabled("#t-traffic"):
        pg.check("#t-traffic"); pg.wait_for_timeout(300)
        check(pg.evaluate("() => map.getLayer('tomtom-traffic') && map.getLayoutProperty('tomtom-traffic', 'visibility') === 'visible'"), "TomTom live traffic on")
        pg.uncheck("#t-traffic"); pg.wait_for_timeout(200)
        check(pg.evaluate("() => map.getLayoutProperty('tomtom-traffic', 'visibility')") == "none", "TomTom live traffic off")
    pg.close()

    # ---------------- corridor API answering (mocked in the browser): route, live junctions, runs, frames ----------------
    bodies, mode, counts = [], {"fail": None}, {}
    pg = open_page(b, {"width": 1500, "height": 950}, STREAM_JS % (json.dumps(frames_3d()), 2000))
    mock_api(pg, live_nested, bodies, mode, counts)
    goto(pg)

    case = "I route"; print(case)
    rd = route_data(pg)
    check(len(rd) == 12 and all(n >= 10 for n, _ in rd), f"12 legs cut along the road geometry (vertices per leg: {[n for n, _ in rd]})")
    check("Drawn on the real road" in pg.inner_text("#route-src") and "REAL speeds" in pg.inner_text("#route-src"), f"route note: {pg.inner_text('#route-src')}")
    check([round(k, 1) for _, k in rd] == TYPICAL_KMH, "before a run: legs coloured by TomTom speed (typical day)")
    ends = pg.evaluate("() => { const p = legPaths['j07|j08']; return [p[0], p[p.length - 1]]; }")
    check(all(abs(ends[0][i] - [PTS["j07"]["lon"], PTS["j07"]["lat"]][i]) < 1e-4 and abs(ends[1][i] - [PTS["j08"]["lon"], PTS["j08"]["lat"]][i]) < 1e-4 for i in (0, 1)),
          f"leg 7 → 8 starts at Tolichowki and ends at Nanal Nagar: {ends}")
    whens = pg.eval_on_selector_all("#when option", "els => els.map(e => e.textContent)")
    check(len(whens) == 3 and whens[0].startswith("Typical July day") and strips(pg)[0][2] == "58 min", f"TomTom legs per period from GET /corridor: {whens}")

    case = "J live"; print(case)
    check(pg.is_visible("#live-box") and "REAL" in pg.inner_text("#live-box h2"), "live panel shown, tagged REAL")
    cards = pg.eval_on_selector_all("#live .lj", "els => els.map(e => [e.dataset.id, e.querySelectorAll('.ap').length, e.innerText])")
    check([c[0] for c in cards] == ["j07", "j08", "j09"] and all(c[1] == 3 for c in cards), f"3 live junctions, worst 3 approaches each: {[(c[0], c[1]) for c in cards]}")
    j8 = live_rows(pg, "j08")
    check([r[0] for r in j8] == ["NH163 N-bound", "Mumbai Rd E-bound", "Inner Ring Rd N-bound"], f"worst first (by delay), short names: {[r[0] for r in j8]}")
    check(j8[0] == ["NH163 N-bound", "108 s", "80 s", "95 s", "149 m"] and "TomTom 17:17" in cards[1][2], f"delay now, usual, last hour, queue, TomTom time: {j8[0]}")
    check("25 min old" in cards[2][2], f"old TomTom data flagged: {cards[2][2][:40]!r}")
    check(live_rows(pg, "j09")[2][-1] == "1.1 km", f"long queues in km: {live_rows(pg, 'j09')}")
    check(pg.eval_on_selector_all("#live .lj[data-id=j08] th", "els => els.map(e => e.textContent)") == ["Worst approaches", "Delay", "Usual", "Last hr", "Queue"], "column heads")
    check(pg.eval_on_selector("#live .lj[data-id=j08] .ap b", "e => e.classList.contains('bad')"), "much worse than usual: red")
    check("estimated by TomTom" in pg.inner_text("#live-note") and "every 2 s" in pg.inner_text("#live-note"), f"note: {pg.inner_text('#live-note')}")
    check(pg.eval_on_selector_all(".pin.live", "els => els.map(e => e.textContent)") == ["7", "8", "9"], "LIVE badges on markers 7, 8, 9")
    check(pg.eval_on_selector(".pin.live", "e => getComputedStyle(e, '::after').backgroundColor") == "rgb(26, 127, 55)" and pg.is_visible("#live-note .livedot"),
          "green live dot on the markers, explained in the panel")
    n_live = counts.get("live", 0); counts["v2"] = True
    pg.wait_for_timeout(2600)
    check(counts.get("live", 0) > n_live and live_rows(pg, "j08")[0][1] == "131 s", f"refreshed ({counts.get('live')} calls): new NH163 delay shown")
    pg.click("#live .lj[data-id=j09] .hd"); pg.wait_for_timeout(2000)
    pop = pg.inner_text(".maplibregl-popup")
    check(center_near(pg, "j09")[0] and "Live now: 178 s delay (usual 131 s)" in pop and "REAL" in pop, f"live card flies to Rethibowli, popup: {pop[:120]!r}")
    pg.click("#overview"); pg.wait_for_timeout(1300)
    pg.screenshot(path=str(OUT / "corridor_J.png"))

    case = "H api + playback"; print(case)
    add_iv(pg, "j07", "flyover", {"lanes": 2, "length_m": 600})
    simulate(pg, "#sim-changes", "with 1 change")
    check(len(bodies) == 2 and {json.dumps(x["interventions"]) for x in bodies} == {"[]", json.dumps([{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2, "length_m": 600}}])},
          f"POST /corridor/runs bodies (today + with changes): {bodies}")
    check(all(x.get("volume_scale") == 1.0 and "window" not in x for x in bodies), "volume_scale 1.0, no window sent")
    check("SAMPLE DATA" not in pg.inner_text("body"), "no sample tag for API results")
    check([x[0] for x in strips(pg)] == ["base", "tomtom", "changed"], "three strips from API results")
    sim_kmh = [l["speed_kmh"] for l in SAMPLE["flyover_j07"]["journey"]["legs"]]
    check([k for _, k in route_data(pg)] == sim_kmh and "SIMULATED speeds" in pg.inner_text("#route-src"), "after the run: legs coloured by simulated speed")
    check("traffic input: estimated" in pg.inner_text("#run-note"), f"input label: {pg.inner_text('#run-note')[:80]}")
    pg.wait_for_timeout(3500)
    v = layer(pg, "vehicles")
    check(v > 0, f"vehicles drawn from WS frames: {v}")
    check(pg.evaluate("() => map.getZoom()") > 14 and center_near(pg, "j07", 80)[0], "camera flew to the changed junction for playback")
    check("simulated" in pg.inner_text("#clock") and "frames" in pg.inner_text("#playinfo"), f"clock and frames: {pg.inner_text('#clock')} · {pg.inner_text('#playinfo')}")
    pg.screenshot(path=str(OUT / "corridor_H.png"))
    if "Pause" not in pg.inner_text("#play"):
        pg.click("#play")
    pg.click("#play"); pg.wait_for_timeout(400)
    c1 = pg.inner_text("#clock"); pg.wait_for_timeout(1200)
    check("Play" in pg.inner_text("#play") and c1 == pg.inner_text("#clock"), f"pause holds the clock: {c1}")
    pg.evaluate("() => { const s = document.getElementById('scrub'); s.value = Math.floor(s.max / 2); s.dispatchEvent(new Event('input')); }")
    pg.wait_for_timeout(300)
    check(pg.evaluate("() => Math.round(pos)") == pg.evaluate("() => Math.floor(Number(document.getElementById('scrub').max) / 2)"), f"scrub to the middle: {pg.inner_text('#clock')}")
    check(not pg.is_disabled("#sim-today") and not pg.is_disabled("#iv-add"), "panel usable during playback")
    pg.click("#watch-base"); pg.wait_for_timeout(3000)
    check(layer(pg, "vehicles") > 0 and "r_test" not in pg.inner_text("#status"), f"watch today's run: {pg.inner_text('#playinfo')}")

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
    pg.select_option("#speed", "1")
    pg.click("#follow"); pg.wait_for_timeout(1200)
    pr = pg.evaluate("() => { const v = vehicleAt('probe_fwd_1'), c = map.getCenter(); return [v.lon, v.lat, c.lng, c.lat, map.getPitch()]; }")
    check(abs(pr[0] - pr[2]) < 2e-4 and abs(pr[1] - pr[3]) < 2e-4 and pr[4] > 55, f"camera follows the test car: {pr}")
    check("Stop following" in pg.inner_text("#follow") and "Following test car probe_fwd_1" in pg.inner_text("#playinfo"), f"follow state: {pg.inner_text('#playinfo')}")
    pg.click("#follow"); pg.wait_for_timeout(200)
    check("Follow a test car" in pg.inner_text("#follow"), "stop following")
    b0 = pg.evaluate("() => map.getBearing()"); pg.click("#orbit"); pg.wait_for_timeout(1200); b1 = pg.evaluate("() => map.getBearing()")
    pg.click("#orbit"); pg.wait_for_timeout(300); b2 = pg.evaluate("() => map.getBearing()"); pg.wait_for_timeout(500)
    check(3 < (b1 - b0) % 360 < 20 and abs(pg.evaluate("() => map.getBearing()") - b2) < 0.5, f"orbit turns the camera slowly and stops: {b0:.1f} → {b1:.1f}")
    if not pg.is_disabled("#t-night"):
        pg.check("#t-night"); pg.wait_for_timeout(800)
        fill = layer_props(pg, "buildings", "l => l.props.getFillColor")
        check(fill == [70, 82, 100], f"night view: darker buildings {fill}")
        pg.screenshot(path=str(OUT / "corridor_O_night.png"))
        pg.uncheck("#t-night"); pg.wait_for_timeout(800)
    pg.click("#overview"); pg.wait_for_timeout(1500)
    dots = layer_props(pg, "vehicle-dots", "l => l.props.data.length")
    check(layer(pg, "vehicles") == -1 and dots == 54, f"whole corridor: every vehicle as a dot ({dots}), no 3D boxes")
    check(layer(pg, "buildings") == -1, "no buildings drawn from the overview")

    case = "L long runs"; print(case)
    pg.evaluate("() => { window.__delayRuns = 3500; }")
    n0 = len(bodies)
    pg.click("#p-khajaguda"); pg.wait_for_timeout(300)
    check(pg.is_visible("#busy") and RUN_MSG in pg.inner_text("#busy"), f"waiting note: {pg.inner_text('#busy')}")
    e1 = pg.inner_text("#elapsed"); pg.wait_for_timeout(2100); e2 = pg.inner_text("#elapsed")
    check(e1 == "0:00" and e2 in ("0:02", "0:03"), f"elapsed counter ticks: {e1} → {e2}")
    check(all(pg.is_disabled(x) for x in ("#sim-today", "#sim-changes", "#p-tolichowki", "#p-nanal")), "run buttons wait while simulating")
    check(not pg.is_disabled("#iv-add") and not pg.is_disabled("#when") and not pg.is_disabled("#overview"), "the rest stays usable")
    pg.select_option("#when", "2026-07-05..2026-07-05 8:00-20:00"); pg.wait_for_timeout(200)
    check("Sun 5 Jul" in pg.inner_text("#strips"), "changed the day while waiting")
    check(ivs(pg) == ["5 · Khajaguda X Roads: Signal timing, 120 s cycle, 70% green to main road"] and pg.input_value("#iv-j") == "j05", f"preset filled the list: {ivs(pg)}")
    st, dt = wait_status(pg, ["simulated", "failed"], 30)
    check("simulated in 0:0" in st and pg.is_hidden("#busy"), f"done, time taken shown, note gone: {st}")
    check(len(bodies) == n0 + 1 and bodies[-1]["interventions"] == [{"junction_id": "j05", "kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.7}}],
          f"Khajaguda body (today's run reused): {bodies[n0:]}")
    pg.evaluate("() => { window.__delayRuns = 0; }")
    pg.click("#p-nanal"); wait_status(pg, ["simulated", "failed"], 30); pg.wait_for_timeout(300)
    check(bodies[-1]["interventions"] == [{"junction_id": "j08", "kind": "flyover", "params": {"lanes": 2, "length_m": 1200}}], f"Nanal Nagar + Rethibowli body: {bodies[-1]}")
    pg.wait_for_timeout(300)
    mid = pg.evaluate("() => { const d = structures(changed)[0]; if (!d) return null; const q = d.path[Math.floor(d.path.length / 2)]; return [d.length_m, q[0]]; }")
    check(mid and abs(mid[0] - 1200) < 30 and PTS["j08"]["lon"] < mid[1] < PTS["j09"]["lon"], f"one 1.2 km flyover drawn centred between Nanal Nagar and Rethibowli: {mid}")
    check("420 m apart" in pg.inner_text("#iv-merge") and has_pins(pg) == ["8", "9"], "one flyover note, markers 8 and 9")
    check("flyover, 2 lanes, 1200 m, over nanal nagar + rethibowli" in pg.inner_text("#deltas").lower(), f"headline names the change: {pg.inner_text('#deltas .headline')[:120]}")
    pg.click("#p-tolichowki"); wait_status(pg, ["simulated", "failed"], 30)
    check(bodies[-1]["interventions"] == [{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2, "length_m": 600}}], f"Tolichowki body: {bodies[-1]}")

    case = "M errors"; print(case)
    mode["fail"] = "plain"
    pg.click("#sim-today")
    st, _ = wait_status(pg, ["failed", "simulated"], 30)
    check("HTTP 500" in st and "simulation failed: test" in st and "SAMPLE DATA" not in pg.inner_text("body"), f"a failed simulation is shown, not replaced by the sample: {st[:100]}")
    check("last results stay" in pg.inner_text("#run-note") and pg.is_hidden("#busy") and not pg.is_disabled("#sim-today"), "error in step 3, buttons back")
    mode["fail"] = "json"
    pg.click("#p-khajaguda")
    st, _ = wait_status(pg, ["failed", "simulated"], 30)
    check("netconvert failed at j08: test" in st and "{" not in st, f"FastAPI detail shown as plain text: {st[:100]}")
    pg.close()

    # ---------------- narrow screen ----------------
    case = "N narrow"; print(case)
    bodies, mode, counts = [], {"fail": None}, {}
    pg = open_page(b, {"width": 390, "height": 844}, STREAM_JS % (json.dumps(frames_along("j07", "j08")), 60000))
    mock_api(pg, lambda c: live_flat(), bodies, mode, counts, real_shape=True)
    goto(pg)
    over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    check(over <= 0, f"no sideways scroll ({over} px over)")
    box = pg.evaluate("() => { const m = $('map').getBoundingClientRect(), j = $('journey').getBoundingClientRect(), l = $('left').getBoundingClientRect(); return [m.height, m.bottom, j.top, l.top, l.width]; }")
    check(box[0] > 300 and box[2] >= box[1] and box[3] > box[2] and box[4] > 340, f"map on top, journey then controls below, full width: {box}")
    check(pg.evaluate("() => Object.keys(legPaths).length === 12 && Object.values(legPaths).every(p => p.length === 13)") and len(pg.eval_on_selector_all("#when option", "e => e")) == 3,
          "real GET /corridor shape: per-leg route features used as they are, tomtom.periods read")
    j8 = live_rows(pg, "j08")
    check(j8[0] == ["NH163 N-bound", "100 s", "80 s", "75 s", "150 m"] and "TomTom 17:20" in pg.inner_text("#live .lj[data-id=j08]"), f"flat rows: latest shown, hour averaged: {j8}")
    pg.click("#p-tolichowki"); wait_status(pg, ["simulated", "failed"], 30); pg.wait_for_timeout(2500)
    check([x[0] for x in strips(pg)] == ["base", "tomtom", "changed"], "presets work on a phone")
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
