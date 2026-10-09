"""Real check of corridor playback through the API (MOCK_SIM=0: runs SUMO, about 1-2 minutes; not part of `make smoke`).

    python sim/corridor/check_playback.py          # inside .venv; KEEP=1 keeps the throwaway output folder

1. A baseline run, then the same request with another frames window: the API only replays the frames (same numbers,
   replay_frames). A full run with that window gives identical journey and junction numbers and byte-identical
   frames; each records its own window (first and last frame at from_s and to_s).
2. GET /runs/{run_id}/probes returns every A->B probe car's whole trip, Lingampally to Lakdikapul, whose mean equals
   the journey's total; probes.json stays under 3 MB.
3. The same request again is a cache hit; `hour` without sim/corridor/calibration_hourly.json is a 422.
Runs in a throwaway database and output folder; the API on :8000 and its cache are not touched.
"""
import json, math, os, shutil, statistics, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="cr_playback_"))
os.environ["MOCK_SIM"] = "0"
os.environ["CR_DB"] = str(TMP / "check.db")
os.environ["CR_SIM_OUT"] = str(TMP / "out")
os.environ.setdefault("CR_SIM_PARALLEL", "3")
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.corridor import CALIBRATION_HOURLY  # noqa: E402


def metres(a, b):
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((b[0] - a[0]) * 111320 * k, (b[1] - a[1]) * 110540)


def frames_span(path):
    with open(path) as f:
        ts = [json.loads(line)["t"] for line in f]
    return ts[0], ts[-1], len(ts)


try:
    c = TestClient(app)
    out = {}
    t = time.time()
    a = c.post("/corridor/runs", json={"interventions": []})
    assert a.status_code == 200, a.text[:300]
    a, out["run_default_s"] = a.json(), round(time.time() - t, 1)
    t = time.time()
    b = c.post("/corridor/runs", json={"interventions": [], "frames_from_min": 0, "frames_minutes": 10})
    assert b.status_code == 200, b.text[:300]
    b, out["replay_window_0_10_s"] = b.json(), round(time.time() - t, 1)
    assert a["run_id"] != b["run_id"] and not b.get("cached"), "another window is another run"
    assert b.get("frames_replayed_from") == a["run_id"], "same numbers, other window: only the frames are simulated again"
    for k in ("total_s", "total_s_sd", "legs", "probe_trips"):
        assert a["journey"][k] == b["journey"][k], (k, a["journey"][k], b["journey"][k])
    for r, want in ((a, (900, 1200)), (b, (600, 1200))):
        fw = r["frames_window"]
        assert (fw["from_s"], fw["to_s"]) == want, fw
        lo, hi, n = frames_span(r["frames_path"])
        assert (lo, hi, n) == (want[0], want[1], (want[1] - want[0]) // fw["step_s"] + 1), (lo, hi, n)
    # a full run with the other window: the same numbers (deterministic), and exactly the frames the replay recorded
    import corridor_runner  # noqa: E402  (on sys.path through app.corridor's import)
    t = time.time()
    full = corridor_runner.run(frames_window=(600, 1200), run_id="check_full_0_10")
    out["full_run_window_0_10_s"] = round(time.time() - t, 1)
    for k in ("total_s", "total_s_sd", "legs", "probe_trips"):
        assert a["journey"][k] == full["journey"][k], (k, a["journey"][k], full["journey"][k])
    assert a["junctions"] == full["junctions"] and a["inputs"]["corridor_volumes"] == full["inputs"]["corridor_volumes"]
    assert Path(full["frames_path"]).read_bytes() == Path(b["frames_path"]).read_bytes(), "replayed frames = a full run's frames"
    out["journey_total_s"] = a["journey"]["total_s"]
    out["frames_mb"] = {"5 min": round(os.path.getsize(a["frames_path"]) / 1e6, 1), "10 min": round(os.path.getsize(b["frames_path"]) / 1e6, 1)}

    pts = {p["id"]: (p["lon"], p["lat"]) for p in c.get("/corridor").json()["points"]}
    trips = c.get(f"/runs/{a['run_id']}/probes").json()
    fwd = [x for x in trips if x["direction"] == "A->B"]
    assert len(fwd) == a["journey"]["probe_trips"] == 30, (len(fwd), a["journey"]["probe_trips"])
    for x in fwd:
        p0, p1 = x["points"][0], x["points"][-1]
        assert metres((p0["lon"], p0["lat"]), pts["A_lingampally"]) < 500 and metres((p1["lon"], p1["lat"]), pts["B_lakdikapul"]) < 500, x["id"]
        assert p0["leg"] == 0 and p1["leg"] == 11 and abs(p1["t"] - p0["t"] - x["total_s"]) < 0.2, x["id"]
        assert all(q["t"] > p["t"] for p, q in zip(x["points"], x["points"][1:])), x["id"]
        assert [s["vehicle_id"] for s in x["segments"]] == [f"probe_fwd_{k}.{x['number']}" for k in range(6)], x["segments"]
    mean = statistics.mean(x["total_s"] for x in fwd)
    assert abs(mean - a["journey"]["total_s"]) < 12, (mean, a["journey"]["total_s"])   # journey: sum of rounded leg means
    trips_b = c.get(f"/runs/{b['run_id']}/probes").json()
    assert [x["total_s"] for x in trips_b] == [x["total_s"] for x in trips], "probe tracks do not depend on the window"
    size = os.path.getsize(a["probe_tracks_path"])
    assert size < 3e6, size
    out["probes"] = {"A->B trips": len(fwd), "B->A trips": len(trips) - len(fwd), "mean_A->B_s": round(mean, 1),
                     "points": sum(len(x["points"]) for x in trips), "file_mb": round(size / 1e6, 2)}

    t = time.time()
    again = c.post("/corridor/runs", json={"interventions": [], "frames_from_min": 5, "frames_minutes": 5}).json()
    assert again.get("cached") and again["run_id"] == a["run_id"], "the default window asked for explicitly is a cache hit"
    out["cache_hit_s"] = round(time.time() - t, 2)
    if not CALIBRATION_HOURLY.exists():
        r = c.post("/corridor/runs", json={"interventions": [], "hour": 8})
        assert r.status_code == 422 and "hourly data not available yet" in r.json()["detail"], r.text[:200]
    print(json.dumps(out, indent=1))
    print("PLAYBACK CHECK PASSED")
finally:
    if os.environ.get("KEEP") != "1":
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print("kept", TMP)
