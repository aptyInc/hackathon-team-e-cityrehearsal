"""Headless browser test of the 3D view: loads the page, runs today's traffic, checks vehicles are drawn.

Usage (API on :8000 with MOCK_SIM=0, frontend served on :5174):
    PLAYWRIGHT_BROWSERS_PATH=~/Library/Caches/ms-playwright .venv/bin/python scripts/ui_test.py [url]
Needs `pip install playwright` and `python -m playwright install chromium-headless-shell`.
Writes a screenshot to sim/out/ui_test.png. Exit code 1 on any page error or empty map.
"""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5174/"
errors, problems = [], []
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1500, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(URL, wait_until="load", timeout=60000)
    pg.wait_for_timeout(8000)
    status = pg.inner_text("#status"); print("status:", status)
    print("live panel:", pg.inner_text("#live-body")[:100].replace("\n", " | "))
    print("time choices:", pg.eval_on_selector_all("#date-sel option", "els => els.map(e => e.textContent)"))
    pg.click("#run-base")
    for _ in range(90):
        pg.wait_for_timeout(1000)
        if "done" in pg.inner_text("#status") or "rror" in pg.inner_text("#status"):
            break
    print("after run:", pg.inner_text("#status"))
    pg.wait_for_timeout(6000)
    clock = pg.inner_text("#clock"); print("clock:", clock)
    layer = lambda lid: pg.evaluate(f"() => {{ const l = overlay._deck.props.layers.find(l => l.id === '{lid}'); return l ? l.props.data.length : 0; }}")
    vehicles, roads, buildings = layer("vehicles"), layer("roads"), layer("buildings")
    print(f"drawn: {vehicles} vehicles, {roads} roads, {buildings} buildings")
    pg.screenshot(path="sim/out/ui_test.png")
    b.close()
if errors: problems.append(f"page errors: {errors}")
if vehicles == 0: problems.append("no vehicles drawn")
if roads == 0: problems.append("no road colours drawn")
print("RESULT:", "PASS" if not problems else "FAIL " + "; ".join(problems))
sys.exit(1 if problems else 0)
