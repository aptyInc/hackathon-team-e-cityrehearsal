"""Smoke test: must pass before merging to main. Runs the full workflow in-process."""
import os, sys
from pathlib import Path
os.environ.setdefault("MOCK_SIM", "1")
import tempfile  # noqa: E402
os.environ.setdefault("CR_DB", str(Path(tempfile.mkdtemp()) / "smoke.db"))   # keep test cases out of the real decision log
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
assert c.get("/health").json()["status"] == "ok"
case = c.post("/cases", json={"junction_id": "ymca_circle", "title": "Peak-hour jam at YMCA Circle"}).json()
cid = case["id"]
for vid, tpl, params in [("baseline", "baseline", {}),
                         ("signal_retime_90s", "signal_retime", {"cycle_s": 90}),
                         ("flyover_3lane_400m", "flyover", {"lanes": 3, "length_m": 400, "landing_edge": "e45"})]:
    assert c.post("/variants", json={"case_id": cid, "variant_id": vid, "template": tpl, "params": params}).status_code == 200
    r = c.post("/runs", json={"case_id": cid, "variant_id": vid}).json()
    assert r["junctions"] and "inputs" in r, r
case = c.post(f"/cases/{cid}/submit", json={"chosen_variant_id": "signal_retime_90s"}).json()
assert len(case["fingerprint"]) == 64
blocked = c.post(f"/cases/{cid}/review", json={"reviewer": "reviewer", "recommendation": "recommend"})
assert blocked.status_code == 409, "recommend must be locked until the reviewer re-runs"
c.post("/runs", json={"case_id": cid, "variant_id": "signal_retime_90s", "volume_scale": 0.8, "run_by": "reviewer"})
assert c.post(f"/cases/{cid}/review", json={"reviewer": "reviewer", "recommendation": "recommend"}).status_code == 200
final = c.post(f"/cases/{cid}/decide", json={"decision": "approve", "reason": "Lowest cost, no ripple"}).json()
assert final["stage"] == "decided"
with c.websocket_connect("/stream/test") as ws:
    assert "vehicles" in ws.receive_json()

# ---- corridor (C5, mock mode) ----
cor = c.get("/corridor").json()
assert len(cor["points"]) == 13 and cor["points"][0]["kind"] == "end", cor["points"][:1]
periods = cor["tomtom"]["periods"]
assert periods[0]["kind"] == "average" and periods[0]["label"].startswith("Typical July day"), periods[0]["label"]
assert any(p["label"] == "Wed 1 Jul, 08-20" for p in periods) and all(len(p["legs"]) == 12 for p in periods)
route = cor["route"]
assert route["type"] == "FeatureCollection"
if route["features"]:  # empty only without sumolib (backend-only setup)
    dirs = {f["properties"]["direction"] for f in route["features"] if f["properties"]["kind"] == "route"}
    assert dirs == {"A->B", "B->A"}, dirs
    lon, lat = route["features"][0]["geometry"]["coordinates"][0]
    assert 78.2 < lon < 78.6 and 17.3 < lat < 17.6, (lon, lat)
base = c.post("/corridor/runs", json={"interventions": []}).json()
assert base["variant_id"] == "baseline" and base["journey"]["legs"] and len(base["fingerprint"]) == 64, base.get("variant_id")
fly = c.post("/corridor/runs", json={"interventions": [{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2}}]}).json()
assert fly["variant_id"] == "flyover_j07" and not any("MOCK_SIM" in w for w in fly["warnings"]), fly["warnings"]
other = c.post("/corridor/runs", json={"interventions": [{"junction_id": "j03", "kind": "signal_retime", "params": {}}]}).json()
assert any("MOCK_SIM" in w for w in other["warnings"]), "mock must say when the sample differs from the request"
assert c.get(f"/runs/{fly['run_id']}").json()["corridor_id"] == "lingampally_lakdikapul"
for bad in ({"interventions": [{"junction_id": "j99", "kind": "flyover"}]},
            {"interventions": [{"junction_id": "j07", "kind": "teleport"}]}, {"interventions": [], "volume_scale": 9}):
    assert c.post("/corridor/runs", json=bad).status_code == 400, bad
job = c.post("/corridor/runs?async=1", json={"interventions": []})
assert job.status_code == 202 and job.json()["status"] == "done"
assert c.get(f"/corridor/runs/{job.json()['run_id']}").json()["result"]["variant_id"] == "baseline"
assert c.get("/corridor/runs/rc_nothere").status_code == 404
with c.websocket_connect(f"/stream/{base['run_id']}") as ws:  # sample corridor runs have no frames: closes, no YMCA cars
    try:
        msg = ws.receive_json()
        assert False, f"corridor sample run streamed {str(msg)[:80]}"
    except Exception as e:
        assert "corridor sample run streamed" not in str(e), e
assert c.get(f"/runs/{base['run_id']}/roads").status_code == 404
# playback: frames window (part of the cache key, never of the numbers), probe tracks, hour of the day
fw = base["frames_window"]
assert (fw["from_s"], fw["to_s"], fw["step_s"], fw["sim_minutes_total"]) == (900, 1200, 4, 15), fw
w2 = c.post("/corridor/runs", json={"interventions": [], "frames_from_min": 0, "frames_minutes": 10}).json()
assert (w2["frames_window"]["from_s"], w2["frames_window"]["to_s"]) == (600, 1200) and w2["journey"] == base["journey"], w2["frames_window"]
for bad in ({"frames_minutes": 11}, {"frames_minutes": 0.5}, {"frames_from_min": -1}, {"frames_from_min": 12}, {"frames_from_min": 6, "frames_minutes": 10}):
    r = c.post("/corridor/runs", json={"interventions": [], **bad})
    assert r.status_code == 400 and "frames" in r.json()["detail"], (bad, r.status_code, r.text[:120])
from app.corridor import CorridorRunIn as _In, cache_key as _key, CALIBRATION_HOURLY as _HOURLY  # noqa: E402
assert _key([], _In()) == _key([], _In(frames_from_min=5, frames_minutes=5)) != _key([], _In(frames_from_min=0)), "window in the cache key"
assert c.post("/corridor/runs", json={"interventions": [], "hour": 3}).status_code == 400
assert c.post("/corridor/runs", json={"interventions": [], "day": "2026-07-08"}).status_code == 400, "a day needs an hour"
assert c.post("/corridor/runs", json={"interventions": [], "hour": 8, "day": "8 July"}).status_code == 400
hr = c.post("/corridor/runs", json={"interventions": [], "hour": 8})
hd = c.post("/corridor/runs", json={"interventions": [], "hour": 8, "day": "2026-07-08"})
if not _HOURLY.exists():
    for r in (hr, hd):
        assert r.status_code == 422 and "hourly data not available yet" in r.json()["detail"], r.text[:200]
else:
    assert hr.status_code in (200, 422) and hd.status_code in (200, 422), (hr.text[:200], hd.text[:200])
    if hr.status_code == 200:
        assert hr.json()["time"]["hour"] == 8 and "08:00-09:00" in hr.json()["time"]["window"], hr.json()["time"]
    if hd.status_code == 200:
        assert hd.json()["time"]["day"] == "2026-07-08" and hd.json()["time"]["window"].startswith("2026-07-08 08:00"), hd.json()["time"]
    else:
        assert "not available yet" in hd.json()["detail"], hd.text[:200]
    import app.corridor as _cor  # noqa: E402   without the hourly calibration: a clear 422
    _cor.CALIBRATION_HOURLY = Path(tempfile.mkdtemp()) / "missing.json"
    try:
        r = c.post("/corridor/runs", json={"interventions": [], "hour": 8})
        assert r.status_code == 422 and "hourly data not available yet" in r.json()["detail"], r.text[:200]
    finally:
        _cor.CALIBRATION_HOURLY = _HOURLY
    r = c.post("/corridor/runs", json={"interventions": [], "hour": 8, "day": "2026-06-30"})
    assert r.status_code == 422 and "not available yet" in r.json()["detail"], r.text[:200]
assert c.get("/runs/rc_nothere/probes").status_code == 404
pr = c.get(f"/runs/{base['run_id']}/probes")
assert pr.status_code in (200, 404), pr.text[:200]
if route["features"]:   # mock tracks follow the simulated route
    trips = pr.json()
    assert {t["direction"] for t in trips} == {"A->B", "B->A"} and all(t["mock"] for t in trips), [t["id"] for t in trips]
    t0 = next(t for t in trips if t["direction"] == "A->B")
    p0, p1 = t0["points"][0], t0["points"][-1]
    assert set(p0) == {"t", "lon", "lat", "z", "speed", "leg"} and p0["leg"] == 0 and p1["leg"] == 11, (p0, p1)
    assert abs(p1["t"] - p0["t"] - t0["total_s"]) < 1 and abs(t0["total_s"] - base["journey"]["total_s"]) < 2, t0["total_s"]
    assert all(t["direction"] == "B->A" for t in c.get(f"/runs/{base['run_id']}/probes?direction=rev").json())
    assert len(c.get(f"/runs/{base['run_id']}/probes?direction=A->B&number=1").json()) == 1
    assert c.get(f"/runs/{base['run_id']}/probes?direction=up").status_code == 400
geo = c.get("/corridor/junctions/geometry")
assert geo.status_code == 200, geo.text[:200]
gj = {j["id"]: j for j in geo.json()["junctions"]}
if gj:
    assert any(j["approaches"] for j in gj.values()) and all(len(a["coordinates"]) >= 2 for j in gj.values() for a in j["approaches"])
live = c.get("/corridor/junctions/live")
assert live.status_code in (200, 404)
if live.status_code == 200:
    assert live.json()["labels"]["delay_s"] == "measured" and live.json()["junctions"]
    for j in live.json()["junctions"]:       # live queues are drawn on the geometry: the approach ids match
        if j["approaches"] and j["id"] in gj and gj[j["id"]]["approaches"]:
            assert {a["approach_id"] for a in j["approaches"]} <= {a["approach_id"] for a in gj[j["id"]]["approaches"]}, j["id"]
assert c.get("/corridor/buildings").status_code in (200, 404)
assert c.get("/corridor/buildings/j07").status_code in (200, 404)
for bad in ("j99", "..%2F..%2Fcorridor", "corridor"):
    r = c.get(f"/corridor/buildings/{bad}")
    assert r.status_code == 404 and "geometry" not in r.text, (bad, r.text[:80])

# ---- corridor decision workflow (cases) ----
sig = c.post("/corridor/runs", json={"interventions": [{"junction_id": "j07", "kind": "signal_retime", "params": {"cycle_s": 90}}]}).json()
assert c.post("/corridor/cases", json={"title": "x", "run_ids": ["rc_nothere"]}).status_code == 404
cc = c.post("/corridor/cases", json={"title": "Tolichowki morning delay", "run_ids": [base["run_id"], sig["run_id"], fly["run_id"]],
                                     "created_by": "engineer"}).json()
assert cc["stage"] == "proposed" and len(cc["fingerprints"]) == 3 and len(cc["fingerprint"]) == 64, cc
ccid = cc["case_id"]
assert c.post(f"/corridor/cases/{ccid}/decide", json={"decider": "commissioner", "decision": "approve", "reason": "ok"}).status_code == 409, \
    "a corridor case is decided only after a review re-run"
rv = c.post(f"/corridor/cases/{ccid}/review", json={"reviewer": "reviewer", "volume_scale": 1.2, "note": "peak +20%"}).json()
assert rv["stage"] == "in_review" and sum(r["role"] == "review" for r in rv["runs"]) == 3, [r["role"] for r in rv["runs"]]
assert rv["events"][-1]["prev"] == rv["events"][0]["fingerprint"], "events are hash-chained"
assert {r["volume_scale"] for r in rv["runs"] if r["role"] == "review"} == {1.2}, "review runs report the level they ran at"
assert {r["volume_scale"] for r in rv["runs"] if r["role"] == "option"} == {1.0}
assert c.post(f"/corridor/cases/{ccid}/decide", json={"decider": "c", "decision": "maybe", "reason": "x"}).status_code == 400
dec = c.post(f"/corridor/cases/{ccid}/decide", json={"decider": "commissioner", "decision": "approve",
                                                      "reason": "Signal retime first; flyover pushes the queue to Nanal Nagar"}).json()
assert dec["stage"] == "decided" and dec["decision"]["decision"] == "approve" and len(dec["events"]) == 3
assert c.post(f"/corridor/cases/{ccid}/review", json={"reviewer": "r2"}).status_code == 409, "decided cases are closed"
row = next(k for k in c.get("/corridor/cases").json() if k["case_id"] == ccid)
assert row["decision"] == "approve" and row["decided_at"] >= row["created"], row
assert all("decision" in k and "decided_at" in k for k in c.get("/corridor/cases").json())
ver = c.get(f"/corridor/cases/{ccid}/verify").json()
assert ver["ok"] and [e["seq"] for e in ver["events"]] == [0, 1, 2], ver
assert all(e["matches"] and e["prev_ok"] and e["recomputed"] == e["fingerprint"] for e in ver["events"])
assert ver["evidence"] and all(x["matches"] for x in ver["evidence"]), ver["evidence"]
import sqlite3 as _sq  # noqa: E402  tamper with one event, check verify notices, put it back
from app.corridor import DB as _DB  # noqa: E402
with _sq.connect(_DB) as _con:
    _orig = _con.execute("SELECT body FROM corridor_case_events WHERE case_id=? AND seq=2", (ccid,)).fetchone()[0]
    _con.execute("UPDATE corridor_case_events SET body=? WHERE case_id=? AND seq=2", (_orig.replace("approve", "reject"), ccid))
try:
    bad = c.get(f"/corridor/cases/{ccid}/verify").json()
    assert not bad["ok"] and not bad["events"][2]["matches"] and bad["events"][1]["matches"], bad["events"]
finally:
    with _sq.connect(_DB) as _con:
        _con.execute("UPDATE corridor_case_events SET body=? WHERE case_id=? AND seq=2", (_orig, ccid))
assert c.get(f"/corridor/cases/{ccid}/verify").json()["ok"]
assert c.get("/corridor/cases/cc_nothere/verify").status_code == 404
cal = c.get("/corridor/calibration")
if cal.status_code == 200:
    assert "TomTom's own route is" in cal.json()["tomtom_basis"], cal.json().get("tomtom_basis")

# ---- planning assistant (Claude client mocked: no API cost) ----
import json as _json  # noqa: E402
from types import SimpleNamespace as _NS  # noqa: E402
from app.agent import agent as _agent  # noqa: E402


class _FakeMessages:
    """Scripted Claude: corridor data -> low-cost and construction options -> brief -> answer."""
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        msgs = kw["messages"]
        assert kw["tools"] and kw["system"] and msgs[0]["role"] == "user"
        results = [_json.loads(b["content"]) for b in (msgs[-1]["content"] if isinstance(msgs[-1]["content"], list) else [])
                   if b.get("type") == "tool_result"]
        start = max(i for i, m in enumerate(msgs) if m["role"] == "user" and isinstance(m["content"], str))
        n = sum(1 for m in msgs[start:] if m["role"] == "assistant")
        if start > 0:   # follow-up turn: just answer
            return _NS(content=[{"type": "text", "text": "You're welcome."}], stop_reason="end_turn", usage=None)
        use = lambda i, name, inp: {"type": "tool_use", "id": f"tu_{n}_{i}", "name": name, "input": inp}
        if n == 0:
            content = [{"type": "text", "text": "Checking the corridor."}, use(0, "get_corridor", {}),
                       use(1, "run_corridor", {"interventions": [{"junction_id": "j07", "kind": "signal_retime", "params": {"cycle_s": 90}}]}),
                       use(2, "run_corridor", {"interventions": [{"junction_id": "j07", "kind": "flyover", "params": {"lanes": 2}}]}),
                       use(3, "run_corridor", {"interventions": [{"junction_id": "j99", "kind": "flyover"}]})]
            stop = "tool_use"
        elif n == 1:
            assert results[0]["data"].startswith("MEASURED") and results[3]["error"], results
            ids = [r["run_id"] for r in results[1:3]]
            content = [use(0, "compare_runs", {"run_ids": ids}),
                       use(1, "write_brief", {"title": "Tolichowki", "problem": "j06->j07 is the slowest leg.", "run_ids": ids,
                                              "recommendation": "Retime the Tolichowki signal first.", "reasons": ["cheap"]})]
            stop = "tool_use"
        else:
            assert "brief_id" in results[1], results
            content = [{"type": "text", "text": f"Recommend the signal retime (brief {results[1]['brief_id']})."}]
            stop = "end_turn"
        return _NS(content=content, stop_reason=stop, usage=_NS(input_tokens=1000, output_tokens=100,
                                                                cache_read_input_tokens=0, cache_creation_input_tokens=0))


_fake = _FakeMessages()
_agent.set_client_factory(lambda: _NS(beta=_NS(messages=_fake)))
chat = c.post("/agent/chat", json={"message": "Should we build a flyover at Tolichowki? Try a cheaper option first."})
assert chat.status_code == 200, chat.text
chat = chat.json()
assert chat["brief_id"] and len(chat["run_ids"]) >= 2 and [s["tool"] for s in chat["steps"]][:2] == ["get_corridor", "run_corridor"], chat
assert "error" in chat["steps"][3]["summary"], "a bad junction comes back to the model as an error, not a crash"
br = c.get(f"/briefs/{chat['brief_id']}").json()
assert "## Recommendation" in br["markdown"] and "not a decision" in br["markdown"] and len(br["fingerprints"]) >= 3, br["markdown"][:300]
assert "MOCK_SIM=1" in br["markdown"], "mock numbers must be labelled in the brief"
hist = c.get(f"/agent/sessions/{chat['session_id']}").json()
assert len(hist["turns"]) == 1 and hist["turns"][0]["status"] == "done" and hist["brief_ids"] == [chat["brief_id"]]
# follow-up turn sees the history; async mode reports progress
_fake.calls.clear()
job = c.post("/agent/chat?async=1", json={"session_id": chat["session_id"], "message": "Thanks"})
assert job.status_code == 202, job.text
import time as _time  # noqa: E402
for _ in range(100):
    t = c.get(f"/agent/turns/{job.json()['turn_id']}").json()
    if t["status"] != "running":
        break
    _time.sleep(0.05)
assert t["status"] == "done" and len(_fake.calls[0]["messages"]) > 5, (t, len(_fake.calls[0]["messages"]))
# brief guardrail: construction only -> refused
from app.agent.tools import Context as _Ctx, execute as _exec  # noqa: E402
out, err = _exec(_Ctx(), "write_brief", {"title": "t", "problem": "p", "run_ids": [fly["run_id"]], "recommendation": "r", "reasons": []})
assert err and "low-cost" in out["error"], out
# no key -> 503 with a plain message
_agent.set_client_factory(None)
_key = os.environ.pop("ANTHROPIC_API_KEY", None)
r = c.post("/agent/chat", json={"message": "hi"})
assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"], r.text
if _key:
    os.environ["ANTHROPIC_API_KEY"] = _key

# ---- weather (July hourly, now with the network mocked, rain factors) ----
import app.weather as _wx  # noqa: E402
wj = c.get("/weather", params={"day": "july", "hour": 17}).json()
assert wj["label"].startswith("measured") and 0 <= wj["share_of_days_with_rain"] <= 1 and wj["slot"] == "17:00-18:00", wj
wd = c.get("/weather", params={"day": "2026-07-17", "hour": 15}).json()
assert wd["rain_class"] in ("dry", "light", "moderate", "heavy") and wd["what_if"] in ("dry", "light_rain", "heavy_rain"), wd
assert len(c.get("/weather", params={"day": "2026-07-21"}).json()["hours"]) == 24
for bad in ({"day": "2026-08-01", "hour": 3}, {"hour": 24}, {"day": "yesterday"}):
    assert c.get("/weather", params=bad).status_code == 400, bad
wf = c.get("/weather/factors").json()
assert wf["label"] == "estimated" and set(wf["what_if"]) == {"dry", "light_rain", "heavy_rain"} and len(wf["per_leg"]) == 12, wf.keys()
_real_fetch = _wx._fetch_now
_wx._mem.pop("now", None)
_wx._fetch_now = lambda: {"latitude": 17.4, "longitude": 78.37, "current": {"time": "2026-07-17T15:00", "interval": 900,
                          "precipitation": 0.2, "rain": 0.2, "temperature_2m": 25.1, "relative_humidity_2m": 90,
                          "wind_speed_10m": 8.5, "weather_code": 61, "cloud_cover": 100, "is_day": 1}}
wn = c.get("/weather/now").json()
assert wn["text"] == "Light rain" and wn["rain_mm_per_hour"] == 0.8 and wn["what_if"] == "light_rain" and not wn["cached"], wn
assert c.get("/weather/now").json()["cached"], "the current weather is cached for 10 minutes"


def _offline():
    raise RuntimeError("no network")


_wx._fetch_now = _offline
_wx._mem.pop("now", None)
r = c.get("/weather/now")
assert r.status_code == 503 and "unavailable" in r.json()["detail"], r.text
_wx._fetch_now = _real_fetch
print("SMOKE TEST PASSED")
