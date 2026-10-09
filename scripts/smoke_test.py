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
print("SMOKE TEST PASSED")
