"""Headless browser test of the app shell: the shared top bar (frontend/nav.js) on every page, the home page (index.html),
the decision log (decisions.html) and About the data (data.html), with the API mocked in the browser, real, and offline.

Cases
  A  Top bar on all 5 pages (home, corridor, YMCA close-up, decisions, about the data): wordmark, 5 links in order, the
     current page marked, status pill; nothing on the page under the bar (map, panels, Ask button, map controls); the
     corridor's left panel still ends inside the window; links navigate
  B  Status pill: Real simulation (/health mock false), Mock (mock true), /health missing -> /config decides, API offline
  C  Home (mocked API): one-line pitch, corridor card (58 min, 22.4 km, 11 junctions, 12 coloured legs, REAL), live strip
     (junctions reporting, stale ones flagged, update time, worst delay now with its road and junction, REAL; the weather
     now from GET /weather/now, modelled, hidden on 503), decisions card (count, latest case and its stage), YMCA card,
     How it works in 3 steps, card links
  D  Decisions (mocked): list newest first with stage, author, time; stage filters with counts (and #stage= links);
     case detail: stage tracker, verdict, timeline proposed -> in review -> decided with actor, time, decision, reason,
     re-test results; runs table (option in words, traffic level incl. the review's 120%, trip minutes, change vs today,
     SAMPLE DATA tag); evidence fingerprints short with the full SHA-256 on hover; chain explanation and link check
     (intact and broken); brief rendered as markdown with HTML escaped; Print brief; Open in corridor link; back to list;
     unknown case and missing brief say so
  E  Corridor deep link: corridor.html#case=<id> opens that case in step 4 (July typical day mode); corridor.html#mode=live
     (the home page's "See it on the map") opens Live now
  F  About the data (mocked /corridor/calibration): sources REAL vs SIMULATED, live junction count, TomTom 58 min and the
     day range, per-stretch table (12 stretches + whole trip, sim vs TomTom, coloured difference), calibrated knobs with
     labels, junction delays, volumes with the "fewer vehicles than TomTom" note, inputs table with what is assumed,
     glossary anchors; calibration 404 explained; rain hour by hour (GET /weather/factors): headline with 95% ranges,
     12-stretch table with the 3 stretches slower beyond chance marked
  G  Real API on :8000 (skipped when it is not running): home, decisions and data page numbers match the API
  H  API offline: every page still loads; home falls back to the saved TomTom numbers; decisions and data say the API is
     not answering; pill says offline
  N  Phone (390 px): every page has the two-row bar with short labels all in view, nothing under it, no sideways scroll
  K  No page errors at any point

Usage (frontend/ served on :5174; the API on :8000 is only needed for case G):
    cd frontend && python3 -m http.server 5174 &
    PLAYWRIGHT_BROWSERS_PATH=~/Library/Caches/ms-playwright .venv/bin/python scripts/ui_test_app.py [base_url]
Screenshots: sim/out/app_<case>.png. Exit code 1 if any check fails.
"""
import csv
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5174/").rstrip("/") + "/"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sim/out"
OUT.mkdir(parents=True, exist_ok=True)
CORRIDOR = json.loads((ROOT / "data/corridor/corridor.json").read_text())
ORDER = [p["id"] for p in CORRIDOR["points"]]
TT_ROWS = list(csv.DictReader((ROOT / "data/raw/corridor_legs_tomtom.csv").open()))
TYPICAL = "2026-07-01..2026-07-31 6:00-23:00"
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}
PAGES = [("home", "index.html"), ("corridor", "corridor.html"), ("ymca", "ymca.html"), ("decisions", "decisions.html"), ("data", "data.html")]
sys.path.insert(0, str(ROOT / "backend"))
from app import weather as WX  # noqa: E402  (GET /weather/factors answered by the endpoint's own code on the repo's files)
WX_FACTORS = WX.weather_factors()
WX_NOW = {"time": "2026-10-10T00:15", "rain_mm_per_hour": 0.0, "is_raining": False, "rain_class": "dry", "what_if": "dry", "temperature_c": 26.6,
          "weather_code": 0, "is_day": True, "text": "Clear sky", "label": "modelled (Open-Meteo forecast), not a rain gauge",
          "location": {"name": "Khajaguda X Roads (corridor midpoint by distance)"}, "cached": False, "age_s": 0}
errors, results = [], []
case = ""


def check(ok, what):
    results.append((case, bool(ok), what))
    print(("  ok   " if ok else "  FAIL ") + what)


def sha(n):
    return (f"{n:02x}" * 32)[:64]


# ---------------- fixtures: the backend's shapes (contracts/api.md, 9 Oct) ----------------
def periods():
    out = []
    for per in [TYPICAL, "2026-07-05..2026-07-05 8:00-20:00", "2026-07-08..2026-07-08 8:00-20:00"]:
        legs = [{"from_id": r["from_id"], "to_id": r["to_id"], "from_name": r["from"], "to_name": r["to"], "distance_m": float(r["distance_m"]),
                 "time_s": float(r["time_s"]), "speed_kmh": float(r["speed_kmh"])} for r in TT_ROWS if r["period"] == per]
        label = {TYPICAL: "Typical July day (06-23)"}.get(per, ("Sun 5 Jul, 08-20" if "07-05" in per else "Wed 8 Jul, 08-20"))
        out.append({"period": per, "label": label, "kind": "average" if per == TYPICAL else "day", "date_from": per[:10], "date_to": per[12:22],
                    "legs": legs, "total_s": round(sum(x["time_s"] for x in legs), 1), "distance_m": round(sum(x["distance_m"] for x in legs))})
    return out


PERIODS = periods()
TYPICAL_LEGS = PERIODS[0]["legs"]
CORRIDOR_API = dict(CORRIDOR, tomtom={"source": "test", "periods": PERIODS}, labels={})


def live():
    t = "2026-10-09T17:17:58+05:30"
    ap = lambda name, d, u, q, v: {"approach_id": name, "name": name, "delay_s": d, "usual_delay_s": u, "queue_m": q, "volume_per_hour": v, "time": t, "stale": False}
    return {"source": "TomTom Junction Analytics (test)", "window_minutes": 60,
            "labels": {"delay_s": "measured", "queue_m": "estimated", "volume_per_hour": "estimated"}, "junctions": [
        {"id": "j07", "name": "Tolichowki", "tomtom_id": "t7", "time": t, "age_s": 20, "approaches": [ap("Mumbai Road East Bound", 19, 15, 0, 3586), ap("Hakimpet Road South Bound", 20, 20, 106, 1183)]},
        {"id": "j08", "name": "Nanal Nagar jn", "tomtom_id": "t8", "time": t, "age_s": 20, "approaches": [ap("NH163 North Bound", 108, 80, 149, 1911), ap("Mumbai Road East Bound", 73, 17, 131, 4933)]},
        {"id": "j09", "name": "Rethibowli jn", "tomtom_id": "t9", "time": t, "age_s": 1500, "approaches": [ap("Mandela Gudem Road North Bound", 178, 131, 297, 341), ap("Mumbai Road East Bound", 103, 88, 379, 4540)]}]}


def run_row(rid, n, option_ivs, total_min, role="option", by="engineer", vol=1.0, sample=False):
    return {"run_id": rid, "role": role, "added_by": by, "option": "raw option text", "interventions": option_ivs, "volume_scale": vol,
            "total_min": total_min, "inputs": {"label": "estimated", "volume_scale": vol}, "warnings": ["test warning: lanes merge"] if option_ivs else [],
            "sample": sample, "fingerprint": sha(n)}


FLY = [{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2, "length_m": 600}}]
RETIME = [{"junction_id": "j07", "kind": "signal_retime", "params": {"cycle_s": 90, "corridor_green_share": 0.65}}]
WIDEN = [{"junction_id": "j05", "kind": "widening", "params": {"add_lanes": 1, "length_m": 300}}]


def events(cid, kinds, broken=False):
    out, prev = [], None
    for seq, (kind, actor, body, created) in enumerate(kinds):
        fp = sha(40 + seq + (10 if cid == "c_2" else 0))
        out.append({"seq": seq, "kind": kind, "actor": actor, "body": body, "fingerprint": fp, "prev": ("ff" * 32 if broken and seq else prev), "created": created})
        prev = fp
    return out


CASES = {
    "c_1": {"case_id": "c_1", "title": "Widen Khajaguda approach", "stage": "proposed", "brief_id": None, "created_by": "Planner K.", "created": 1791550000.0,
            "runs": [run_row("r1a", 1, [], 98.0), run_row("r1b", 2, WIDEN, 96.5)], "decision": None},
    "c_2": {"case_id": "c_2", "title": "Signal retime at Tolichowki", "stage": "in_review", "brief_id": "b_missing", "created_by": "Asha", "created": 1791556000.0,
            "runs": [run_row("r2a", 3, [], 98.0), run_row("r2b", 4, RETIME, 96.0)], "decision": None},
    "c_3": {"case_id": "c_3", "title": "Flyover at Tolichowki", "stage": "decided", "brief_id": "b_1", "created_by": "engineer", "created": 1791553000.0,
            "runs": [run_row("r3a", 5, [], 97.5, sample=True), run_row("r3b", 6, FLY, 93.8, sample=True),
                     run_row("r3c", 7, [], 117.0, role="review", by="reviewer"), run_row("r3d", 8, FLY, 113.2, role="review", by="reviewer")]},
}
CASES["c_1"]["events"] = events("c_1", [("proposed", "Planner K.", {"title": "Widen Khajaguda approach", "runs": {"r1a": sha(1), "r1b": sha(2)}}, 1791550000.0)])
CASES["c_2"]["events"] = events("c_2", [("proposed", "Asha", {"title": "Signal retime at Tolichowki", "runs": {"r2a": sha(3), "r2b": sha(4)}}, 1791556000.0),
                                       ("review", "Ravi", {"volume_scale": 0.8, "note": "quiet hours", "results": []}, 1791556100.0)], broken=True)
CASES["c_3"]["events"] = events("c_3", [
    ("proposed", "engineer", {"title": "Flyover at Tolichowki", "brief_id": "b_1", "runs": {"r3a": sha(5), "r3b": sha(6)}}, 1791553000.0),
    ("review", "Asha (traffic police)", {"volume_scale": 1.2, "note": "peak +20%", "results": [
        {"run_id": "r3c", "option": "baseline (no change)", "total_min": 117.0, "change_vs_baseline_min": 0.0, "fingerprint": sha(7)},
        {"run_id": "r3d", "option": "flyover at j07 Tolichowki", "total_min": 113.2, "change_vs_baseline_min": -3.8, "fingerprint": sha(8)}]}, 1791553600.0),
    ("decision", "Commissioner R.", {"decision": "approve", "reason": "Retime first; flyover only if the queue persists", "evidence": {}}, 1791554200.0)])
CASES["c_3"]["decision"] = {"decision": "approve", "reason": "Retime first; flyover only if the queue persists"}
for c in CASES.values():
    c["fingerprints"] = {r["run_id"]: r["fingerprint"] for r in c["runs"]}
    c["fingerprint"] = c["events"][-1]["fingerprint"]
CASES["c_3"]["fingerprints"]["brief:b_1"] = sha(9)
CASE_LIST = [{k: c[k] for k in ("case_id", "title", "stage", "brief_id", "created_by", "created")} | {"runs": len(c["runs"])} for c in CASES.values()]
BRIEF = {"brief_id": "b_1", "markdown": "# Decision brief: Tolichowki\n\n**Recommendation:** retime first.\n\n1. Evidence one\n2. Evidence two\n\n"
         "| Option | Trip |\n|---|---|\n| Flyover | 93.8 min |\n\n<img src=x onerror=\"window.__xss=1\"><script>window.__xss=2</script>",
         "run_ids": ["r3a", "r3b"], "fingerprints": {"r3a": sha(5), "r3b": sha(6)}, "fingerprint": sha(9), "created_at": "2026-10-09T19:05:00+05:30"}
FACT = [1.01, 1.02, 0.86, 1.05, 0.98, 1.03, 1.0, 0.97, 0.91, 1.02, 0.99, 1.01]
CAL_LEGS = [{"leg": f"{l['from_id']}->{l['to_id']}", "sim_s": round(l["time_s"] * f), "tomtom_s": round(l["time_s"]), "ratio": f} for l, f in zip(TYPICAL_LEGS, FACT)]
CALIBRATION = {
    "target": "TomTom Traffic Stats job 10051304 (test)", "cap_kmh": [23.6, 29.8, 44.1, 43.3, 36.4, 45.2, 50.8, 29.1, 56.4, 23.0, 33.4, 25.5],
    "green_share": {"j03": 0.65, "j07": 0.8}, "through_vph": {"fwd": 1170, "rev": 1170}, "cross_scale": 0.405, "signal_cycle_s": 120,
    "knobs": {"cap_kmh": "calibrated: speed cap per leg standing in for side friction", "green_share": "calibrated: corridor share of the green time",
              "through_vph": "calibrated: end-to-end corridor traffic per direction, lowered 10% at a time while a leg stays too slow",
              "cross_scale": "calibrated as through_vph: share of TomTom's cross-road volumes", "signal_cycle_s": "assumed: 120 s cycle everywhere"},
    "result": {"sim_total_s": sum(x["sim_s"] for x in CAL_LEGS), "tomtom_total_s": sum(x["tomtom_s"] for x in CAL_LEGS), "legs": CAL_LEGS, "total_s_se": 21.5, "probes_arrived": 30,
               "junction_delays": {"j07": {"sim_s": 62.6, "target_s": 13.7}, "j03": {"sim_s": 47.8, "target_s": 70.0}, "j09": {"sim_s": 36.2, "target_s": 41.5}},
               "corridor_volumes": [{"junction_id": "j07", "direction": "A->B", "road": "Mumbai Road East Bound", "tomtom_vph": 3502, "sim_vph": 1956, "label": "estimated"},
                                    {"junction_id": "j08", "direction": "A->B", "road": "Mumbai Road East Bound", "tomtom_vph": 5062, "sim_vph": 1880, "label": "estimated"}],
               "inputs": [{"input": "leg travel times (calibration target)", "label": "counted", "source": "TomTom Traffic Stats"},
                          {"input": "cross-road volumes at j07", "label": "estimated", "source": "TomTom Junction Analytics"},
                          {"input": "signal plans", "label": "assumed", "source": "120 s cycle"},
                          {"input": "vehicle mix", "label": "assumed", "source": "two_wheeler 45%, car 30%"},
                          {"input": "end-to-end corridor volume", "label": "calibrated", "source": "set to match TomTom"}]},
    "calibrated_at": "2026-10-09T19:12:29+0530"}
SIM_TOTAL, TT_TOTAL = CALIBRATION["result"]["sim_total_s"], CALIBRATION["result"]["tomtom_total_s"]
INIT_JS = "window.print = () => { window.__printed = (window.__printed || 0) + 1; window.__printClass = document.body.className; };"


class Backend:
    """The API answered in the browser. health: 'real' | 'mock' | 'none' (404 -> /config decides); offline aborts every call."""

    def __init__(self, health="real", offline=False, calibration=True, wx_now=WX_NOW):
        self.health, self.offline, self.calibration, self.calls, self.wx_now = health, offline, calibration, [], wx_now

    def reply(self, route, status=200, body=None):
        if body is None:
            return route.fulfill(status=status, headers=CORS, body="not here")
        route.fulfill(status=status, headers=CORS, content_type="application/json", body=json.dumps(body))

    def handle(self, route):
        req = route.request
        if self.offline:
            return route.abort()
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        path = urlparse(req.url).path
        self.calls.append(path)
        if path == "/health":
            return self.reply(route, 404) if self.health == "none" else self.reply(route, body={"status": "ok", "mock": self.health == "mock"})
        if path == "/config":
            return self.reply(route, body={"tomtom_maps_key": "", "mock": self.health == "mock", "junction": {"id": "ymca_circle", "name": "YMCA Circle", "lon": 78.4903, "lat": 17.3954}})
        if path == "/corridor":
            return self.reply(route, body=CORRIDOR_API)
        if path == "/corridor/junctions/live":
            return self.reply(route, body=live())
        if path == "/corridor/calibration":
            return self.reply(route, body=CALIBRATION) if self.calibration else self.reply(route, 404)
        if path == "/corridor/cases":
            return self.reply(route, body=CASE_LIST)
        if path.startswith("/corridor/cases/"):
            cid = path.rsplit("/", 1)[-1]
            return self.reply(route, body=CASES[cid]) if cid in CASES else self.reply(route, 404)
        if path.startswith("/briefs/"):
            return self.reply(route, body=BRIEF) if path.endswith("/b_1") else self.reply(route, 404)
        if path == "/weather/now":   # 503 when Open-Meteo cannot be reached
            return self.reply(route, body=self.wx_now) if self.wx_now else self.reply(route, 503, {"detail": "current weather unavailable (test)"})
        if path == "/weather/factors":
            return self.reply(route, body=WX_FACTORS)
        return self.reply(route, 404)


def open_page(b, page, backend=None, viewport=(1500, 950), hash_="", wait=1500):
    pg = b.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    pg.on("pageerror", lambda e: errors.append(f"[{case}] {page}: {e}"))
    pg.add_init_script(INIT_JS)
    if backend:
        pg.route("http://localhost:8000/**", backend.handle)
    pg.route("**/data/corridor/buildings/*.geojson", lambda r: r.fulfill(status=404, headers=CORS, body="none"))
    pg.goto(BASE + page + hash_, wait_until="load", timeout=60000)
    pg.wait_for_function("() => document.getElementById('cr-nav') && document.querySelector('#cr-nav .crn-pill').dataset.state !== 'checking'", timeout=20000)
    pg.wait_for_timeout(wait)
    return pg


def wait_for(pg, js, seconds=10):
    try:
        pg.wait_for_function(js, timeout=seconds * 1000)
        return True
    except Exception:
        return False


def rect(pg, sel):
    return pg.evaluate(f"() => {{ const e = document.querySelector({json.dumps(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }}")


def api_get(path):
    try:
        with urllib.request.urlopen("http://localhost:8000" + path, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


UNDER_BAR = {"home": ["main"], "corridor": ["#map", "#left", "#right", "#ask-open", ".maplibregl-ctrl-top-right"],
             "ymca": ["#map", "#left", "#right"], "decisions": ["main"], "data": ["main"]}

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])

    # ---------------- A: the bar on every page ----------------
    case = "A nav"; print(case)
    for pid, page in PAGES:
        pg = open_page(b, page, Backend(), wait=2500 if pid in ("corridor", "ymca") else 800)
        links = pg.eval_on_selector_all("#cr-nav .crn-links a", "els => els.map(e => [e.getAttribute('href'), e.querySelector('.crn-long').textContent, e.getAttribute('aria-current')])")
        check([l[0] for l in links] == [x[1] for x in PAGES] and [l[1] for l in links] == ["Home", "Corridor", "YMCA close-up", "Decisions", "About the data"],
              f"{pid}: 5 links in order: {[l[1] for l in links]}")
        check([l[0] for l in links if l[2] == "page"] == [page], f"{pid}: current page marked: {[l[0] for l in links if l[2] == 'page']}")
        check(pg.inner_text("#cr-nav .crn-brand").strip() == "Terascope AI" and pg.get_attribute("#cr-nav .crn-brand", "href") == "index.html", f"{pid}: wordmark links home")
        pill = pg.eval_on_selector("#cr-nav .crn-pill", "e => [e.dataset.state, e.innerText, e.title]")
        check(pill[0] == "real" and pill[1] == "Real simulation", f"{pid}: pill {pill[:2]}")
        nav = rect(pg, "#cr-nav")
        under = {s: rect(pg, s) for s in UNDER_BAR[pid]}
        check(nav[1] == 0 and 40 <= nav[3] <= 48 and all(r and r[1] >= nav[3] - 0.5 for r in under.values()),
              f"{pid}: bar {nav[3]:.0f} px; below it: {', '.join(f'{s} {r[1]:.0f}' if r else f'{s} missing' for s, r in under.items())}")
        if pid == "corridor":
            left = rect(pg, "#left")
            check(left[3] <= 950 - 11, f"corridor: left panel ends inside the window ({left[3]:.0f} of 950)")
            z = pg.evaluate("() => [document.elementFromPoint(innerWidth - 30, 70)?.closest('.maplibregl-ctrl, #right') ? 1 : 0, getComputedStyle(document.getElementById('cr-nav')).position]")
            check(z == [1, "fixed"], f"corridor: map controls / layers panel clickable just under the bar; bar fixed: {z}")
            pg.screenshot(path=str(OUT / "app_A_corridor.png"))
        if pid == "home":
            pg.click("#cr-nav a[data-page=decisions]")
            pg.wait_for_load_state("load")
            check(pg.url.endswith("decisions.html") and pg.get_attribute("#cr-nav a[aria-current=page]", "href") == "decisions.html", f"clicking Decisions opens it: {pg.url}")
        pg.close()

    # ---------------- B: status pill ----------------
    case = "B pill"; print(case)
    for be, want, text in ((Backend(health="mock"), "mock", "Mock: sample data"), (Backend(health="none"), "real", "Real simulation"), (Backend(offline=True), "offline", "API offline")):
        pg = open_page(b, "index.html", be, wait=300)
        st = pg.eval_on_selector("#cr-nav .crn-pill", "e => [e.dataset.state, e.innerText, e.title, window.crNav.state]")
        check(st[0] == want and st[1] == text and st[3] == want and st[2], f"{want}: {st[1]!r} ({st[2][:60]})")
        if want == "real":
            check("/config" in be.calls and "/health" in be.calls, "no /health: /config decides")
        pg.close()

    # ---------------- C: home, mocked ----------------
    case = "C home"; print(case)
    be = Backend()
    pg = open_page(b, "index.html", be)
    wait_for(pg, "() => document.getElementById('lv-worst') && /Decision|case/.test(document.getElementById('d-line').innerText)")
    pitch = pg.inner_text("#pitch")
    check(all(w in pitch for w in ("Predict", "mitigate", "low-cost", "build", "tested", "reviewed and recorded")), f"pitch: {pitch[:90]}")
    check(pg.inner_text("#c-min") == "58 min" and pg.inner_text("#c-km") == "22.4 km" and pg.inner_text("#c-jn") == "11", f"corridor card: {pg.inner_text('#c-min')}, {pg.inner_text('#c-km')}, {pg.inner_text('#c-jn')} junctions")
    check(pg.eval_on_selector_all("#c-legs span", "els => els.length") == 12 and "REAL" in pg.inner_text("#card-corridor") and "Typical July day" in pg.inner_text("#c-src"),
          "12 coloured legs, REAL, labelled from the API")
    check(pg.get_attribute("#card-corridor", "href") == "corridor.html" and pg.get_attribute("#card-ymca", "href") == "ymca.html" and pg.get_attribute("#card-decisions", "href") == "decisions.html", "card links")
    check(pg.get_attribute("#live-map", "href") == "corridor.html#mode=live" and pg.is_visible("#live-map"), "live strip links to the corridor's Live now")
    lv = pg.inner_text("#live")
    check("REAL" in lv and "3 TomTom junctions reporting" in lv and "1 not updated for 15+ min" in lv and "updated 17:17" in lv, f"live strip: {lv[:140]!r}")
    check("178 s" in pg.inner_text("#lv-worst") and "Mandela Gudem Road North Bound at Rethibowli jn" in pg.inner_text("#lv-worst") and "usually 131 s" in pg.inner_text("#lv-worst"),
          f"worst delay now: {pg.inner_text('#lv-worst')}")
    check(pg.inner_text("#c-live") == "3", "corridor card: 3 with live data")
    check(pg.inner_text("#d-count") == "3" and "Signal retime at Tolichowki" in pg.inner_text("#d-line") and pg.inner_text("#d-stage") == "In review", f"decisions card: {pg.inner_text('#d-line')[:90]!r}")
    check(pg.eval_on_selector_all(".steps li h3", "els => els.map(e => e.textContent)") == ["Predict", "Mitigate first", "Build what was tested, on the record"], "How it works: 3 steps")
    check(pg.get_attribute("footer a", "href") == "data.html", "footer links About the data")
    wx = pg.inner_text("#wx-now") if pg.is_visible("#wx-now") else ""
    check("Weather now: Clear sky · 27°C" in wx and "modelled" in wx and "not a rain gauge" in (pg.get_attribute("#wx-now", "title") or "") and pg.locator("#wx-now svg").count() == 1,
          f"weather now in the live strip (GET /weather/now), modelled: {wx!r}")
    pg.screenshot(path=str(OUT / "app_C_home.png"), full_page=True)
    pg.close()
    pg = open_page(b, "index.html", Backend(wx_now=None))
    wait_for(pg, "() => document.getElementById('lv-worst')")
    check(pg.is_hidden("#wx-now") and "Weather" not in pg.inner_text("#live"), "GET /weather/now 503: no weather chip")
    pg.close()

    # ---------------- D: decisions, mocked ----------------
    case = "D decisions"; print(case)
    be = Backend()
    pg = open_page(b, "decisions.html", be)
    rows = pg.eval_on_selector_all("#cases .case-row", "els => els.map(e => [e.dataset.case, e.querySelector('.t').textContent, e.querySelector('.stage').textContent, e.querySelector('.m').textContent])")
    check([r[0] for r in rows] == ["c_2", "c_3", "c_1"], f"newest first: {[r[0] for r in rows]}")
    check(rows[0][2] == "In review" and "Proposed by Asha" in rows[0][3] and "9 Oct 2026" in rows[0][3] and "2 runs" in rows[0][3], f"row: {rows[0]}")
    f = pg.eval_on_selector_all("#filters button", "els => els.map(e => e.innerText.replace(/\\s+/g, ' ').trim())")
    check(f == ["All 3", "Proposed 1", "In review 1", "Decided 1"], f"stage filters with counts: {f}")
    pg.click("#filters button[data-stage=decided]")
    check(pg.eval_on_selector_all("#cases .case-row", "els => els.map(e => e.dataset.case)") == ["c_3"] and pg.url.endswith("#stage=decided")
          and pg.get_attribute("#filters button[data-stage=decided]", "aria-pressed") == "true", "filter Decided: one case, #stage=decided")
    pg.click("#cases .case-row[data-case=c_3]")
    check(wait_for(pg, "() => document.getElementById('d-title')?.textContent === 'Flyover at Tolichowki'"), "case detail opens")
    check(pg.url.endswith("#case=c_3") and pg.is_hidden("#list-view"), "URL #case=c_3, list hidden")
    check(pg.inner_text(".stages li[aria-current=step]") == "Decided" and pg.locator(".stages li.done").count() == 2, "stage tracker: Decided")
    v = pg.inner_text("#verdict")
    check("Approved by Commissioner R." in v and "Retime first; flyover only if the queue persists" in v and "append-only" in v, f"verdict: {v[:100]!r}")
    tl = pg.eval_on_selector_all("#timeline .tl > li", "els => els.map(e => [e.dataset.kind, e.innerText])")
    check([t[0] for t in tl] == ["proposed", "review", "decision"], f"timeline proposed -> review -> decision: {[t[0] for t in tl]}")
    check("PROPOSED" in tl[0][1].upper() and "engineer" in tl[0][1] and "Sent for review: Flyover at Tolichowki with 2 runs as evidence and brief b_1" in tl[0][1], f"proposed: {tl[0][1][:120]!r}")
    check("Asha (traffic police)" in tl[1][1] and "Re-tested every option at 120% traffic" in tl[1][1] and "peak +20%" in tl[1][1] and "−3.8 min vs today's roads" in tl[1][1], f"review: {tl[1][1][:160]!r}")
    check("Commissioner R." in tl[2][1] and "Approved: “Retime first" in tl[2][1] and "9 Oct 2026" in tl[2][1], f"decision: {tl[2][1][:120]!r}")
    check(pg.locator("#timeline .chain-ok").count() == 2 and "first event" in tl[0][1], "each event follows the previous one (✓)")
    runs = pg.eval_on_selector_all("#runs tr[data-run]", "els => els.map(e => [...e.cells].map(c => c.innerText.replace(/\\s+/g, ' ').trim()))")
    check(len(runs) == 4 and runs[1][0].startswith("Flyover at Tolichowki (2 lanes, 600 m)") and "proposed option" in runs[1][0], f"runs in words: {[r[0][:40] for r in runs]}")
    check([r[1] for r in runs] == ["100%", "100%", "120%", "120%"], f"traffic levels (the review's 120% for its re-runs): {[r[1] for r in runs]}")
    check([r[2] for r in runs] == ["97.5 min", "93.8 min", "117.0 min", "113.2 min"] and runs[1][3] == "−3.7 min" and runs[3][3] == "−3.8 min" and runs[0][3] == "–", f"trip minutes and change vs today: {[(r[2], r[3]) for r in runs]}")
    check("SAMPLE DATA" in runs[0][0] and "SAMPLE DATA" not in runs[2][0] and "reviewer's re-test" in runs[2][0], "sample runs tagged, re-tests named")
    fps = pg.eval_on_selector_all("#runs .fp", "els => els.map(e => [e.textContent, e.title])")
    check(len(fps) == 4 and fps[0][0] == sha(5)[:10] and fps[0][1] == "SHA-256 " + sha(5), f"short fingerprints, full on hover: {fps[0]}")
    ev = pg.inner_text("#evidence")
    check("previous event's fingerprint" in ev and "chain" in ev and "Chain links intact" in ev and pg.locator("#evidence .fp").count() == 6, f"evidence: chain explained, intact, 6 fingerprints ({pg.locator('#evidence .fp').count()})")
    check("Brief b_1" in pg.inner_text("#evidence"), "brief fingerprint listed")
    check(wait_for(pg, "() => /Decision brief: Tolichowki/.test(document.getElementById('brief-body').innerText)"), "brief loaded")
    bb = pg.locator("#brief-body")
    check(bb.locator(".md-h").first.inner_text() == "Decision brief: Tolichowki" and bb.locator("b").first.inner_text() == "Recommendation:" and bb.locator("ol li").count() == 2
          and bb.locator("table tr").count() == 2, "brief markdown: heading, bold, list, table")
    check(bb.locator("img, script").count() == 0 and pg.evaluate("() => window.__xss") is None and "<img src=x" in bb.inner_text(), "HTML in the brief shown as text, not run")
    check(pg.is_visible("#brief-print"), "Print brief button")
    pg.click("#brief-print")
    check(pg.evaluate("() => [window.__printed, window.__printClass.split(' ').includes('print-brief')]") == [1, True], "Print brief prints with only the brief selected")
    pg.wait_for_timeout(700)
    check(not pg.evaluate("() => document.body.classList.contains('print-brief')"), "after printing, the page prints whole again")
    shown = "() => ['#brief-card', '#brief-body', '#tl-card', '#runs-card', '#ev-card', '#d-card', '#cr-nav', '#brief-print'].map(s => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none' && e.offsetParent !== null; })"
    pg.emulate_media(media="print"); pg.evaluate("() => document.body.classList.add('print-brief')")
    check(pg.evaluate(shown) == [True, True, False, False, False, False, False, False], f"printed brief: only the brief, no bar or buttons ({pg.evaluate(shown)})")
    pg.evaluate("() => document.body.classList.remove('print-brief')")
    check(pg.evaluate(shown)[:6] == [True, True, True, True, True, True] and not pg.evaluate(shown)[6], "printed record: the whole case, no top bar")
    pg.emulate_media(media="screen")
    check(pg.evaluate("() => [...document.styleSheets].flatMap(x => { try { return [...x.cssRules]; } catch (e) { return []; } }).some(r => r.media && r.media.mediaText === 'print' && /print-brief/.test(r.cssText))"), "print stylesheet for the brief")
    check(pg.get_attribute("#open-corridor", "href") == "corridor.html#case=c_3", "Open in corridor link")
    pg.screenshot(path=str(OUT / "app_D_detail.png"), full_page=True)
    pg.click("#back")
    check(wait_for(pg, "() => !document.getElementById('list-view').hidden && document.getElementById('detail-view').hidden") and pg.url.endswith("#stage=decided"), "back to the list (filter kept)")
    pg.goto(BASE + "decisions.html#case=c_2"); pg.wait_for_timeout(1200)
    check("chain is broken" in pg.inner_text("#evidence") and pg.locator("#timeline .chain-bad").count() == 1, "a broken chain is shown as broken")
    check("not on this server" in pg.inner_text("#brief-body"), f"missing brief: {pg.inner_text('#brief-body')[:60]}")
    check("Re-tested every option at 80% traffic" in pg.inner_text("#timeline") and pg.inner_text(".stages li[aria-current=step]") == "In review", "in-review case")
    pg.goto(BASE + "decisions.html#case=c_1"); pg.wait_for_timeout(1000)
    check(pg.is_hidden("#verdict") if pg.locator("#verdict").count() else True, "proposed case: no verdict")
    check("No decision brief" in pg.inner_text("#brief-body") and "Road widening at Khajaguda X Roads (+1 lane, 300 m)" in pg.inner_text("#runs"), "no brief noted; widening in words")
    pg.goto(BASE + "decisions.html#case=nope"); pg.wait_for_timeout(1000)
    check("Case nope is not on this server" in pg.inner_text("#d-card"), "unknown case says so")
    pg.close()

    # ---------------- E: corridor deep link ----------------
    case = "E deep link"; print(case)
    pg = open_page(b, "corridor.html", Backend(), hash_="#case=c_3", wait=2500)
    check(wait_for(pg, "() => !document.getElementById('case').hidden && /Flyover at Tolichowki/.test(document.querySelector('#case .case-hd').innerText)"), "corridor.html#case=c_3 opens the case in step 4")
    check(pg.inner_text("#case .stages li.now") == "Decided" and pg.locator("#case .tl li").count() == 3, "with its stage and record")
    check(pg.get_attribute("#mode-july", "aria-selected") == "true" and pg.is_visible("#dec"), "a case link opens in July typical day (where decisions are)")
    pg.close()
    pg = open_page(b, "corridor.html", Backend(), hash_="#mode=live", wait=2500)
    check(pg.get_attribute("#mode-live", "aria-selected") == "true" and pg.is_visible("#live-box") and pg.is_hidden("#journey"), "corridor.html#mode=live opens Live now")
    pg.close()

    # ---------------- F: about the data, mocked ----------------
    case = "F data"; print(case)
    pg = open_page(b, "data.html", Backend())
    wait_for(pg, "() => document.getElementById('legs-table') && /corridor junctions/.test(document.getElementById('ja-key').innerText)")
    check(pg.locator("#real .tag.real, .sources .tag.real").count() >= 4 and "SIMULATED" in pg.inner_text("#tags + .legend") and "SAMPLE DATA" in pg.inner_text("#tags + .legend"), "tags explained: REAL, SIMULATED, SAMPLE DATA")
    labs = pg.eval_on_selector_all("#tags + .legend .lab", "els => els.map(e => e.textContent)")
    check(labs == ["counted", "measured", "estimated", "calibrated", "assumed"], f"input labels explained: {labs}")
    check(pg.inner_text("#ts-key").startswith("58 min") and "49 min (Sun 5 Jul" in pg.inner_text("#ts-range") and "65 min (Wed 8 Jul" in pg.inner_text("#ts-range"), f"Traffic Stats: {pg.inner_text('#ts-key')[:40]} / {pg.inner_text('#ts-range')[:110]}")
    check(pg.inner_text("#ja-key").startswith("3") and pg.locator("#ja-chips span").count() == 3 and pg.locator("#ja-chips span.old").count() == 1 and "17:17" in pg.inner_text("#ja-note"), f"Junction Analytics live: {pg.inner_text('#ja-key')}")
    for sid, words in (("src-osm", "OpenStreetMap"), ("src-buildings", "assumed"), ("src-rain", "low to moderate"), ("src-rain", "same day")):
        check(words in pg.inner_text(f"#{sid}"), f"{sid}: mentions {words!r}")
    check(wait_for(pg, "() => document.getElementById('rain-legs-table')"), "rain: per-stretch table from GET /weather/factors")
    h = WX_FACTORS["headline"]
    heads = pg.inner_text("#rain-heads")
    check(pg.inner_text("#rain-any").startswith(f"+{h['any_rain']['pct']}%") and f"95% range +{h['any_rain']['ci95_pct'][0]}% to +{h['any_rain']['ci95_pct'][1]}%" in heads
          and f"+{h['sustained']['moderate']['pct']}%" in heads and "only 34 such hours" in heads and "low to moderate" in heads, f"rain headline, hour by hour, with ranges: {heads[:160]!r}")
    rows = pg.eval_on_selector_all("#rain-legs-table tr[data-leg]", "els => els.map(e => [e.dataset.leg, e.className, e.cells[0].textContent])")
    clear = [r[0] for r in rows if r[1] == "clear"]
    check(len(rows) == 12 and clear == ["j01-j02", "j03-j04", "j05-j06"] and rows[1][2] == "Nallagandla Rd jn → ISB Rd / DLF jn",
          f"12 stretches, the 3 slower in light rain beyond chance marked: {clear}")
    check("21% slower" not in pg.inner_text("#src-rain") and "≈ +5%" not in pg.inner_text("#src-rain"), "the old daily '+5%' first look is gone from the card")
    legs = pg.eval_on_selector_all("#legs-table tr[data-leg]", "els => els.map(e => [...e.cells].slice(0, 4).map(c => c.textContent))")
    check(len(legs) == 12 and legs[0][0] == "Lingampally → Nallagandla Rd jn" and legs[-1][0] == "Masab Tank → Lakdikapul", f"12 stretches named A -> B: {legs[0][0]} … {legs[-1][0]}")
    check(legs[2][3] == "−14%" and pg.eval_on_selector("#legs-table tr[data-leg='j02->j03'] td:nth-child(4)", "e => e.classList.contains('fair')"), f"difference coloured: {legs[2]}")
    tot = pg.inner_text("#legs-table tr:last-child")
    check("Whole trip" in tot and f"{TT_TOTAL / 60:.1f} min" in tot and f"{SIM_TOTAL / 60:.1f} min" in tot, f"whole trip row: {tot!r}")
    check(pg.inner_text("#cal-sim") == f"{SIM_TOTAL / 60:.1f} min" and pg.inner_text("#cal-tt") == f"{TT_TOTAL / 60:.1f} min" and "TomTom Traffic Stats job 10051304 (test)" in pg.inner_text("#cal-summary"), "summary: simulated vs TomTom, target")
    hon = pg.inner_text("#cal-honest")
    check("fewer vehicles" in hon and "46%" in hon and "lowered" in hon and "not as exact minutes" in hon, f"honest note: {hon[:150]!r}")
    kn = pg.eval_on_selector_all("#cal-knobs .knob", "els => els.map(e => [e.dataset.knob, e.querySelector('.lab').textContent, e.innerText])")
    check([k[0] for k in kn] == ["cap_kmh", "green_share", "through_vph", "cross_scale", "signal_cycle_s"] and [k[1] for k in kn] == ["calibrated"] * 4 + ["assumed"], f"knobs with labels: {[(k[0], k[1]) for k in kn]}")
    check("Tolichowki 80%" in kn[1][2] and "towards Lakdikapul 1170 vehicles/hour" in kn[2][2] and "41% of TomTom's estimate" in kn[3][2] and "Lingampally → Nallagandla Rd jn: 23.6 km/h" in kn[0][2], "knob values in words")
    jn = pg.eval_on_selector_all("#jn-table tr[data-j]", "els => els.map(e => [e.dataset.j, e.cells[3].textContent, e.cells[3].className])")
    check(jn == [["j03", "−32%", "n poor"], ["j07", "+357%", "n poor"], ["j09", "−13%", "n fair"]], f"junction delays sim vs TomTom: {jn}")
    check(pg.locator("#vol-table tr").count() == 3 and "estimated" in pg.inner_text("#cal-vol"), "volumes: TomTom (estimated) vs simulated")
    ins = pg.eval_on_selector_all("#inputs-table tr", "els => els.length")
    check(ins == 6 and "signal plans; vehicle mix" in pg.inner_text("#assumed-note") and pg.locator("#inputs-table .lab.assumed").count() == 2, f"inputs with labels, assumed listed: {pg.inner_text('#assumed-note')[:80]!r}")
    terms = pg.eval_on_selector_all("a.term", "els => els.map(e => e.getAttribute('href'))")
    check(terms and all(pg.locator(t).count() == 1 for t in set(terms)) and pg.locator("a[href*='docs/glossary.md']").count() == 1,
          f"glossary terms link to definitions, full glossary linked: {sorted(set(terms))}")
    pg.click("a.term[href='#g-calibration']"); pg.wait_for_timeout(400)
    r = rect(pg, "#g-calibration")
    check(r and r[1] >= 44, f"a glossary link scrolls the term into view below the bar ({r and round(r[1])} px)")
    pg.screenshot(path=str(OUT / "app_F_data.png"), full_page=True)
    pg.close()
    pg = open_page(b, "data.html", Backend(calibration=False))
    check(wait_for(pg, "() => document.getElementById('cal-off')") and "not been calibrated" in pg.inner_text("#cal-off") and "assumed" in pg.inner_text("#inputs"), f"calibration 404: {pg.inner_text('#cal-summary')[:80]!r}")
    pg.close()

    # ---------------- G: real API ----------------
    case = "G real API"; print(case)
    st, health = api_get("/health")
    if st != 200:
        print("      (API on :8000 not running: skipped)")
    else:
        _, cor = api_get("/corridor")
        _, lv = api_get("/corridor/junctions/live")
        _, cl = api_get("/corridor/cases")
        cst, cal = api_get("/corridor/calibration")
        pg = open_page(b, "index.html", None, wait=2500)
        want = "real" if health.get("mock") is False else "mock"
        check(pg.get_attribute("#cr-nav .crn-pill", "data-state") == want, f"pill matches /health: {want}")
        typ = next((x for x in cor["tomtom"]["periods"] if x.get("kind") == "average"), cor["tomtom"]["periods"][0])
        check(pg.inner_text("#c-min") == f"{round(typ['total_s'] / 60)} min", f"corridor minutes from the API: {pg.inner_text('#c-min')}")
        n = len([j for j in lv.get("junctions", []) if any(a.get("delay_s") is not None for a in j.get("approaches", []))]) if lv else 0
        check(wait_for(pg, "() => document.getElementById('lv-count')") and pg.inner_text("#lv-count").startswith(str(n)), f"live junctions reporting: {pg.inner_text('#live-body')[:80]!r} (API: {n})")
        check((pg.inner_text("#d-count") == str(len(cl))) if cl else "No cases" in pg.inner_text("#d-line"), f"cases: {pg.inner_text('#d-line')[:60]!r} (API: {len(cl or [])})")
        pg.screenshot(path=str(OUT / "app_G_home.png"), full_page=True)
        pg.close()
        pg = open_page(b, "decisions.html", None, wait=2000)
        check(pg.locator("#cases .case-row").count() == len(cl or []), f"decision list: {pg.locator('#cases .case-row').count()} rows")
        if cl:
            pg.click("#cases .case-row >> nth=0")
            check(wait_for(pg, "() => document.getElementById('d-title')") and pg.locator("#runs tr[data-run]").count() >= 1 and pg.locator("#timeline .tl > li").count() >= 1, "first case opens with runs and its record")
        pg.close()
        pg = open_page(b, "data.html", None, wait=3000)
        if cst == 200:
            check(pg.locator("#legs-table tr[data-leg]").count() == len(cal["result"]["legs"]) and pg.inner_text("#cal-sim") == f"{cal['result']['sim_total_s'] / 60:.1f} min",
                  f"calibration table from the API: {pg.locator('#legs-table tr[data-leg]').count()} stretches, {pg.inner_text('#cal-sim')}")
            check(pg.locator("#cal-knobs .knob").count() == len(cal.get("knobs", {})), "every calibrated knob listed")
        else:
            check(pg.locator("#cal-off").count() == 1, f"calibration {cst}: explained")
        pg.close()

    # ---------------- H: API offline ----------------
    case = "H offline"; print(case)
    for pid, page in PAGES:
        be = Backend(offline=True)
        pg = open_page(b, page, be, wait=2500 if pid in ("corridor", "ymca") else 1200)
        check(pg.get_attribute("#cr-nav .crn-pill", "data-state") == "offline", f"{pid}: pill says offline")
        if pid == "home":
            check(pg.inner_text("#c-min") == "58 min" and "saved copy" in pg.inner_text("#c-src") and pg.locator("#c-legs span").count() == 12, "home: saved TomTom numbers")
            check("not answering" in pg.inner_text("#live-body") and "not answering" in pg.inner_text("#d-line"), f"home: live and decisions explain: {pg.inner_text('#d-line')[:70]!r}")
            pg.screenshot(path=str(OUT / "app_H_home.png"))
        if pid == "decisions":
            check("not answering" in pg.inner_text("#cases") and pg.locator("#filters button").count() == 0, f"decisions: {pg.inner_text('#cases')[:70]!r}")
        if pid == "data":
            check("not answering" in pg.inner_text("#cal-off") and pg.inner_text("#ts-key").startswith("58 min") and "not answering" in pg.inner_text("#ja-note"), "data: written sources stay, live and calibration explain")
        if pid == "corridor":
            check("API not running" in pg.inner_text("#status") and pg.locator("#strips .strip[data-strip]").count() == 1, f"corridor: {pg.inner_text('#status')[:60]!r}")
        if pid == "ymca":
            check("API not running" in pg.inner_text("#status"), f"ymca: {pg.inner_text('#status')[:60]!r}")
        pg.close()

    # ---------------- N: phone ----------------
    case = "N phone"; print(case)
    for pid, page in PAGES:
        pg = open_page(b, page, Backend(), viewport=(390, 844), wait=2500 if pid in ("corridor", "ymca") else 1000)
        over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        nav = rect(pg, "#cr-nav")
        lk = pg.eval_on_selector_all("#cr-nav .crn-links a", "els => els.map(e => { const r = e.getBoundingClientRect(); return [e.innerText.trim(), r.left, r.right, r.top]; })")
        check(over <= 0 and 60 <= nav[3] <= 80 and [x[0] for x in lk] == ["Home", "Corridor", "YMCA", "Decisions", "Data"] and all(x[1] >= 0 and x[2] <= 390 for x in lk),
              f"{pid}: no sideways scroll ({over}), bar {nav[3]:.0f} px, short labels in view")
        first = {"home": "main", "corridor": "#map", "ymca": "#map", "decisions": "main", "data": "main"}[pid]
        r = rect(pg, first)
        check(r[1] >= nav[3] - 0.5 and pg.get_attribute("#cr-nav .crn-pill", "data-state") == "real" and pg.is_visible("#cr-nav .crn-pill"), f"{pid}: {first} starts below the bar ({r[1]:.0f} >= {nav[3]:.0f}), pill shown")
        if pid in ("home", "decisions", "data"):
            pg.screenshot(path=str(OUT / f"app_N_{pid}.png"))
        pg.close()
    b.close()

case = "K overall"
check(not errors, f"page errors: {errors or 'none'}")
print("\nSUMMARY")
for c in dict.fromkeys(r[0] for r in results):
    rs = [r for r in results if r[0] == c]
    print(f"  {c:14} {sum(r[1] for r in rs)}/{len(rs)} {'PASS' if all(r[1] for r in rs) else 'FAIL: ' + '; '.join(r[2] for r in rs if not r[1])}")
failed = [r for r in results if not r[1]]
print("RESULT:", "PASS" if not failed else f"FAIL ({len(failed)} of {len(results)} checks)")
sys.exit(1 if failed else 0)
