"""Headless browser test of "Ask CityRehearsal" and "4 · Decision" on the corridor page (frontend/corridor.html + planner.js).

Every backend endpoint is mocked in the browser (shapes agreed with the agent workstream, 9 Oct):
  POST /agent/chat?async=1 -> {session_id, turn_id}; GET /agent/turns/{id} -> {status, steps, reply?, run_ids?, brief_id?, error?}
  GET /briefs/{id}; GET /runs/{id} (C5); POST /corridor/cases, /corridor/cases/{id}/review, /corridor/cases/{id}/decide; GET /corridor/cases

Cases
  A  Load: chat closed, "Ask CityRehearsal" button, step 4 waiting for runs, earlier-cases list hidden while empty
  B  Chat (async): suggestions, steps shown live ("Running: …" with a ticking clock), reply markdown rendered safely
     (headings, bold, lists, table; HTML escaped), a Show-on-map button per run, session kept for the next question,
     a failed turn shown with its steps
  C  Show on map: the agent's run becomes the "with changes" result (strip, table, list of changes) with its baseline
     from the same answer, no new simulation started
  D  Brief: modal with the markdown, evidence fingerprints, Print / save as PDF, Escape closes
  E  Case: Send for review (baseline + changes runs + brief), stage Proposed, short SHA-256 fingerprints (full on hover)
  F  Review: name required, re-test at 120% (busy note with a clock), stage In review, new runs, timeline entry
  G  Decide: reason required, approve, stage Decided, final/append-only note, timeline with who/when/what
  H  Fallbacks: /agent/chat and /corridor/cases answering 404 hide the features with a short note; a missing run or brief
     says so; chat answered synchronously (no turn_id) still works; sample results made in the browser cannot be sent
  N  Narrow screen (390 px) with the chat open: stacked under the journey, no sideways scroll
  K  No page errors at any point

Usage (repo root served on :5180; nothing needs to run on :8000):
    python3 -m http.server 5180 &
    PLAYWRIGHT_BROWSERS_PATH=~/Library/Caches/ms-playwright .venv/bin/python scripts/ui_test_review.py [url]
Screenshots: sim/out/review_<case>.png. Exit code 1 if any check fails.
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5180/frontend/corridor.html"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sim/out"
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = json.loads((ROOT / "contracts/samples/corridor_results.sample.json").read_text())
CORRIDOR = json.loads((ROOT / "data/corridor/corridor.json").read_text())
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"}
errors, results = [], []
case = ""


def check(ok, what):
    results.append((case, bool(ok), what))
    print(("  ok   " if ok else "  FAIL ") + what)


def sha(n):
    return (f"{n:02x}" * 32)[:64]


def run(kind, run_id, n, volume=1.0, ivs=None):
    r = json.loads(json.dumps(SAMPLE["flyover_j07" if kind == "fly" else "baseline"]))
    r.pop("sample", None)
    r.update(run_id=run_id, fingerprint=sha(n), frames_path=None, roads_path=None)
    r["inputs"] = {"counts_source": "test", "label": "estimated", "volume_scale": volume}
    if ivs is not None:
        r["interventions"] = ivs
    if kind == "retime":
        r["variant_id"] = "retime_j07"
        for leg in r["journey"]["legs"]:
            if leg["to_id"] == "j07":
                leg["time_s"] -= 120
        r["journey"]["total_s"] -= 120
    if volume != 1.0:
        for leg in r["journey"]["legs"]:
            leg["time_s"] = round(leg["time_s"] * volume, 1)
        r["journey"]["total_s"] = round(r["journey"]["total_s"] * volume, 1)
    return r


FLY = [{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2, "length_m": 600}}]
RETIME = [{"junction_id": "j07", "kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.65}}]
RUNS = {"r_agent_base": run("base", "r_agent_base", 1), "r_agent_retime": run("retime", "r_agent_retime", 2, ivs=RETIME),
        "r_agent_fly": run("fly", "r_agent_fly", 3)}
REPLY = """## Where to start at Tolichowki
The trip takes **98 min** in the model; the flyover saves *3.7 min* but moves the queue.

- Signal retime at Tolichowki: **−2 min**, low cost
- Flyover at Tolichowki: −3.7 min, knock-on at Nanal Nagar

| Option | Trip | Cost |
|---|---|---|
| Retime j07 | 96 min | low |
| Flyover j07 | 94 min | high |

<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>"""
BRIEF = {"brief_id": "b_1", "markdown": "# Decision brief: Tolichowki\n\n**Recommendation:** retime first.\n\n1. Evidence one\n2. Evidence two",
         "run_ids": ["r_agent_base", "r_agent_fly"], "fingerprints": {"r_agent_base": sha(1), "r_agent_fly": sha(3)}, "created_at": "2026-10-09T19:05:00+05:30"}
STREAM_JS = """(() => {
  const Real = window.WebSocket;
  window.WebSocket = class { constructor(url) { if (!url.includes('/stream/')) return new Real(url); setTimeout(() => this.onclose && this.onclose({}), 30); } close() {} };
  window.AGENT_POLL_MS = 250; window.LIVE_REFRESH_MS = 600000;
  const realFetch = window.fetch;   // hold review calls for window.__delayReview ms, like a re-run would
  window.fetch = async (u, o) => { if (window.__delayReview && String(u).includes('/review')) await new Promise(r => setTimeout(r, window.__delayReview)); return realFetch(u, o); };
  window.print = () => { window.__printed = (window.__printed || 0) + 1; };
})();"""


class Backend:
    """The agent + case endpoints, answered in the browser. `off` lists features answering 404; `sync_chat` answers chat directly."""

    def __init__(self, off=(), sync_chat=False):
        self.off, self.sync_chat = set(off), sync_chat
        self.calls, self.polls, self.cases, self.turns = [], {}, {}, {}
        self.hour_probes = 0

    def reply(self, route, status=200, body=None):
        if body is None:
            return route.fulfill(status=status, headers=CORS, body="not here" if status == 404 else "")
        route.fulfill(status=status, headers=CORS, content_type="application/json", body=json.dumps(body))

    def turn(self, tid):
        n = self.polls[tid] = self.polls.get(tid, 0) + 1
        step1 = {"tool": "simulate_corridor", "input": {"interventions": []}, "summary": "Simulated today's roads: 98 min", "run_id": "r_agent_base"}
        step2 = {"tool": "simulate_corridor", "input": {"interventions": RETIME}, "summary": "Signal retime at Tolichowki: 96 min", "run_id": "r_agent_retime"}
        step3 = {"tool": "simulate_corridor", "input": {"interventions": FLY}}
        if self.turns[tid] == "fail":
            return {"status": "failed", "steps": [step1], "error": "tool crashed: test"} if n >= 2 else {"status": "running", "steps": [step1]}
        if self.turns[tid] == "rain":
            return {"status": "done", "steps": [], "reply": "Rain makes the trip **about 15% slower** (assumed).", "run_ids": []}
        if n <= 1:
            return {"status": "running", "steps": []}
        if n == 2:
            return {"status": "running", "steps": [step1]}
        if n <= 4:
            return {"status": "running", "steps": [step1, step2]}
        if n <= 16:
            return {"status": "running", "steps": [step1, step2, dict(step3, status="running")]}
        return {"status": "done", "steps": [step1, step2, dict(step3, summary="Flyover at Tolichowki: 94 min", run_id="r_agent_fly")],
                "reply": REPLY, "run_ids": ["r_agent_base", "r_agent_retime", "r_agent_fly"], "brief_id": "b_1"}

    def case_runs(self, ids, volume=1.0):
        return [{"run_id": i, "volume_scale": volume, "total_s": RUNS[i]["journey"]["total_s"], "interventions": RUNS[i]["interventions"], "fingerprint": RUNS[i]["fingerprint"]} for i in ids]

    def handle(self, route):
        req = route.request
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        u = urlparse(req.url)
        path, q = u.path, parse_qs(u.query)
        body = json.loads(req.post_data) if req.method == "POST" and req.post_data else None
        if path == "/corridor/runs" and body and "hour" in body:   # the page asks once whether the API takes `hour` (not yet: 422)
            self.hour_probes += 1
            return self.reply(route, 422, {"detail": "hourly data not available yet"})
        self.calls.append((req.method, path + (("?" + u.query) if u.query else ""), body))
        if path == "/config":
            return self.reply(route, body={"tomtom_maps_key": "", "mock": True})
        if path == "/corridor":
            return self.reply(route, body=CORRIDOR)
        if path == "/corridor/runs":
            if "corridor_runs" in self.off:
                return self.reply(route, 404)
            return self.reply(route, body=RUNS["r_agent_fly" if body.get("interventions") else "r_agent_base"])
        if path.startswith("/corridor/buildings") or path == "/corridor/junctions/live" or path.endswith("/roads"):
            return self.reply(route, 404)
        if path == "/agent/chat":
            if "chat" in self.off:
                return self.reply(route, 404)
            msg = body.get("message", "")
            if self.sync_chat:
                return self.reply(route, body={"session_id": "s_sync", "reply": "The worst leg is **Shaikpet → Tolichowki**.", "run_ids": ["r_agent_fly"],
                                               "steps": [{"tool": "simulate_corridor", "input": {"interventions": FLY}, "summary": "Flyover at Tolichowki: 94 min", "run_id": "r_agent_fly"}]})
            tid = f"t{len(self.turns) + 1}"
            self.turns[tid] = "fail" if "fail" in msg else "rain" if "rain" in msg.lower() else "main"
            return self.reply(route, 202, {"session_id": body.get("session_id") or "s_1", "turn_id": tid})
        if path.startswith("/agent/turns/"):
            tid = path.rsplit("/", 1)[-1]
            return self.reply(route, body=self.turn(tid)) if tid in self.turns else self.reply(route, 404)
        if path.startswith("/briefs/"):
            return self.reply(route, body=BRIEF) if "briefs" not in self.off and path.endswith("/b_1") else self.reply(route, 404)
        if path.startswith("/runs/"):
            rid = path.split("/")[2]
            return self.reply(route, body=RUNS[rid]) if "runs" not in self.off and rid in RUNS else self.reply(route, 404)
        if path.startswith("/corridor/cases"):
            if "cases" in self.off:
                return self.reply(route, 404)
            parts = path.strip("/").split("/")
            if len(parts) == 2 and req.method == "GET":
                return self.reply(route, body=[{k: c[k] for k in ("case_id", "title", "stage", "created_at")} for c in self.cases.values()])
            if len(parts) == 2:
                cid = f"c_{len(self.cases) + 1}"
                c = {"case_id": cid, "title": body["title"], "stage": "proposed", "brief_id": body.get("brief_id"), "created_at": "2026-10-09T19:10:00+05:30",
                     "runs": self.case_runs(body["run_ids"]), "fingerprints": {i: RUNS[i]["fingerprint"] for i in body["run_ids"]}, "fingerprint": sha(9), "reviews": [], "decisions": []}
                self.cases[cid] = c
                return self.reply(route, body=c)
            c = self.cases.get(parts[2])
            if not c:
                return self.reply(route, 404)
            if len(parts) == 3:
                return self.reply(route, body=c)
            if parts[3] == "review":
                v = body.get("volume_scale")
                if v:
                    for i in (f"r_rv_base_{v}", f"r_rv_fly_{v}"):
                        RUNS[i] = run("fly" if "fly" in i else "base", i, 4 if "base" in i else 5, volume=v)
                        c["runs"].append(self.case_runs([i], v)[0])
                c["reviews"].append({"reviewer": body["reviewer"], "volume_scale": v, "note": body.get("note"), "created_at": "2026-10-09T19:20:00+05:30", "fingerprint": sha(10)})
                c["stage"] = "in_review"
                return self.reply(route, body=c)
            if parts[3] == "decide":
                c["decisions"].append({"decider": body["decider"], "decision": body["decision"], "reason": body["reason"], "created_at": "2026-10-09T19:30:00+05:30", "fingerprint": sha(11)})
                c["stage"] = "decided"
                return self.reply(route, body=c)
        return self.reply(route, 404)

    def posts(self, prefix):
        return [b for m, p, b in self.calls if m == "POST" and p.startswith(prefix)]


def open_page(b, viewport, backend):
    pg = b.new_page(viewport=viewport)
    pg.on("pageerror", lambda e: errors.append(f"[{case}] {e}"))
    pg.add_init_script(STREAM_JS)
    pg.route("http://localhost:8000/**", backend.handle)
    pg.route("**/data/corridor/buildings/*.geojson", lambda r: r.fulfill(status=404, headers=CORS, body="none"))
    pg.goto(URL, wait_until="load", timeout=60000)
    pg.wait_for_function("() => typeof overlay !== 'undefined' && overlay && document.querySelectorAll('.pin').length > 0 && window.planner", timeout=30000)
    pg.wait_for_timeout(1200)
    return pg


def wait_for(pg, js, seconds=20):
    try:
        pg.wait_for_function(js, timeout=seconds * 1000)
        return True
    except Exception:
        return False


def strips(pg):
    return pg.eval_on_selector_all("#strips .strip[data-strip]", "els => els.map(e => [e.dataset.strip, e.querySelector('.total').textContent])")


def last_bot(pg):
    return pg.locator("#chat-log .msg.bot").last


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])

    # ---------------- everything answering ----------------
    be = Backend()
    pg = open_page(b, {"width": 1500, "height": 950}, be)

    case = "A load"; print(case)
    check(pg.is_hidden("#chat") and pg.is_visible("#ask-open") and pg.inner_text("#ask-open") == "Ask CityRehearsal", "chat closed, Ask CityRehearsal button shown")
    check(pg.is_visible("#dec-new") and pg.is_disabled("#case-send") and "Simulate today and with changes first" in pg.inner_text("#case-why"), f"step 4 waits for runs: {pg.inner_text('#case-why')}")
    check("append-only" in pg.inner_text("#dec-new") and "RECORDED" in pg.inner_text("#left"), "step 4 says decisions are recorded and append-only")
    check(pg.is_hidden("#case-list-box"), "no earlier cases: list hidden")

    case = "B chat"; print(case)
    pg.click("#ask-open"); pg.wait_for_timeout(300)
    check(pg.is_visible("#chat") and pg.is_hidden("#right") and pg.inner_text("#ask-open") == "Close assistant", "chat opens in place of the layers panel")
    jr = pg.evaluate("() => [document.getElementById('journey').getBoundingClientRect().right, document.getElementById('chat').getBoundingClientRect().left]")
    check(jr[0] <= jr[1], f"trip strip makes room for the chat: {jr}")
    sugg = pg.eval_on_selector_all("#chat-sugg button", "els => els.map(e => e.textContent)")
    check(len(sugg) == 3 and "Where does the trip lose the most time?" in sugg[0] and sugg[1] == "Should we build a flyover at ISB Rd / DLF? Try a cheaper option first." and "rain" in sugg[2], f"3 suggested questions: {sugg}")
    pg.click("#chat-sugg button >> nth=1")
    check(wait_for(pg, "() => document.querySelector('#chat-log .steps li.run')", 10), "a running step is shown")
    check(wait_for(pg, "() => /Running: flyover, 2 lanes, 600 m at Tolichowki/.test(document.querySelector('#chat-log .msg.bot:last-child').innerText)", 10),
          f"live step: {last_bot(pg).inner_text()[:160]!r}")
    e1 = pg.inner_text("#chat-log .steps li.run .el"); pg.wait_for_timeout(1100)
    e2 = pg.inner_text("#chat-log .steps li.run .el") if pg.locator("#chat-log .steps li.run .el").count() else "done"
    check(e1 != e2, f"step clock ticks: {e1} -> {e2}")
    check("Simulated today's roads: 98 min" in last_bot(pg).inner_text() and pg.is_disabled("#chat-send"), "finished steps listed, Ask disabled while working")
    check(wait_for(pg, "() => document.querySelector('#chat-log .reply')", 15), "reply arrives")
    asked = be.posts("/agent/chat")
    check(len(asked) == 1 and asked[0] == {"message": sugg[1]} and any(p.startswith("/agent/chat?async=1") for _, p, _ in be.calls), f"POST /agent/chat?async=1 {asked}")
    rep = pg.locator("#chat-log .reply").last
    check(rep.locator(".md-h").first.inner_text() == "Where to start at Tolichowki" and rep.locator("b").first.inner_text() == "98 min", "heading and bold rendered")
    check(rep.locator("ul li").count() == 2 and rep.locator("table tr").count() == 3 and rep.locator("th").first.inner_text() == "Option", "list and table rendered")
    check(rep.locator("img, script").count() == 0 and pg.evaluate("() => window.__xss") is None and "<img src=x" in rep.inner_text(), "HTML in the reply is shown as text, not run")
    btns = pg.eval_on_selector_all("#chat-log .show-run", "els => els.map(e => e.dataset.run)")
    check(btns == ["r_agent_base", "r_agent_retime", "r_agent_fly"], f"a Show-on-map button per run: {btns}")
    labels = pg.eval_on_selector_all("#chat-log .rrow span", "els => els.map(e => e.textContent)")
    check(labels[2] == "flyover, 2 lanes, 600 m at Tolichowki" and "SIMULATED" in pg.inner_text("#chat-log .runs"), f"runs labelled in plain words, SIMULATED: {labels}")
    check(not pg.is_disabled("#chat-send") and pg.locator("#chat-log .open-brief").count() == 1, "Ask enabled again, brief button shown")
    pg.fill("#chat-in", "What would rain do to the trip?"); pg.press("#chat-in", "Enter")
    check(wait_for(pg, "() => document.querySelectorAll('#chat-log .reply').length === 2", 10), "second question answered")
    check(be.posts("/agent/chat")[-1] == {"session_id": "s_1", "message": "What would rain do to the trip?"}, f"session kept: {be.posts('/agent/chat')[-1]}")
    pg.fill("#chat-in", "fail please"); pg.click("#chat-send")
    check(wait_for(pg, "() => /could not finish/.test(document.querySelector('#chat-log .msg.bot:last-child').innerText)", 10), "failed turn shown")
    check("tool crashed: test" in last_bot(pg).inner_text() and "Simulated today's roads" in last_bot(pg).inner_text(), f"error and steps so far: {last_bot(pg).inner_text()[:120]!r}")
    pg.screenshot(path=str(OUT / "review_B.png"))

    case = "C show on map"; print(case)
    n_runs = len(be.posts("/corridor/runs"))
    pg.click("#chat-log .show-run[data-run=r_agent_fly]")
    check(wait_for(pg, "() => document.querySelectorAll('#strips .strip[data-strip]').length === 3", 10), "three strips")
    check([s[0] for s in strips(pg)] == ["base", "tomtom", "changed"] and "98 → 94 min" in pg.inner_text("#deltas .headline"), f"agent's run is the 'with changes' result, baseline from the same answer: {strips(pg)}")
    check(pg.eval_on_selector_all("#iv-list .iv span", "els => els.map(e => e.textContent)") == ["7 · Tolichowki: Flyover, 2 lanes, 600 m"] and "edited after" not in pg.inner_text("#deltas"),
          "list of changes matches the run")
    check(len(be.posts("/corridor/runs")) == n_runs and "SIMULATED" in pg.inner_text("#strips") and "Loaded from the assistant" in pg.inner_text("#run-note"), "no new simulation, labels kept")
    names = pg.eval_on_selector_all("#strips .strip[data-strip] .name", "els => els.map(e => e.textContent)")
    check(names[0].startswith("Simulated typical July day, roads as they are") and names[2].startswith("Simulated typical July day, with your changes"),
          f"trip rows say what is simulated: {names}")
    check(be.hour_probes == 1 and pg.is_disabled("#hour") and pg.get_attribute("#hour-box", "title") == "hourly TomTom data arriving tonight",
          f"hour picker asked the API once (422 now): disabled, 'hourly TomTom data arriving tonight' ({be.hour_probes} probe)")
    check(pg.eval_on_selector("#jt tr[data-id=j07]", "e => e.classList.contains('has')") and "85 → 120 s" in pg.inner_text("#jt tr[data-id=j08]"), "junction table before → after")
    check(pg.eval_on_selector("#chat-log .show-run[data-run=r_agent_fly]", "e => e.classList.contains('on')"), "button marks what is shown")
    pg.click("#chat-log .show-run[data-run=r_agent_retime]"); pg.wait_for_timeout(600)
    check("Signal timing, 120 s cycle, 65% green" in pg.inner_text("#iv-list") and "98 → 96 min" in pg.inner_text("#deltas .headline"), f"retime run shown: {pg.inner_text('#deltas .headline')[:60]}")
    pg.click("#chat-log .show-run[data-run=r_agent_fly]"); pg.wait_for_timeout(600)

    case = "D brief"; print(case)
    pg.click("#chat-log .open-brief")
    check(wait_for(pg, "() => /Decision brief: Tolichowki/.test(document.getElementById('brief-body').innerText)", 5), "brief opens in a modal")
    check(pg.locator("#brief-body ol li").count() == 2 and pg.locator("#brief-body b").first.inner_text() == "Recommendation:", "brief markdown rendered")
    fps = pg.eval_on_selector_all("#brief-meta .fp", "els => els.map(e => [e.textContent, e.title])")
    check(len(fps) == 2 and fps[0][0] == sha(1)[:10] and sha(1) in fps[0][1], f"evidence fingerprints, short with the full one on hover: {fps}")
    pg.click("#brief-print")
    check(pg.evaluate("() => window.__printed") == 1, "Print / save as PDF calls the browser's print")
    check(pg.evaluate("() => [...document.styleSheets].flatMap(x => { try { return [...x.cssRules]; } catch (e) { return []; } }).some(r => r.media && r.media.mediaText === 'print' && /brief-open/.test(r.cssText))"), "print stylesheet prints only the brief")
    pg.screenshot(path=str(OUT / "review_D.png"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    check(pg.is_hidden("#brief-modal"), "Escape closes the brief")

    case = "E case"; print(case)
    pg.click("#ask-open"); pg.wait_for_timeout(200)
    pg.locator("#left").evaluate("e => e.scrollTop = e.scrollHeight")
    check(not pg.is_disabled("#case-send") and "brief b_1" in pg.inner_text("#case-why"), f"Send for review ready: {pg.inner_text('#case-why')}")
    check(pg.input_value("#case-title") == "Flyover, 2 lanes, 600 m at Tolichowki", f"title from the change: {pg.input_value('#case-title')}")
    pg.fill("#case-by", "Planner K.")
    pg.click("#case-send")
    check(wait_for(pg, "() => !document.getElementById('case').hidden", 5), "case shown")
    check(be.posts("/corridor/cases") == [{"title": "Flyover, 2 lanes, 600 m at Tolichowki", "run_ids": ["r_agent_base", "r_agent_fly"], "brief_id": "b_1", "created_by": "Planner K."}],
          f"POST /corridor/cases {be.posts('/corridor/cases')}")
    check(pg.inner_text("#case .stages li.now") == "Proposed" and pg.is_hidden("#dec-new"), "stage Proposed")
    fps = pg.eval_on_selector_all("#case .caseruns .fp", "els => els.map(e => [e.textContent, e.title])")
    check(len(fps) == 2 and all(len(t) == 10 for t, _ in fps) and sha(3) in fps[1][1], f"runs with short fingerprints: {fps}")
    tl = pg.eval_on_selector_all("#case .tl li", "els => els.map(e => e.innerText)")
    check(len(tl) == 1 and "PROPOSED" in tl[0].upper() and "Planner K." in tl[0] and "brief b_1" in tl[0] and sha(9)[:10] in tl[0], f"timeline: {tl}")
    check("At 100% traffic: 98 → 94 min" in pg.inner_text("#case .sums"), f"summary per traffic level: {pg.inner_text('#case .sums')}")
    check(wait_for(pg, "() => !document.getElementById('case-list-box').hidden && /Flyover, 2 lanes/.test(document.getElementById('case-list').textContent)", 5), "earlier cases list updated")

    case = "F review"; print(case)
    pg.click("#rv-120"); pg.wait_for_timeout(200)
    check("reviewer's name" in pg.inner_text("#case-msg") and not be.posts("/corridor/cases/c_1/review"), "name required before a re-test")
    pg.fill("#rv-name", "Asha (traffic police)"); pg.fill("#rv-note", "Check the Nanal Nagar queue")
    pg.evaluate("() => { window.__delayReview = 2300; }")
    pg.click("#rv-120"); pg.wait_for_timeout(300)
    check(pg.is_visible("#case-busy") and "Re-testing both options at 120% traffic" in pg.inner_text("#case-busy") and pg.is_disabled("#rv-80"), f"busy: {pg.inner_text('#case-busy')}")
    c1 = pg.inner_text("#case-busy .el"); pg.wait_for_timeout(1100)
    check(pg.inner_text("#case-busy .el") != c1, "busy clock ticks")
    check(wait_for(pg, "() => document.getElementById('case-busy').hidden", 10), "re-test done")
    pg.evaluate("() => { window.__delayReview = 0; }")
    check(be.posts("/corridor/cases/c_1/review") == [{"reviewer": "Asha (traffic police)", "volume_scale": 1.2, "note": "Check the Nanal Nagar queue"}], f"review body: {be.posts('/corridor/cases/c_1/review')}")
    check(pg.inner_text("#case .stages li.now") == "In review" and pg.locator("#case .stages li.done").count() == 1, "stage In review")
    check(pg.locator("#case .caseruns tr[data-run]").count() == 4 and "At 120% traffic: 117 → 113 min" in pg.inner_text("#case .sums"), f"new runs at 120%: {pg.inner_text('#case .sums')}")
    tl = pg.eval_on_selector_all("#case .tl li", "els => els.map(e => e.innerText)")
    check(len(tl) == 2 and "Asha (traffic police)" in tl[1] and "Re-tested at 120% traffic: Check the Nanal Nagar queue" in tl[1] and sha(10)[:10] in tl[1], f"timeline: {tl[1:]}")
    pg.click("#case .case-show[data-run='r_rv_fly_1.2']"); pg.wait_for_timeout(800)
    check("at 120% traffic" in pg.inner_text("#run-note") and "117 → 113 min" in pg.inner_text("#deltas .headline"), f"re-test run on the map with its 120% baseline: {pg.inner_text('#deltas .headline')[:50]}")

    pg.click("#case-another"); pg.wait_for_timeout(200)
    check(pg.is_hidden("#case") and pg.is_visible("#dec-new") and not pg.is_disabled("#case-send"), "start another case: the form comes back, this one stays in Earlier cases")
    pg.eval_on_selector("#case-list button", "b => b.click()")
    check(wait_for(pg, "() => !document.getElementById('case').hidden && document.querySelector('#case .stages li.now')?.textContent === 'In review'", 5), "reopened from Earlier cases")

    case = "G decide"; print(case)
    pg.fill("#dc-name", "Commissioner R."); pg.click("#dc-approve"); pg.wait_for_timeout(200)
    check("reason is required" in pg.inner_text("#case-msg") and not be.posts("/corridor/cases/c_1/decide"), "reason required")
    pg.fill("#dc-reason", "Retime first; build the flyover only if the queue persists at 120%.")
    pg.click("#dc-approve")
    check(wait_for(pg, "() => document.querySelector('#case .stages li.now')?.textContent === 'Decided'", 5), "stage Decided")
    check(be.posts("/corridor/cases/c_1/decide") == [{"decider": "Commissioner R.", "decision": "approve", "reason": "Retime first; build the flyover only if the queue persists at 120%."}], "decide body")
    tl = pg.eval_on_selector_all("#case .tl li", "els => els.map(e => e.innerText)")
    check(len(tl) == 3 and "Commissioner R." in tl[2] and "Approved: Retime first" in tl[2] and "9 Oct" in tl[2] and sha(11)[:10] in tl[2], f"timeline: {tl[2]!r}")
    check("Approved by Commissioner R., 9 Oct, 19:30." in pg.inner_text("#case .note.info"), f"verdict: {pg.inner_text('#case .note.info')[:60]}")
    check("append-only" in pg.inner_text("#case") and pg.locator("#rv-80, #dc-approve").count() == 0 and pg.is_visible("#dec-new"), "final: no more buttons, new case possible")
    pg.screenshot(path=str(OUT / "review_G.png"))
    pg.click("#case-list-box summary"); pg.click("#case-list button"); pg.wait_for_timeout(500)
    check(pg.inner_text("#case .stages li.now") == "Decided" and pg.locator("#case .tl li").count() == 3, "earlier case reopens from the list")
    ev = pg.evaluate("""() => planner.timeline({ case_id: 'x', events: [{ stage: 'proposed', by: 'Ravi', at: '2026-10-09T19:00:00+05:30', what: 'Sent', fingerprint: 'abc' },
                                                                         { type: 'decided', actor: 'Meera', decision: 'reject', reason: 'too costly' }] })""")
    check(ev[0]["who"] == "Ravi" and ev[0]["fp"] == "abc" and ev[1]["stage"] == "decided" and ev[1]["what"] == "Rejected: too costly", f"server events read as the timeline: {ev}")
    pg.close()

    # ---------------- nothing there yet: 404 ----------------
    case = "H fallbacks"; print(case)
    be = Backend(off=("chat", "cases", "briefs"))
    pg = open_page(b, {"width": 1500, "height": 950}, be)
    check(pg.is_visible("#dec-off") and "not on this server yet" in pg.inner_text("#dec-off") and pg.is_hidden("#dec-new"), f"step 4 hidden with a note: {pg.inner_text('#dec-off')}")
    pg.click("#ask-open"); pg.click("#chat-sugg button >> nth=0")
    check(wait_for(pg, "() => !document.getElementById('chat-off').hidden", 5), "chat 404 noted")
    check(pg.is_hidden("#chat-form") and pg.is_hidden("#chat-sugg") and pg.locator("#chat-log .msg").count() == 0 and "not on this server yet" in pg.inner_text("#chat-off"), "chat input hidden, short note")
    pg.evaluate("() => planner.openBrief('nope')"); pg.wait_for_timeout(400)
    check("not on this server" in pg.inner_text("#brief-body"), "missing brief says so")
    pg.click("#brief-close")
    pg.close()

    # ---------------- phone, chat answered synchronously, browser-made sample results ----------------
    case = "N narrow"; print(case)
    be = Backend(off=("corridor_runs",), sync_chat=True)   # POST /corridor/runs 404: the page falls back to its built-in sample
    pg = open_page(b, {"width": 390, "height": 844}, be)
    pg.click("#p-dlf")
    check(wait_for(pg, "() => document.querySelectorAll('#strips .strip[data-strip]').length === 3", 15), "preset works (sample fallback)")
    check(pg.is_disabled("#case-send") and "sample results made in the browser" in pg.inner_text("#case-why"), f"sample results cannot be sent: {pg.inner_text('#case-why')}")
    pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)"); pg.wait_for_timeout(200)
    check(pg.is_visible("#ask-open") and pg.evaluate("() => { const r = $('ask-open').getBoundingClientRect(); return r.bottom <= innerHeight && r.top >= 0; }"),
          "assistant button floats in view wherever the page is scrolled")
    pg.click("#ask-open"); pg.wait_for_timeout(600)
    over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    box = pg.evaluate("() => { const c = $('chat').getBoundingClientRect(), j = $('journey').getBoundingClientRect(), l = $('left').getBoundingClientRect(); return [c.top, j.bottom, l.top, c.width]; }")
    check(over <= 0 and box[0] >= box[1] and box[2] > box[0] and box[3] > 340, f"chat stacked under the trip strip, full width, no sideways scroll: {box}, {over}")
    check(pg.is_hidden("#ask-open") and pg.is_visible("#chat-close"), "open chat: floating button out of the way, the chat's own close button shown")
    pg.fill("#chat-in", "Where does the trip lose the most time?"); pg.click("#chat-send")
    check(wait_for(pg, "() => document.querySelector('#chat-log .reply')", 5) and "Shaikpet → Tolichowki" in pg.inner_text("#chat-log .reply"), "synchronous answer (no turn_id) shown")
    pg.click("#chat-log .show-run")
    check(wait_for(pg, "() => /Loaded from the assistant/.test(document.getElementById('run-note').innerText)", 10), "show on map from a phone")
    check("SAMPLE DATA" not in pg.inner_text("#journey") and [s[0] for s in strips(pg)] == ["tomtom", "changed"] and "no run of today's roads" in pg.inner_text("#run-note"),
          f"agent's run replaces the browser sample, no sample baseline mixed in: {strips(pg)}")
    pg.screenshot(path=str(OUT / "review_N.png"), full_page=True)
    pg.close()
    b.close()

case = "K overall"
check(not errors, f"page errors: {errors or 'none'}")
print("\nSUMMARY")
for c in dict.fromkeys(r[0] for r in results):
    rs = [r for r in results if r[0] == c]
    print(f"  {c:16} {sum(r[1] for r in rs)}/{len(rs)} {'PASS' if all(r[1] for r in rs) else 'FAIL: ' + '; '.join(r[2] for r in rs if not r[1])}")
failed = [r for r in results if not r[1]]
print("RESULT:", "PASS" if not failed else f"FAIL ({len(failed)} of {len(results)} checks)")
sys.exit(1 if failed else 0)
