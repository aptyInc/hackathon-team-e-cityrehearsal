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
print("SMOKE TEST PASSED")
