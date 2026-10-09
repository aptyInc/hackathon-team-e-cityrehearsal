"""Smoke test: must pass before merging to main. Runs the full workflow in-process."""
import os, sys
from pathlib import Path
os.environ.setdefault("MOCK_SIM", "1")
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
live = c.get("/corridor/junctions/live")
assert live.status_code in (200, 404)
if live.status_code == 200:
    assert live.json()["labels"]["delay_s"] == "measured" and live.json()["junctions"]
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
assert c.post(f"/corridor/cases/{ccid}/decide", json={"decider": "c", "decision": "maybe", "reason": "x"}).status_code == 400
dec = c.post(f"/corridor/cases/{ccid}/decide", json={"decider": "commissioner", "decision": "approve",
                                                      "reason": "Signal retime first; flyover pushes the queue to Nanal Nagar"}).json()
assert dec["stage"] == "decided" and dec["decision"]["decision"] == "approve" and len(dec["events"]) == 3
assert c.post(f"/corridor/cases/{ccid}/review", json={"reviewer": "r2"}).status_code == 409, "decided cases are closed"
assert any(k["case_id"] == ccid for k in c.get("/corridor/cases").json())

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
print("SMOKE TEST PASSED")
