"""Headless browser test of the 3D view: every user path, clicked the way a user does.

Cases
  A  Page load: no errors, live panel filled, time choices, map canvas, buildings drawn
  B  Typical weekday morning x {today's roads, 3-lane flyover, 20% less traffic}
  C  A specific date and hour (Fri 09:00) x the same three options
  D  A quiet night hour (Thu 23:00, few vehicles seen by TomTom)
  E  Live now: refreshes TomTom, simulates the last 15 minutes, turns the live traffic layer on
  F  Re-running the same option at the same time replaces its row (no duplicates)
  G  Playback: play/pause, speed, scrub, replay an older row from the table
  H  Layers: TomTom traffic, model congestion, buildings, vehicles on/off; night view and back
  I  Data panel: history, July and count charts; model-vs-TomTom bars after a run
  J  Camera: recenter and orbit
  K  The panel stays usable during every run; no page errors at any point

Usage (API on :8000 with MOCK_SIM=0, frontend served on :5174):
    PLAYWRIGHT_BROWSERS_PATH=~/Library/Caches/ms-playwright .venv/bin/python scripts/ui_test.py [url]
Needs `pip install playwright` and `python -m playwright install chromium-headless-shell`.
Screenshots: sim/out/ui_test_<case>.png. Exit code 1 if any check fails.
"""
import sys
import time
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5174/"
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
        pg.wait_for_timeout(400)
    return pg.inner_text("#status"), time.time() - t0


def layer(pg, lid):
    return pg.evaluate(f"() => {{ const l = overlay._deck.props.layers.find(l => l.id === '{lid}'); return l ? l.props.data.length : -1; }}")


def run(pg, button, expect_label, seconds=150):
    pg.click(button)
    pg.wait_for_timeout(300)
    busy = pg.is_disabled("#run-base")
    st, dt = wait_status(pg, [f"{expect_label}: simulated", "rror", "failed"], seconds)
    ok = "simulated" in st and expect_label in st
    check(ok, f"{expect_label}: {st} ({dt:.0f} s)")
    pg.wait_for_timeout(2500)
    check(busy and not pg.is_disabled("#run-base") and not pg.is_disabled("#run-fly"), "buttons locked while simulating, usable while playing")
    v = layer(pg, "vehicles")
    check(v > 0, f"vehicles drawn: {v}")
    return st


def rows(pg):
    return pg.eval_on_selector_all("#results tr td:first-child b", "els => els.map(e => e.textContent)")


def set_time(pg, date, hour=None):
    pg.select_option("#date-sel", date)
    if hour is not None:
        pg.select_option("#hour-sel", hour)
    pg.wait_for_timeout(300)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1500, "height": 950})
    pg.on("pageerror", lambda e: errors.append(f"[{case}] {e}"))
    pg.goto(URL, wait_until="load", timeout=60000)
    pg.wait_for_timeout(8000)

    case = "A load"; print(case)
    check("API: ok" in pg.inner_text("#status"), f"status: {pg.inner_text('#status')}")
    check("delay" in pg.inner_text("#live-body"), "live panel shows TomTom data")
    dates = pg.eval_on_selector_all("#date-sel option", "els => els.map(e => e.value)")
    check(dates[0] == "typical" and len(dates) >= 3, f"time choices: {dates}")
    check(pg.input_value("#date-sel") == "typical" and pg.is_disabled("#hour-sel"), "defaults to the typical morning, hour locked")
    check(pg.evaluate("() => !!document.querySelector('#map canvas')"), "map canvas present")
    check(layer(pg, "buildings") > 1000, f"buildings drawn before any run: {layer(pg, 'buildings')}")

    case = "B typical"; print(case)
    run(pg, "#run-base", "Typical morning · today's roads")
    check(layer(pg, "roads") > 50, f"road colours drawn: {layer(pg, 'roads')}")
    run(pg, "#run-fly", "Typical morning · 3-lane flyover")
    check("lanes merge" in pg.inner_text("#results"), "lane-drop warning in the table")
    run(pg, "#run-base80", "Typical morning · 20% less traffic")
    check("reviewer" in pg.inner_text("#results"), "20% run marked as the reviewer's")
    check(len(rows(pg)) == 3, f"three rows: {rows(pg)}")
    pg.screenshot(path="sim/out/ui_test_B.png")

    case = "C Fri 09:00"; print(case)
    day = [d for d in dates if d != "typical"][-1]
    set_time(pg, day, "09")
    check("TomTom measured" in pg.inner_text("#time-note"), f"note: {pg.inner_text('#time-note')[:80]}")
    run(pg, "#run-base", "09:00 · today's roads")
    check("vs TomTom" in pg.inner_text("#results"), "row compares with TomTom for that hour")
    run(pg, "#run-fly", "09:00 · 3-lane flyover")
    run(pg, "#run-base80", "09:00 · 20% less traffic")
    check(len(rows(pg)) == 6, f"six rows: {len(rows(pg))}")
    pg.screenshot(path="sim/out/ui_test_C.png")

    case = "D night"; print(case)
    first = [d for d in dates if d != "typical"][0]
    set_time(pg, first)
    hours = pg.eval_on_selector_all("#hour-sel option", "els => els.map(e => e.value)")
    check(len(hours) >= 1, f"hours offered for {first}: {hours}")
    set_time(pg, first, hours[-1])
    run(pg, "#run-base", f"{hours[-1]}:00 · today's roads")

    case = "L peak buttons"; print(case)
    set_time(pg, day)
    check(pg.is_visible("#bands"), "quick peak-hour buttons appear once a date is chosen")
    bands = pg.eval_on_selector_all("#bands button", "els => els.map(e => [e.textContent, e.disabled])")
    print("     ", bands)
    check(len(bands) == 6, f"six buttons: {[x[0] for x in bands]}")
    usable = [x[0] for x in bands if not x[1]]
    check("8–10 am" in usable, f"windows with data are enabled: {usable}")
    pg.locator("#bands button", has_text="8–10 am").click(); pg.wait_for_timeout(300)
    check("8–10 am" in pg.inner_text("#time-note") and "2 hours" in pg.inner_text("#time-note"), f"note: {pg.inner_text('#time-note')[:100]}")
    check(pg.input_value("#hour-sel") == "", "hour box shows '–' while a quick button is on")
    run(pg, "#run-base", "8–10 am · today's roads")
    pg.locator("#bands button", has_text="8–10 am").click(); pg.wait_for_timeout(300)
    check(pg.eval_on_selector_all("#bands button.on", "els => els.length") == 0, "clicking the same button again clears it")
    check(pg.input_value("#hour-sel") != "", f"hour box back to a real hour: {pg.input_value('#hour-sel')}")
    set_time(pg, "typical")
    check(not pg.is_visible("#bands"), "buttons hidden for the typical morning")

    case = "E live"; print(case)
    pg.click("#run-live")
    pg.wait_for_timeout(500)
    check("Live" in pg.inner_text("#time-note"), "time note switches to live")
    st, dt = wait_status(pg, ["Live", "rror", "failed"], 180)
    st, dt = wait_status(pg, ["today's roads: simulated", "rror", "failed"], 180)
    check(st.startswith("Live") and "simulated" in st, f"live run: {st} ({dt:.0f} s)")
    check(pg.is_checked("#t-traffic"), "live traffic layer switched on")
    check(pg.evaluate("() => map.getLayer('tomtom-traffic') && map.getLayoutProperty('tomtom-traffic', 'visibility') === 'visible'"), "TomTom traffic layer visible on the map")
    pg.wait_for_timeout(2500)
    check(layer(pg, "vehicles") > 0, f"vehicles drawn: {layer(pg, 'vehicles')}")
    pg.screenshot(path="sim/out/ui_test_E.png")

    case = "F re-run"; print(case)
    set_time(pg, "typical")
    n = len(rows(pg))
    run(pg, "#run-base", "Typical morning · today's roads")
    check(len(rows(pg)) == n, f"same run replaced its row: {n} -> {len(rows(pg))}")

    case = "G playback"; print(case)
    pg.wait_for_timeout(2000)
    playing = pg.inner_text("#play")
    pg.click("#play"); pg.wait_for_timeout(600)
    check(pg.inner_text("#play") != playing, f"play/pause toggles: {playing!r} -> {pg.inner_text('#play')!r}")
    c1 = pg.inner_text("#clock"); pg.wait_for_timeout(1500); c2 = pg.inner_text("#clock")
    paused = "Play" in pg.inner_text("#play")
    check(paused and c1 == c2, f"clock holds while paused: {c1}")
    pg.click("#play"); pg.select_option("#speed", "1"); pg.wait_for_timeout(2000)
    pg.select_option("#speed", "10")
    pg.evaluate("() => { const s = document.getElementById('scrub'); s.value = Math.floor(s.max / 2); s.dispatchEvent(new Event('input')); }")
    pg.wait_for_timeout(1500)
    check("simulated" in pg.inner_text("#clock"), f"scrub to the middle: {pg.inner_text('#clock')}")
    replay = pg.locator("#results button", has_text="Play").nth(1)
    replay.click(); pg.wait_for_timeout(4000)
    check(layer(pg, "vehicles") > 0 and "frames" in pg.inner_text("#playinfo") or "loaded" in pg.inner_text("#playinfo"), f"older row replays: {pg.inner_text('#playinfo')}")

    case = "H layers"; print(case)
    for box, lid in (("#t-roads", "roads"), ("#t-buildings", "buildings"), ("#t-vehicles", "vehicles")):
        pg.uncheck(box); pg.wait_for_timeout(400)
        off = layer(pg, lid)
        pg.check(box); pg.wait_for_timeout(400)
        on = layer(pg, lid)
        check(off == -1 and on > 0, f"{lid}: off hides it, on shows {on}")
    pg.uncheck("#t-traffic"); pg.wait_for_timeout(300)
    check(pg.evaluate("() => map.getLayoutProperty('tomtom-traffic', 'visibility')") == "none", "TomTom traffic off")
    pg.check("#t-traffic"); pg.wait_for_timeout(300)
    pg.check("#t-night"); pg.wait_for_timeout(6000)
    check(pg.evaluate("() => !!map.getLayer('tomtom-traffic')"), "night view keeps the TomTom traffic layer")
    check(layer(pg, "vehicles") > 0 and layer(pg, "buildings") > 0, "night view still draws vehicles and buildings")
    pg.screenshot(path="sim/out/ui_test_H_night.png")
    pg.uncheck("#t-night"); pg.wait_for_timeout(5000)
    check(pg.evaluate("() => !!map.getLayer('tomtom-traffic')"), "day view restores the TomTom traffic layer")

    case = "I data"; print(case)
    pg.click("#data-toggle"); pg.wait_for_timeout(4000)
    svgs = pg.evaluate("() => document.querySelectorAll('#data svg').length")
    check(svgs >= 3, f"charts drawn: {svgs}")
    check("since last night" in pg.inner_text("#d-history"), "junction history chart")
    check("July 2026" in pg.inner_text("#d-july"), "July speed chart")
    check("2020 study" in pg.inner_text("#d-counts"), "vehicle count table")
    check("Does the model match reality" in pg.inner_text("#d-calib"), "model vs TomTom bars after a run")
    pg.screenshot(path="sim/out/ui_test_I.png")
    pg.click("#data-toggle")

    case = "J camera"; print(case)
    pg.evaluate("() => map.jumpTo({ center: [78.48, 17.40], zoom: 14 })"); pg.click("#recenter"); pg.wait_for_timeout(1500)
    z = pg.evaluate("() => map.getZoom()")
    check(abs(z - 17.2) < 0.3, f"recenter returns to the circle (zoom {z:.1f})")
    b0 = pg.evaluate("() => map.getBearing()"); pg.click("#orbit"); pg.wait_for_timeout(1500); b1 = pg.evaluate("() => map.getBearing()"); pg.click("#orbit")
    check(abs(b1 - b0) > 1, f"orbit turns the view ({b0:.0f} -> {b1:.0f} deg)")
    b.close()

case = "K overall"
check(not errors, f"page errors: {errors or 'none'}")
print("\nSUMMARY")
for c in dict.fromkeys(r[0] for r in results):
    rs = [r for r in results if r[0] == c]
    print(f"  {c:12} {sum(r[1] for r in rs)}/{len(rs)} {'PASS' if all(r[1] for r in rs) else 'FAIL: ' + '; '.join(r[2] for r in rs if not r[1])}")
failed = [r for r in results if not r[1]]
print("RESULT:", "PASS" if not failed else f"FAIL ({len(failed)} of {len(results)} checks)")
sys.exit(1 if failed else 0)
