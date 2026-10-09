"""CityRehearsal backend (C4 workflow API). Owner: AI agent workstream.

MOCK_SIM=1 serves sample C2 results and replays sample C1 frames from /contracts/samples,
so frontend and agent work never wait for SUMO. Set MOCK_SIM=0 once /sim provides a runner.
"""
import asyncio, hashlib, json, os, sqlite3, time, uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MOCK = os.getenv("MOCK_SIM", "1") == "1"
SAMPLES = ROOT / "contracts" / "samples"
DB = ROOT / "backend" / "cityrehearsal.db"

app = FastAPI(title="CityRehearsal API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=2000)  # GeoJSON (routes, roads, buildings) shrinks ~5x


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, junction_id TEXT, title TEXT, raised_by TEXT,
            stage TEXT, chosen_variant_id TEXT, fingerprint TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS variants(id TEXT PRIMARY KEY, case_id TEXT, template TEXT, params TEXT);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, case_id TEXT, variant_id TEXT, run_by TEXT,
            result TEXT, created REAL);  -- append-only: no delete endpoint
        CREATE TABLE IF NOT EXISTS reviews(case_id TEXT, reviewer TEXT, recommendation TEXT, comments TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS decisions(case_id TEXT, decision TEXT, reason TEXT, created REAL);
        """)


init_db()


# ---------- models (C3 + C4 bodies) ----------
class CaseIn(BaseModel):
    junction_id: str
    title: str
    raised_by: str = "inspector"


class VariantIn(BaseModel):
    case_id: str
    variant_id: str
    template: str
    params: dict = {}


class RunIn(BaseModel):
    case_id: str
    variant_id: str
    volume_scale: float = 1.0
    run_by: str = "engineer"
    window: str | None = None   # ISO start (IST) to rebuild a specific time from TomTom junction data; "live" = the last `minutes`
    minutes: int = 15


class SubmitIn(BaseModel):
    chosen_variant_id: str


class ReviewIn(BaseModel):
    reviewer: str
    recommendation: str  # "recommend" | "send_back"
    comments: str = ""


class DecideIn(BaseModel):
    decision: str  # approve | reject | defer
    reason: str


TEMPLATES = {"baseline", "signal_retime", "junction_redesign", "bus_lane", "widening", "flyover"}


# ---------- simulation runner ----------
def resolve_window(window: str | None, minutes: int) -> str | None:
    """'live' -> refresh the TomTom junction archive and use the last `minutes`; else pass the ISO start through."""
    if window != "live":
        return window
    import subprocess, sys
    from datetime import datetime, timedelta, timezone
    subprocess.run([sys.executable, str(ROOT / "data/tomtom/fetch_junction_archive.py"), "2026-10-08"],
                   capture_output=True, timeout=120)
    ist = timezone(timedelta(hours=5, minutes=30))
    return (datetime.now(ist) - timedelta(minutes=minutes)).replace(second=0, microsecond=0).isoformat(timespec="minutes")


def run_simulation(variant_id: str, template: str, volume_scale: float, params: dict | None = None,
                   run_id: str | None = None, window: str | None = None, minutes: int = 15) -> dict:
    if MOCK:
        samples = json.loads((SAMPLES / "run_results.sample.json").read_text())
        key = variant_id if variant_id in samples else ("flyover_3lane_400m" if template == "flyover" else "baseline")
        result = json.loads(json.dumps(samples[key]))
        for j in result["junctions"]:  # crude illustrative scaling for sensitivity tests in mock mode
            j["avg_delay_s"] = round(j["avg_delay_s"] * volume_scale ** 2, 1)
        result["inputs"]["volume_scale"] = volume_scale
        result["variant_id"] = variant_id
        return result
    # Real SUMO run (sim/runner.py): a few seconds per run; writes C1 frames next to the result.
    import sys
    sys.path.insert(0, str(ROOT / "sim"))
    import runner  # noqa: E402
    try:
        return runner.run({"variant_id": variant_id, "template": template, "params": params or {}},
                          volume_scale, run_id=run_id, window=resolve_window(window, minutes), minutes=minutes)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except RuntimeError as e:
        raise HTTPException(500, f"simulation failed: {e}")


# ---------- endpoints ----------
@app.get("/health")
def health():
    return {"status": "ok", "mock": MOCK}


@app.get("/config")
def config():
    """Keys the browser may hold (TomTom map keys are made for browser use); the MOVE key never leaves the server."""
    return {"tomtom_maps_key": os.getenv("TOMTOM_MAPS_KEY", ""), "mock": MOCK,
            "junction": {"id": "ymca_circle", "name": "YMCA Circle, Narayanguda", "lon": 78.4903, "lat": 17.3954}}


@app.get("/live/ymca")
def live_ymca():
    """TomTom Junction Analytics right now: delay, queue, volume and turns per road into YMCA Circle."""
    import urllib.request
    key = os.getenv("TOMTOM_API_KEY")
    if not key:
        raise HTTPException(503, "TOMTOM_API_KEY not set")
    names = {}
    definition = ROOT / "data/tomtom/junction/ymca_definition.json"
    if definition.exists():
        m = json.loads(definition.read_text())["junctionModel"]
        names = {x["id"]: x["name"] for x in m["approaches"] + m["exits"]}
    url = f"https://api.tomtom.com/junction-analytics/junctions/1/6ac7d6870b461bdaf5cd8158/live-data?key={key}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            d = json.load(r)
    except Exception as e:  # certificate problems on some laptops: fall back to curl
        import subprocess
        out = subprocess.run(["curl", "-s", "--compressed", url], capture_output=True, text=True, timeout=20)
        if not out.stdout.startswith("{"):
            raise HTTPException(502, f"TomTom live data unavailable: {e}")
        d = json.loads(out.stdout)
    return {"time": time.time(), "source": "TomTom Junction Analytics (measured; volume and queue estimated)",
            "approaches": [{"name": names.get(a["id"], str(a["id"])), "delay_s": a["delaySec"],
                            "usual_delay_s": a["usualDelaySec"], "travel_time_s": a["travelTimeSec"],
                            "queue_m": a["queueLengthMeters"], "volume_per_hour": a["volumePerHour"],
                            "turns": [{"exit": names.get(t["exitId"], str(t["exitId"])), "percent": t["ratioPercent"],
                                       "probes": t["probesCount"]} for t in a.get("turnRatios", [])]}
                           for a in d["approachesLiveData"]]}


@app.get("/runs/{run_id}/roads")
def run_roads(run_id: str):
    """Per-road simulated speeds for the run as GeoJSON (for congestion colours on the map)."""
    with db() as c:
        r = c.execute("SELECT result FROM runs WHERE id=?", (run_id,)).fetchone()
    path = json.loads(r["result"]).get("roads_path") if r else None
    if not path or not Path(path).exists():
        raise HTTPException(404, "no road data for this run (mock mode, or run not found)")
    return json.loads(Path(path).read_text())


SHORT = {"Narayanguda Road South Bound": "NE", "Raja Bahadur Venkata Rama Reddy Marg West Bound": "E",
         "Narayanguda Road North Bound": "S", "YMCA to Ramkoti Road East Bound": "W"}
ROUTE_IN = {"NE Narayanaguda Road - in": "NE", "SE Basant Talkies side - in": "E", "S road - in": "S",
            "W Narayanguda Main Road - in": "W"}


@app.get("/data/junction_history")
def junction_history(minutes: int = 10):
    """TomTom Junction Analytics since 8 Oct 23:17, averaged per bucket of `minutes`: delay, queue, volume per road."""
    import csv
    from collections import defaultdict
    path = ROOT / "data/raw/tomtom_ymca_junction_live.csv"
    if not path.exists():
        raise HTTPException(404, "run `make junction-data` first")
    acc = defaultdict(lambda: defaultdict(list))
    for r in csv.DictReader(open(path)):
        short = SHORT.get(r["approach"])
        if not short:
            continue
        t = r["time"]
        bucket = t[:11] + f"{int(t[11:13]):02d}:{(int(t[14:16]) // minutes) * minutes:02d}"
        for k in ("delay_s", "queue_m", "volume_per_hour"):
            acc[bucket][(short, k)].append(float(r[k]))
    out = []
    for b in sorted(acc):
        row = {"time": b, "delay_s": {}, "queue_m": {}, "volume_per_hour": {}}
        for (short, k), v in acc[b].items():
            row[k][short] = round(sum(v) / len(v), 1)
        out.append(row)
    return {"source": "TomTom Junction Analytics, junction 6ac7d6870b461bdaf5cd8158 (measured; volume and queue estimated)",
            "roads": {"NE": "Narayanguda Rd from north-east", "E": "Raja Bahadur V. R. Reddy Marg from east",
                      "S": "Narayanguda Rd from south", "W": "Narayanguda Main Rd from west"},
            "bucket_minutes": minutes, "buckets": out}


@app.get("/data/july_speeds")
def july_speeds():
    """TomTom Traffic Stats: average speed by hour of day on each road into the circle, weekdays July 2026."""
    import csv
    path = ROOT / "data/raw/tomtom_ymca_speeds.csv"
    if not path.exists():
        raise HTTPException(404, "data/raw/tomtom_ymca_speeds.csv missing")
    hours = {k: [None] * 24 for k in ROUTE_IN.values()}
    for r in csv.DictReader(open(path)):
        short = ROUTE_IN.get(r["route"])
        if short:
            hours[short][int(r["hour"])] = float(r["avg_speed_kmh"])
    return {"source": "TomTom Traffic Stats job 10048164, weekdays 1-31 Jul 2026 (measured)", "speed_kmh_by_hour": hours}


@app.get("/data/counts")
def counts():
    """Field counts per road and vehicle class from the 2020 YMCA Circle study, and the calibration applied."""
    import csv
    path = ROOT / "data/raw/ymca_counts.csv"
    if not path.exists():
        raise HTTPException(404, "data/raw/ymca_counts.csv missing")
    rows = list(csv.DictReader(open(path)))
    import sys
    sys.path.insert(0, str(ROOT / "sim"))
    try:
        from runner import CALIBRATED_SCALE
    except Exception:
        CALIBRATED_SCALE = None
    return {"source": "Sohail, Faheem, Aquil, IJRAR June 2020, Table 2 (counted)", "calibrated_scale": CALIBRATED_SCALE,
            "rows": [{k: (int(v) if v.isdigit() else v) for k, v in r.items()} for r in rows]}


@app.get("/buildings")
def buildings():
    path = ROOT / "data/raw/ymca_buildings.geojson"
    if not path.exists():
        raise HTTPException(404, "data/raw/ymca_buildings.geojson missing")
    return json.loads(path.read_text())


@app.post("/cases")
def create_case(body: CaseIn):
    cid = "c_" + uuid.uuid4().hex[:8]
    with db() as c:
        c.execute("INSERT INTO cases VALUES(?,?,?,?,?,?,?,?)",
                  (cid, body.junction_id, body.title, body.raised_by, "exploring", None, None, time.time()))
    return get_case(cid)


@app.get("/cases/{case_id}")
def get_case(case_id: str):
    with db() as c:
        row = c.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            raise HTTPException(404, "case not found")
        case = dict(row)
        case["variants"] = [dict(r) | {"params": json.loads(r["params"])} for r in
                            c.execute("SELECT * FROM variants WHERE case_id=?", (case_id,))]
        case["runs"] = [json.loads(r["result"]) | {"run_by": r["run_by"]} for r in
                        c.execute("SELECT * FROM runs WHERE case_id=? ORDER BY created", (case_id,))]
        case["reviews"] = [dict(r) for r in c.execute("SELECT * FROM reviews WHERE case_id=?", (case_id,))]
        case["decisions"] = [dict(r) for r in c.execute("SELECT * FROM decisions WHERE case_id=?", (case_id,))]
    return case


@app.post("/variants")
def create_variant(body: VariantIn):
    if body.template not in TEMPLATES:
        raise HTTPException(400, f"template must be one of {sorted(TEMPLATES)}")
    with db() as c:
        c.execute("INSERT OR REPLACE INTO variants VALUES(?,?,?,?)",
                  (body.variant_id, body.case_id, body.template, json.dumps(body.params)))
    return body.model_dump()


@app.post("/runs")
def create_run(body: RunIn):
    with db() as c:
        v = c.execute("SELECT * FROM variants WHERE id=?", (body.variant_id,)).fetchone()
    template = v["template"] if v else "baseline"
    run_id = "r_" + uuid.uuid4().hex[:8]
    result = run_simulation(body.variant_id, template, body.volume_scale,
                            params=json.loads(v["params"]) if v else {}, run_id=run_id,
                            window=body.window, minutes=body.minutes)
    result["run_id"] = run_id
    with db() as c:
        c.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)",
                  (result["run_id"], body.case_id, body.variant_id, body.run_by, json.dumps(result), time.time()))
    if not MOCK:
        from .corridor import prune_runs
        prune_runs()  # disk safeguard: keep the newest run folders only
    return result


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    with db() as c:
        r = c.execute("SELECT result FROM runs WHERE id=?", (run_id,)).fetchone()
    if not r:
        raise HTTPException(404, "run not found")
    return json.loads(r["result"])


@app.websocket("/stream/{run_id}")
async def stream(ws: WebSocket, run_id: str):
    await ws.accept()
    with db() as c:
        r = c.execute("SELECT result FROM runs WHERE id=?", (run_id,)).fetchone()
    stored = json.loads(r["result"]) if r else {}
    if MOCK and "corridor_id" not in stored:  # YMCA sample frames; corridor runs never get YMCA vehicles
        for f in json.loads((SAMPLES / "vehicle_frames.sample.json").read_text()):
            await ws.send_json(f)
            await asyncio.sleep(0.1)
    else:  # send the run's C1 frames (one per simulated second) as fast as the client takes them; it plays them at its own pace
        path = stored.get("frames_path")
        if path and Path(path).exists():
            try:
                with open(path) as fh:
                    for line in fh:
                        await ws.send_text(line.rstrip("\n"))
                        await asyncio.sleep(0)
            except Exception:  # client switched to another run
                return
    await ws.close()


@app.post("/cases/{case_id}/submit")
def submit(case_id: str, body: SubmitIn):
    case = get_case(case_id)
    pack = {"case_id": case_id, "chosen_variant_id": body.chosen_variant_id,
            "variants": case["variants"], "runs": case["runs"]}  # every run, not just the chosen one
    fingerprint = hashlib.sha256(json.dumps(pack, sort_keys=True).encode()).hexdigest()
    with db() as c:
        c.execute("UPDATE cases SET stage='in_review', chosen_variant_id=?, fingerprint=? WHERE id=?",
                  (body.chosen_variant_id, fingerprint, case_id))
    return get_case(case_id)


@app.post("/cases/{case_id}/review")
def review(case_id: str, body: ReviewIn):
    case = get_case(case_id)
    if body.recommendation == "recommend":
        if not any(r.get("run_by") == body.reviewer for r in case["runs"]):
            raise HTTPException(409, "Reviewer must re-run at least one scenario before recommending")
    with db() as c:
        c.execute("INSERT INTO reviews VALUES(?,?,?,?,?)",
                  (case_id, body.reviewer, body.recommendation, body.comments, time.time()))
        stage = "awaiting_decision" if body.recommendation == "recommend" else "exploring"
        c.execute("UPDATE cases SET stage=? WHERE id=?", (stage, case_id))
    return get_case(case_id)


@app.post("/cases/{case_id}/decide")
def decide(case_id: str, body: DecideIn):
    if body.decision not in {"approve", "reject", "defer"} or not body.reason.strip():
        raise HTTPException(400, "decision must be approve/reject/defer with a reason")
    with db() as c:
        c.execute("INSERT INTO decisions VALUES(?,?,?,?)", (case_id, body.decision, body.reason, time.time()))
        c.execute("UPDATE cases SET stage='decided' WHERE id=?", (case_id,))
    return get_case(case_id)


from .corridor import router as corridor_router  # noqa: E402  (corridor endpoints)

app.include_router(corridor_router)
