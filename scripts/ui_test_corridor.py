"""Headless browser test of the corridor view (frontend/corridor.html), clicked the way a user does.

Cases
  A  Load: no errors, 13 markers (A, 1..11, B), time choices with weekday names, TomTom strip (REAL), route drawn
  B  When: choosing a Sunday shortens the measured trip
  C  Changes: add, update (same junction and kind), add another, remove; markers highlight changed junctions
  D  Simulate today: journey strip from the API or the sample fallback, junction table, sample tag when sample
  E  Simulate with changes: third strip, total and per-leg deltas, knock-on, before/after table, warnings
  F  Camera: table row, map marker, strip block and "Whole corridor" move the map
  G  Layers: route and TomTom traffic on/off
  H  API path (corridor endpoints mocked in the browser): request body, no sample tag, vehicle playback from
     WS frames, play/pause, scrub, a 500 is shown as an error (no silent fallback)
  K  No page errors at any point

Usage (API on :8000 if available; repo root served on :5180):
    python3 -m http.server 5180 &        # from the repo root
    PLAYWRIGHT_BROWSERS_PATH=~/Library/Caches/ms-playwright .venv/bin/python scripts/ui_test_corridor.py [url]
Screenshots: sim/out/corridor_<case>.png. Exit code 1 if any check fails.
"""
import json
import math
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5180/frontend/corridor.html"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sim/out"
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = json.loads((ROOT / "contracts/samples/corridor_results.sample.json").read_text())
CORRIDOR = json.loads((ROOT / "data/corridor/corridor.json").read_text())
PTS = {p["id"]: p for p in CORRIDOR["points"]}
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
        pg.select_option(f"#iv-params select[data-k={k}]", str(v))
    pg.click("#iv-add")
    pg.wait_for_timeout(200)


def ivs(pg):
    return pg.eval_on_selector_all("#iv-list .iv span", "els => els.map(e => e.textContent)")


def simulate(pg, button, label):
    pg.click(button)
    pg.wait_for_timeout(50)
    st, dt = wait_status(pg, ["simulated", "rror", "failed", "answered"], 600)
    check("simulated" in st and label in st, f"{label}: {st} ({dt:.0f} s)")
    check(not pg.is_disabled("#sim-today") and not pg.is_disabled("#sim-changes"), "simulate buttons usable again")
    return st


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


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])

    # ---------------- the page against whatever API is running (corridor endpoints may 404: sample fallback) ----------------
    pg = b.new_page(viewport={"width": 1500, "height": 950})
    pg.on("pageerror", lambda e: errors.append(f"[{case}] {e}"))
    pg.goto(URL, wait_until="load", timeout=60000)
    pg.wait_for_function("() => typeof overlay !== 'undefined' && overlay && document.querySelectorAll('.pin').length > 0", timeout=30000)
    pg.wait_for_timeout(4000)

    case = "A load"; print(case)
    st = pg.inner_text("#status")
    check("API" in st and "error" not in st.lower(), f"status: {st}")
    pins = pg.eval_on_selector_all(".pin.maplibregl-marker", "els => els.map(e => e.textContent)")
    check(pins == ["A"] + [str(i) for i in range(1, 12)] + ["B"], f"13 markers: {pins}")
    whens = pg.eval_on_selector_all("#when option", "els => els.map(e => e.textContent)")
    check(len(whens) == 16 and whens[0].startswith("Typical July day") and pg.input_value("#when").startswith("2026-07-01..2026-07-31"), f"16 time choices, typical first: {whens[0]}")
    check(any(w.startswith("Sun 5 Jul") for w in whens) and any(w.startswith("Wed 1 Jul") for w in whens), f"weekday names: {whens[1]}, {whens[5]}")
    s = strips(pg)
    check(len(s) == 1 and s[0][0] == "tomtom" and s[0][1] == 12, f"TomTom strip with 12 legs before any run: {s}")
    check("REAL" in s[0][3] and s[0][2] == "58 min", f"measured strip tagged REAL, 58 min: {s[0][2]}")
    check(pg.evaluate("() => !!document.querySelector('#map canvas')"), "map canvas present")
    check(layer(pg, "route") == 12, f"route drawn as 12 legs: {layer(pg, 'route')}")
    z = pg.evaluate("() => map.getZoom()")
    check(10.5 < z < 13.5, f"map framed on the whole corridor (zoom {z:.1f})")
    pg.screenshot(path=str(OUT / "corridor_A.png"))

    case = "B when"; print(case)
    pg.select_option("#when", "2026-07-05..2026-07-05 8:00-20:00"); pg.wait_for_timeout(300)
    s = strips(pg)
    check(s[0][2] == "49 min" and "Sun 5 Jul" in s[0][3], f"Sunday 5 Jul: {s[0][2]}, {s[0][3]}")
    check("Sundays (5 and 12 Jul)" in pg.inner_text("#when-note"), f"note: {pg.inner_text('#when-note')[:110]}")
    pg.select_option("#when", "2026-07-08..2026-07-08 8:00-20:00"); pg.wait_for_timeout(300)
    check(strips(pg)[0][2] == "65 min", f"Wed 8 Jul weekday: {strips(pg)[0][2]}")

    case = "C changes"; print(case)
    check(pg.eval_on_selector_all("#iv-params select", "els => els.map(e => e.dataset.k)") == ["lanes", "length_m"], "flyover asks for lanes and length")
    pg.select_option("#iv-kind", "signal_retime"); pg.wait_for_timeout(100)
    check(pg.eval_on_selector_all("#iv-params select option", "els => els.map(e => e.value)") == ["90", "120", "150"], "signal timing offers 90/120/150 s")
    add_iv(pg, "j07", "flyover", {"lanes": 3, "length_m": 400})
    add_iv(pg, "j03", "signal_retime", {"cycle_s": 150})
    add_iv(pg, "j07", "flyover", {"lanes": 2, "length_m": 600})
    v = ivs(pg)
    check(len(v) == 2 and "3 · Gachibowli Circle: Signal timing, 150 s cycle" in v[0] and "2 lanes, 600 m" in v[1], f"list in corridor order, j07 updated not duplicated: {v}")
    check(pg.eval_on_selector_all(".pin.has", "els => els.map(e => e.textContent)") == ["3", "7"], "markers 3 and 7 highlighted")
    pg.locator("#iv-list .iv", has_text="Gachibowli").locator("button").click(); pg.wait_for_timeout(200)
    check(len(ivs(pg)) == 1 and pg.eval_on_selector_all(".pin.has", "els => els.map(e => e.textContent)") == ["7"], f"removed: {ivs(pg)}")

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

    # ---------------- H: corridor API answering (mocked in the browser) with frames to play ----------------
    case = "H api + playback"; print(case)
    pg = b.new_page(viewport={"width": 1500, "height": 950})
    pg.on("pageerror", lambda e: errors.append(f"[{case}] {e}"))
    bodies, mode = [], {"fail": False}
    CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}

    def corridor_runs(route):
        if route.request.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        body = json.loads(route.request.post_data or "{}")
        bodies.append(body)
        if mode["fail"]:
            return route.fulfill(status=500, body="simulation failed: test")
        r = json.loads(json.dumps(SAMPLE["flyover_j07" if body.get("interventions") else "baseline"]))
        r.pop("sample", None)
        r["run_id"] = "r_test_" + r["variant_id"]
        r["frames_path"] = "test"
        r["inputs"] = {"counts_source": "test", "label": "estimated", "volume_scale": 1.0}
        route.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(r))

    pg.route("http://localhost:8000/corridor/runs", corridor_runs)
    pg.route("http://localhost:8000/corridor", lambda r: r.fulfill(status=200, content_type="application/json", headers=CORS, body=json.dumps(CORRIDOR)))
    pg.route("http://localhost:8000/runs/*/roads", lambda r: r.fulfill(status=404, headers=CORS, body="no roads"))

    # WS /stream/{run_id}: a stand-in socket that replays synthetic frames (page.route_web_socket hangs in the sync API here)
    pg.add_init_script("""(() => {
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
    })();""" % json.dumps(frames_along("j07", "j08")))
    pg.goto(URL, wait_until="load", timeout=60000)
    pg.wait_for_function("() => typeof overlay !== 'undefined' && overlay && document.querySelectorAll('.pin').length > 0", timeout=30000)
    pg.wait_for_timeout(2500)
    add_iv(pg, "j07", "flyover", {"lanes": 2, "length_m": 600})
    simulate(pg, "#sim-changes", "with 1 change")
    check(len(bodies) == 2 and {json.dumps(x["interventions"]) for x in bodies} == {"[]", json.dumps([{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2, "length_m": 600}}])},
          f"POST /corridor/runs bodies (today + with changes): {bodies}")
    check(all(x.get("volume_scale") == 1.0 and "window" not in x for x in bodies), "volume_scale 1.0, no window sent")
    check("SAMPLE DATA" not in pg.inner_text("body"), "no sample tag for API results")
    check([x[0] for x in strips(pg)] == ["base", "tomtom", "changed"], "three strips from API results")
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
    mode["fail"] = True
    pg.click("#sim-today")
    st, _ = wait_status(pg, ["500", "simulated"], 30)
    check("500" in st and "SAMPLE DATA" not in pg.inner_text("body"), f"a failed simulation is shown, not replaced by the sample: {st[:80]}")
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
