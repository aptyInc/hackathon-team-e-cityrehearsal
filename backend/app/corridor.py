"""Corridor endpoints (C4 corridor section, C5 results): Lingampally -> Lakdikapul. Owner: AI agent workstream.

    GET  /corridor                  points (data/corridor/corridor.json), TomTom leg times per period (REAL, measured),
                                    and the route through the simulated network as GeoJSON (A->B and B->A, per leg)
    POST /corridor/runs             {window?, minutes?, volume_scale?, interventions, run_by?, case_id?} -> C5 result
    POST /corridor/runs?async=1     same body -> 202 {run_id, status}; poll GET /corridor/runs/{run_id}
    GET  /corridor/runs/{run_id}    {run_id, status: queued|running|done|failed, result?, error?, elapsed_s}
    GET  /corridor/junctions/live   latest TomTom Junction Analytics snapshot per configured junction + last-60-min mean

MOCK_SIM=1: POST returns the contract sample (baseline, or flyover_j07 when any intervention is given), with a
warning when the request asked for something else. MOCK_SIM=0: sim/corridor/corridor_runner.run in a worker thread
(one SUMO run at a time, so the event loop never blocks), with a result cache keyed by
sha256(sorted interventions, volume_scale, window, minutes, sim/corridor/calibration.json, runner + template sources):
the same request twice returns the stored result instantly (`cached: true`), and the same request while it is still
running joins that run instead of starting a second one. Results are stored in the runs table (append-only) with a
SHA-256 fingerprint, so GET /runs/{id}, WS /stream/{id} and GET /runs/{id}/roads work for corridor runs too.
"""
import asyncio, csv, hashlib, json, os, shutil, sqlite3, sys, threading, time, uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from dotenv import load_dotenv

# same settings and database as main.py (not imported from it, so this module also loads on its own: no import cycle)
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MOCK = os.getenv("MOCK_SIM", "1") == "1"
SAMPLES = ROOT / "contracts" / "samples"
DB = ROOT / "backend" / "cityrehearsal.db"


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


router = APIRouter()

CORRIDOR_JSON = ROOT / "data/corridor/corridor.json"
LEGS_CSV = ROOT / "data/raw/corridor_legs_tomtom.csv"
JA_CONFIG = Path(os.getenv("CR_CORRIDOR_JA_CONFIG", ROOT / "data/tomtom/junction/corridor_junctions.json"))  # read per request
JA_LIVE = Path(os.getenv("CR_CORRIDOR_JA_LIVE", ROOT / "data/raw/tomtom_corridor_junction_live.csv"))
SIM_CORRIDOR = ROOT / "sim/corridor"
NET = SIM_CORRIDOR / "corridor.net.xml"
CALIBRATION = SIM_CORRIDOR / "calibration.json"
# sources whose change changes a run's result (the cache key hashes them)
SIM_SOURCES = [SIM_CORRIDOR / "corridor_runner.py", SIM_CORRIDOR / "corridor_net.py", ROOT / "sim/templates/corridor.py"]
CACHE_DIR = ROOT / "backend/.cache"
SIM_OUT = Path(os.getenv("CR_SIM_OUT", ROOT / "sim/out"))
KEEP_RUNS = int(os.getenv("CR_KEEP_RUNS", "15"))
KEEP_MB = int(os.getenv("CR_KEEP_RUNS_MB", "1500"))   # and never more than this in run folders (per output dir)
BUILDINGS = Path(os.getenv("CR_CORRIDOR_BUILDINGS", ROOT / "data/corridor/buildings"))
KINDS = ("flyover", "underpass", "signal_retime", "widening", "one_way", "u_turn")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

with db() as _c:
    _c.execute("CREATE TABLE IF NOT EXISTS corridor_cache(key TEXT PRIMARY KEY, run_id TEXT, created REAL)")


def corridor_def() -> dict:
    return json.loads(CORRIDOR_JSON.read_text())


def junction_ids() -> list[str]:
    return [p["id"] for p in corridor_def()["points"] if p["kind"] == "junction"]


# ---------- disk safeguard ----------
def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def prune_runs(keep: int = KEEP_RUNS, busy: set[str] = frozenset(), keep_mb: int = KEEP_MB):
    """Keep only the newest `keep` run folders the API created (r_*, rc_*) under the YMCA and corridor output dirs,
    and drop older ones beyond `keep_mb` in total (the newest folder always stays). Calibration and test folders are
    left alone; folders of runs still in progress are never touched."""
    for d in (SIM_OUT / "runs", SIM_OUT / "corridor"):
        if not d.is_dir():
            continue
        runs = sorted((p for p in d.iterdir() if p.is_dir() and p.name.startswith(("r_", "rc_")) and p.name not in busy),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        total = 0
        for k, p in enumerate(runs):
            total += _size(p)
            if k >= keep or (k > 0 and total > keep_mb * 1e6):
                shutil.rmtree(p, ignore_errors=True)


def trim_frames(path: Path, lo: float, hi: float):
    """Keep only the frames in [lo, hi] s (the runner's FRAMES window). The runner writes vehicle positions from `lo`
    to the end of the simulation (~0.5 GB per run) while the 3D view plays the window only. Kept lines are unchanged."""
    tmp = path.with_suffix(".tmp")
    with path.open() as src, tmp.open("w") as dst:
        for line in src:
            t = float(line[5:line.index(",")]) if line.startswith('{"t":') else json.loads(line)["t"]
            if t > hi:
                break
            if t >= lo:
                dst.write(line)
    tmp.replace(path)


# ---------- GET /corridor ----------
def _hours(h: str) -> str:   # "6:00-23:00" -> "06-23"
    a, b = h.split("-")
    return f"{int(a.split(':')[0]):02d}-{int(b.split(':')[0]):02d}"


def tomtom_periods() -> list[dict]:
    """TomTom Traffic Stats leg times per period: the July average first, then each day."""
    if not LEGS_CSV.exists():
        return []
    periods: dict[str, dict] = {}
    for r in csv.DictReader(LEGS_CSV.open()):
        p = periods.get(r["period"])
        if p is None:
            dates, hours = r["period"].split(" ")
            d0, d1 = dates.split("..")
            if d0 == d1:
                d = datetime.fromisoformat(d0)
                label, kind = f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}, {_hours(hours)}", "day"
            else:
                label, kind = f"Typical {datetime.fromisoformat(d0).strftime('%B')} day ({_hours(hours)})", "average"
            p = periods[r["period"]] = {"period": r["period"], "label": label, "kind": kind, "date_from": d0, "date_to": d1,
                                        "hours": hours, "job": r["job"], "trip_total_s": float(r["trip_total_s"]),
                                        "source": f"TomTom Traffic Stats job {r['job']}", "data_label": "measured", "legs": []}
        p["legs"].append({"from_id": r["from_id"], "to_id": r["to_id"], "from_name": r["from"], "to_name": r["to"],
                          "distance_m": float(r["distance_m"]), "time_s": float(r["time_s"]), "speed_kmh": float(r["speed_kmh"])})
    out = sorted(periods.values(), key=lambda p: (p["kind"] != "average", p["date_from"]))
    for p in out:
        p["total_s"] = round(sum(l["time_s"] for l in p["legs"]), 1)
        p["distance_m"] = round(sum(l["distance_m"] for l in p["legs"]))
    return out


_route_lock = threading.Lock()
_route_mem: dict = {}


def _file_hash(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes() if p.exists() else b"-")
    return h.hexdigest()


def route_geometry() -> dict | None:
    """The corridor's path through the simulation network (corridor_net.route), as lon/lat GeoJSON: one LineString
    per direction and one per leg between corridor points. Cached in memory and in backend/.cache (keyed by the
    network and route sources), since loading the network takes a few seconds."""
    key = _file_hash(NET, SIM_CORRIDOR / "corridor_net.py", SIM_CORRIDOR / "route_points.json", CORRIDOR_JSON)[:16]
    with _route_lock:
        if _route_mem.get("key") == key:
            return _route_mem["geo"]
        cached = CACHE_DIR / f"corridor_route_{key}.json"
        if cached.exists():
            geo = json.loads(cached.read_text())
        else:
            try:
                geo = _build_route()
            except Exception as e:   # no sumolib (backend-only setup) or no network file
                return {"type": "FeatureCollection", "features": [], "error": f"route geometry unavailable: {type(e).__name__}: {e}"}
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            for old in CACHE_DIR.glob("corridor_route_*.json"):
                old.unlink()
            cached.write_text(json.dumps(geo, separators=(",", ":")))
        _route_mem.update(key=key, geo=geo)
        return geo


def _build_route() -> dict:
    import math
    sys.path.insert(0, str(SIM_CORRIDOR))
    import sumolib
    import corridor_net as cn
    net = sumolib.net.readNet(str(NET))
    points = cn.CORRIDOR["points"]

    def line(edges):
        coords = []
        for e in edges:
            for x, y, *_ in e.getShape(True):
                c = [round(v, 6) for v in net.convertXY2LonLat(x, y)]
                if not coords or coords[-1] != c:
                    coords.append(c)
        return coords

    feats = []
    for direction, pts, path in (("A->B", points, cn.route(net)), ("B->A", points[::-1], cn.route(net, reverse=True))):
        if not path:
            continue
        idx = []
        for p in pts:   # the path edge whose end is closest to each corridor point, as the runner splits legs
            x, y = net.convertLonLat2XY(p["lon"], p["lat"])
            idx.append(min(range(len(path)), key=lambda i: math.dist(path[i].getToNode().getCoord()[:2], (x, y))))
        idx[0], idx[-1] = -1, len(path) - 1
        feats.append({"type": "Feature", "properties": {"kind": "route", "direction": direction, "from_id": pts[0]["id"],
                                                        "to_id": pts[-1]["id"], "edges": len(path),
                                                        "length_m": round(sum(e.getLength() for e in path))},
                      "geometry": {"type": "LineString", "coordinates": line(path)}})
        for k, (a, b) in enumerate(zip(idx, idx[1:])):
            edges = path[a + 1:b + 1]
            if edges:
                feats.append({"type": "Feature", "properties": {"kind": "leg", "direction": direction, "from_id": pts[k]["id"],
                                                                "to_id": pts[k + 1]["id"], "length_m": round(sum(e.getLength() for e in edges))},
                              "geometry": {"type": "LineString", "coordinates": line(edges)}})
    return {"type": "FeatureCollection", "features": feats,
            "source": "sim/corridor/corridor.net.xml (OpenStreetMap via SUMO netconvert), path from corridor_net.route",
            "data_label": "network geometry (not a measurement)"}


@router.get("/corridor")
def get_corridor():
    """Corridor definition + TomTom measured leg times per period + the simulated route's geometry."""
    c = corridor_def()
    c["tomtom"] = {"source": "TomTom Traffic Stats, Lingampally -> Lakdikapul, July 2026 (data/raw/corridor_legs_tomtom.csv)",
                   "data_label": "REAL: measured (TomTom probe data)", "periods": tomtom_periods()}
    c["route"] = route_geometry()
    c["labels"] = {"points": "reference: team junction list + OpenStreetMap coordinates",
                   "tomtom": "REAL: measured by TomTom (probe vehicles); leg times, speeds and distances",
                   "route": "network geometry the simulation drives on (OpenStreetMap), not a measurement",
                   "runs": "SIMULATED: everything POST /corridor/runs returns, except legs[].tomtom_time_s (measured)"}
    c["mock"] = MOCK
    return c


# ---------- POST /corridor/runs ----------
class InterventionIn(BaseModel):
    junction_id: str
    kind: str
    params: dict = {}


class CorridorRunIn(BaseModel):
    window: str | None = None
    minutes: int | None = None
    volume_scale: float = 1.0
    interventions: list[InterventionIn] = []
    run_by: str = "engineer"
    case_id: str | None = None


def validate(body: CorridorRunIn) -> list[dict]:
    """Checked, normalised and sorted interventions (sorted so the same set in any order is the same run)."""
    ids, seen, out = junction_ids(), set(), []
    for iv in body.interventions:
        if iv.junction_id not in ids:
            raise HTTPException(400, f"unknown junction {iv.junction_id!r}; use one of {', '.join(ids)}")
        if iv.kind not in KINDS:
            raise HTTPException(400, f"unknown intervention kind {iv.kind!r}; use one of {', '.join(KINDS)}")
        if (iv.junction_id, iv.kind) in seen:
            raise HTTPException(400, f"{iv.kind} at {iv.junction_id} is listed twice; give it once with all its params")
        seen.add((iv.junction_id, iv.kind))
        out.append({"junction_id": iv.junction_id, "kind": iv.kind, "params": iv.params})
    if not 0.1 <= body.volume_scale <= 3.0:
        raise HTTPException(400, f"volume_scale must be between 0.1 and 3.0, got {body.volume_scale}")
    if body.minutes is not None and not 1 <= body.minutes <= 24 * 60:
        raise HTTPException(400, f"minutes must be between 1 and 1440, got {body.minutes}")
    return sorted(out, key=lambda iv: (iv["junction_id"], iv["kind"], json.dumps(iv["params"], sort_keys=True)))


def cache_key(ivs: list[dict], body: CorridorRunIn) -> str:
    calib = CALIBRATION.read_text() if CALIBRATION.exists() else None
    blob = json.dumps({"interventions": ivs, "volume_scale": round(body.volume_scale, 3), "window": body.window,
                       "minutes": body.minutes, "calibration": calib, "sim": _file_hash(*SIM_SOURCES)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def fingerprint(result: dict) -> str:
    return hashlib.sha256(json.dumps({k: v for k, v in result.items() if k not in ("fingerprint", "cached")},
                                     sort_keys=True).encode()).hexdigest()


def store(result: dict, body: CorridorRunIn) -> dict:
    result["fingerprint"] = fingerprint(result)
    with db() as c:
        c.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)", (result["run_id"], body.case_id or "corridor",
                                                           result["variant_id"], body.run_by, json.dumps(result), time.time()))
    return result


def stored_run(run_id: str) -> dict | None:
    with db() as c:
        r = c.execute("SELECT result FROM runs WHERE id=?", (run_id,)).fetchone()
    return json.loads(r["result"]) if r else None


def cache_lookup(key: str) -> dict | None:
    """The stored result for `key`, if its files (frames, roads) are still on disk."""
    with db() as c:
        r = c.execute("SELECT run_id FROM corridor_cache WHERE key=?", (key,)).fetchone()
    res = stored_run(r["run_id"]) if r else None
    if not res or any(res.get(k) and not Path(res[k]).exists() for k in ("frames_path", "roads_path")):
        return None
    return res


MOCK_SYNTH = os.getenv("CR_MOCK_SYNTH", "0") == "1"   # opt-in: illustrative mock per request (see synth_mock)
# illustrative effect of each kind in synth mocks: (delay factor at the junction, congestion factor on the leg into it,
# congestion factor on the leg out of it, delay factor at the next junction). Invented for demos, NOT a model.
SYNTH = {"signal_retime": (0.8, 0.85, 1.0, 1.05), "widening": (0.75, 0.8, 1.05, 1.1), "one_way": (0.9, 0.92, 1.0, 1.03),
         "flyover": (0.25, 0.45, 1.35, 1.4), "underpass": (0.3, 0.5, 1.3, 1.35)}


def synth_mock(ivs: list[dict], body: CorridorRunIn) -> dict:
    """CR_MOCK_SYNTH=1: a made-up result shaped like the request (baseline sample, congestion scaled by volume_scale^2,
    fixed illustrative factors per intervention). Lets the UI and the agent exercise any request without SUMO.
    Always labelled 'assumed' and carries a MOCK_SIM warning: it is not a simulation."""
    samples = json.loads((SAMPLES / "corridor_results.sample.json").read_text())
    res = json.loads(json.dumps(samples["baseline"]))
    vs2 = body.volume_scale ** 2
    legs, juncs = res["journey"]["legs"], {j["id"]: j for j in res["junctions"]}
    free = {id(l): l["distance_m"] / (40 / 3.6) for l in legs}          # free-flow part of each leg at 40 km/h
    cong = {id(l): max(0.0, l["time_s"] - free[id(l)]) * vs2 for l in legs}
    for j in juncs.values():
        j["avg_delay_s"], j["max_queue_m"] = j["avg_delay_s"] * vs2, j["max_queue_m"] * vs2
    order = [l["to_id"] for l in legs]
    for iv in ivs:
        f = SYNTH.get(iv["kind"])
        if not f:
            res["warnings"].append(f"{iv['junction_id']} {iv['kind']}: this template is not built yet; the intervention was left out")
            continue
        jid = iv["junction_id"]
        into = next(l for l in legs if l["to_id"] == jid)
        out = next(l for l in legs if l["from_id"] == jid)
        cong[id(into)] *= f[1]
        cong[id(out)] *= f[2]
        juncs[jid]["avg_delay_s"] *= f[0]
        juncs[jid]["max_queue_m"] *= f[0]
        nxt = order[order.index(jid) + 1] if order.index(jid) + 1 < len(order) else None
        if nxt in juncs:
            juncs[nxt]["avg_delay_s"] *= f[3]
            juncs[nxt]["max_queue_m"] *= f[3]
            if f[3] >= 1.3:
                res["warnings"].append(f"{jid} {iv['kind']}: traffic released by the structure queues at {juncs[nxt]['name']} "
                                       "(illustrative mock)")
    for l in legs:
        l["time_s"] = round(free[id(l)] + cong[id(l)])
        l["speed_kmh"] = round(l["distance_m"] / l["time_s"] * 3.6, 1)
    for j in juncs.values():
        j["avg_delay_s"], j["max_queue_m"] = round(j["avg_delay_s"], 1), round(j["max_queue_m"])
    res["journey"]["total_s"] = sum(l["time_s"] for l in legs)
    res["interventions"] = ivs
    res["variant_id"] = "_".join(f"{iv['kind']}_{iv['junction_id']}" for iv in ivs) or "baseline"
    res["inputs"]["volume_scale"] = body.volume_scale
    res["warnings"].append("MOCK_SIM=1 (CR_MOCK_SYNTH=1): illustrative made-up numbers shaped like your request, not a "
                           "simulation. Start the API with MOCK_SIM=0 for real runs.")
    return res


def mock_result(ivs: list[dict], body: CorridorRunIn) -> dict:
    samples = json.loads((SAMPLES / "corridor_results.sample.json").read_text())
    res = json.loads(json.dumps(samples["flyover_j07" if ivs else "baseline"]))
    asked = {"interventions": ivs, "volume_scale": body.volume_scale, "window": body.window, "minutes": body.minutes}
    sample = {"interventions": res["interventions"], "volume_scale": res["inputs"]["volume_scale"], "window": None, "minutes": None}
    if [(i["junction_id"], i["kind"]) for i in ivs] != [(i["junction_id"], i["kind"]) for i in sample["interventions"]] \
            or asked["volume_scale"] != sample["volume_scale"] or body.window or body.minutes:
        if MOCK_SYNTH:
            res = synth_mock(ivs, body)
            res["run_id"] = "rc_" + uuid.uuid4().hex[:8]
            res["requested"] = asked
            return res
        res["warnings"].append("MOCK_SIM=1: this is the sample result (" + res["variant_id"] + "), not a simulation of your request "
                               f"({json.dumps(asked)}). Start the API with MOCK_SIM=0 for real runs.")
    res["run_id"] = "rc_" + uuid.uuid4().hex[:8]
    res["requested"] = asked
    return res


# One SUMO run at a time (CPU and disk); a job per run_id; identical requests in flight share one job.
EXECUTOR = ThreadPoolExecutor(max_workers=int(os.getenv("CR_CORRIDOR_WORKERS", "1")), thread_name_prefix="corridor")
JOBS: dict[str, dict] = {}
INFLIGHT: dict[str, tuple[str, Future]] = {}
_jobs_lock = threading.Lock()


class SimError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _ensure_sumo_on_path():
    """`make dev` activates .venv (which has sumo and netconvert); a bare `uvicorn` may not."""
    venv_bin = str(Path(sys.executable).parent)
    if shutil.which("sumo") is None and venv_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")


def _simulate(run_id: str, key: str, ivs: list[dict], body: CorridorRunIn) -> dict:
    """Worker thread: one real corridor run. Returns the stored C5 result or raises SimError (plain language)."""
    import inspect, subprocess
    JOBS[run_id].update(status="running", started=time.time())
    _ensure_sumo_on_path()
    if not CALIBRATION.exists():
        raise SimError(500, "The corridor simulation is not calibrated yet (sim/corridor/calibration.json is missing). "
                            "Run `python sim/corridor/corridor_runner.py calibrate` inside .venv, then try again.")
    try:
        sys.path.insert(0, str(SIM_CORRIDOR))
        import corridor_runner
        kwargs = {"interventions": ivs, "volume_scale": body.volume_scale, "run_id": run_id, "frames": True}
        params = inspect.signature(corridor_runner.run).parameters
        extra = []
        for k in ("window", "minutes"):
            v = getattr(body, k)
            if v is not None:
                if k in params:
                    kwargs[k] = v
                else:
                    extra.append(f"{k}={v}")
        res = corridor_runner.run(**kwargs)
        if extra:
            res["warnings"].append(f"The corridor simulation does not take {', '.join(extra)} yet; this run is the calibrated "
                                   f"typical day ({res['time'].get('label', '')}).")
    except ValueError as e:      # a template refused the change (bad params)
        raise SimError(400, f"That change cannot be built: {e}")
    except RuntimeError as e:    # gridlock, netconvert failure
        raise SimError(500, f"The simulation could not finish: {e}")
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else str(e.stderr or "")
        tail = err.strip()[-400:]
        raise SimError(500, f"SUMO stopped with an error ({Path(str(e.cmd[0])).name} exit {e.returncode}): {tail or 'no message'}")
    except FileNotFoundError as e:
        raise SimError(500, f"A simulation file or program is missing ({e}). Is SUMO installed? Run `make setup-sim`.")
    except ImportError as e:
        raise SimError(500, f"The simulation needs sumolib ({e}). Run `make setup-sim`.")
    except Exception as e:
        raise SimError(500, f"The simulation failed unexpectedly ({type(e).__name__}: {e})")
    res["run_id"] = run_id
    window = getattr(corridor_runner, "FRAMES", None)
    if res.get("frames_path") and window and len(window) >= 2 and Path(res["frames_path"]).exists():
        trim_frames(Path(res["frames_path"]), window[0], window[1])
    res = store(res, body)
    with db() as c:
        c.execute("INSERT OR REPLACE INTO corridor_cache VALUES(?,?,?)", (key, run_id, time.time()))
    return res


def _job(run_id: str, key: str, ivs: list[dict], body: CorridorRunIn) -> dict:
    try:
        res = _simulate(run_id, key, ivs, body)
        JOBS[run_id].update(status="done", finished=time.time())
        return res
    except SimError as e:
        JOBS[run_id].update(status="failed", finished=time.time(), error=e.message, http_status=e.status)
        out = SIM_OUT / "corridor" / run_id   # a failed run's files are of no use and disk is tight
        shutil.rmtree(out, ignore_errors=True)
        raise
    finally:
        with _jobs_lock:
            INFLIGHT.pop(key, None)
            busy = {rid for rid, _ in INFLIGHT.values()}
        prune_runs(busy=busy)


def submit(ivs: list[dict], body: CorridorRunIn) -> tuple[str, Future | dict]:
    """(run_id, stored result) on a cache hit; else (run_id, future) of a new or already-running identical job."""
    key = cache_key(ivs, body)
    hit = cache_lookup(key)
    if hit:
        return hit["run_id"], hit | {"cached": True}
    with _jobs_lock:
        if key in INFLIGHT:
            return INFLIGHT[key]
        run_id = "rc_" + uuid.uuid4().hex[:8]
        JOBS[run_id] = {"status": "queued", "key": key, "queued": time.time(), "interventions": ivs,
                        "volume_scale": body.volume_scale}
        fut = EXECUTOR.submit(_job, run_id, key, ivs, body)
        INFLIGHT[key] = (run_id, fut)
    return run_id, fut


def run_blocking(body: CorridorRunIn) -> dict:
    """POST /corridor/runs for callers on a worker thread (the AI agent, case reviews): same validation, mock,
    cache and one-run-at-a-time queue, but blocks until the C5 result is stored. Raises HTTPException (400/500)."""
    ivs = validate(body)
    if MOCK:
        return store(mock_result(ivs, body), body)
    run_id, job = submit(ivs, body)
    if isinstance(job, dict):    # cache hit
        return job
    try:
        return job.result()
    except SimError as e:
        raise HTTPException(e.status, e.message)


def is_cached(body: CorridorRunIn) -> bool:
    """True when POST /corridor/runs would answer instantly (mock mode, or a stored identical run)."""
    return MOCK or cache_lookup(cache_key(validate(body), body)) is not None


@router.post("/corridor/runs")
async def corridor_run(body: CorridorRunIn, request: Request):
    """Simulate the corridor with interventions -> C5 result. `?async=1`: return {run_id, status} at once (202)."""
    ivs = validate(body)
    is_async = request.query_params.get("async") in ("1", "true", "yes")
    if MOCK:
        res = store(mock_result(ivs, body), body)
        return JSONResponse({"run_id": res["run_id"], "status": "done", "result": res}, 202) if is_async else res
    run_id, job = submit(ivs, body)
    if isinstance(job, dict):    # cache hit
        return JSONResponse({"run_id": run_id, "status": "done", "cached": True, "result": job}, 202) if is_async else job
    if is_async:
        return JSONResponse({"run_id": run_id, "status": JOBS[run_id]["status"]}, 202)
    try:
        return await asyncio.wrap_future(job)
    except SimError as e:
        raise HTTPException(e.status, e.message)


@router.get("/corridor/calibration")
def corridor_calibration():
    """How well the simulation matches TomTom: the calibrated knobs and the last round's fit (sim/corridor/calibration.json)."""
    if not CALIBRATION.exists():
        raise HTTPException(404, "The corridor simulation is not calibrated yet (sim/corridor/calibration.json is missing).")
    return json.loads(CALIBRATION.read_text())


@router.get("/corridor/runs/{run_id}")
def corridor_run_status(run_id: str):
    """Status of a corridor run: queued | running | done (with result) | failed (with a plain-language error)."""
    job = JOBS.get(run_id)
    if job is None or job["status"] == "done":
        res = stored_run(run_id)
        if res is None:
            raise HTTPException(404, "corridor run not found (runs in progress are forgotten when the API restarts)")
        return {"run_id": run_id, "status": "done", "result": res}
    now = time.time()
    out = {"run_id": run_id, "status": job["status"], "elapsed_s": round(now - job.get("started", job["queued"]), 1),
           "queued_s": round(job.get("started", now) - job["queued"], 1)}
    if job["status"] == "failed":
        out |= {"error": job["error"], "http_status": job["http_status"]}
    return out


# ---------- GET /corridor/junctions/live ----------
def _f(v: str):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@router.get("/corridor/junctions/live")
def corridor_junctions_live(window_minutes: int = 60):
    """Latest TomTom Junction Analytics snapshot per configured corridor junction and approach, plus the mean of the
    last `window_minutes` (counted back from that junction's latest snapshot, so it also works on an old file)."""
    if not JA_LIVE.exists():
        raise HTTPException(404, f"{JA_LIVE.name} not found: run the corridor junction collector "
                                 "(data/tomtom), or set CR_CORRIDOR_JA_LIVE to the CSV's path")
    config = json.loads(JA_CONFIG.read_text())["junctions"] if JA_CONFIG.exists() else []
    rows: dict[str, list[dict]] = {}
    for r in csv.DictReader(JA_LIVE.open()):
        rows.setdefault(r["junction_id"], []).append(r)
    fields = ("delay_s", "usual_delay_s", "queue_m", "volume_per_hour", "travel_time_s", "free_flow_travel_time_s")
    junctions = []
    # every configured junction (a new line in the config shows up on the next request), plus any in the CSV only
    ids = sorted({j["corridor_id"] for j in config} | set(rows))
    for jid in ids:
        cfg = next((j for j in config if j["corridor_id"] == jid), {})
        rs = rows.get(jid, [])
        if not rs:
            junctions.append({"id": jid, "name": cfg.get("name", jid), "tomtom_id": cfg.get("tomtom_id"), "time": None,
                              "approaches": [], "note": "no snapshot collected yet"})
            continue
        latest_t = max(datetime.fromisoformat(r["time"]) for r in rs)
        since = latest_t - timedelta(minutes=window_minutes)
        approaches: dict[str, dict] = {}
        for r in rs:
            t = datetime.fromisoformat(r["time"])
            a = approaches.setdefault(r["approach_id"], {"approach_id": r["approach_id"], "name": r["approach"], "_t": None, "_win": []})
            if a["_t"] is None or t >= a["_t"]:
                a.update({"_t": t, "time": r["time"], "closed": r.get("closed") == "True",
                          **{k: _f(r.get(k)) for k in fields}})
            if t >= since:
                a["_win"].append(r)
        out = []
        for a in approaches.values():
            win = a.pop("_win")
            a.pop("_t")
            a["stale"] = a["time"] != latest_t.isoformat()   # approach missing from the latest snapshot
            mean = {"samples": len(win), "from": since.isoformat(), "to": latest_t.isoformat()}
            for k in ("delay_s", "usual_delay_s", "queue_m", "volume_per_hour"):
                vals = [v for v in (_f(r.get(k)) for r in win) if v is not None]
                mean[k] = round(sum(vals) / len(vals), 1) if vals else None
            a[f"last_{window_minutes}min"] = mean
            out.append(a)
        out.sort(key=lambda a: -(a["volume_per_hour"] or 0))
        age = (datetime.now(latest_t.tzinfo) - latest_t).total_seconds()
        junctions.append({"id": jid, "name": cfg.get("name", rs[0]["junction"]), "tomtom_id": cfg.get("tomtom_id"),
                          "time": latest_t.isoformat(), "age_s": round(age), "approaches": out})
    return {"source": "TomTom Junction Analytics, one live junction per corridor junction (data/tomtom/junction/corridor_junctions.json)",
            "file": str(JA_LIVE.name), "window_minutes": window_minutes,
            "labels": {"delay_s": "measured", "usual_delay_s": "measured", "travel_time_s": "measured",
                       "free_flow_travel_time_s": "measured", "queue_m": "estimated", "volume_per_hour": "estimated"},
            "junctions": junctions}


# ---------- buildings for the 3D view ----------
@router.get("/corridor/buildings")
def corridor_buildings_index():
    """Index of the building footprints around each corridor point (data/corridor/buildings/index.json)."""
    path = BUILDINGS / "index.json"
    if not path.exists():
        raise HTTPException(404, "corridor buildings are not there yet (data/corridor/buildings/index.json is missing)")
    return FileResponse(path, media_type="application/json")


@router.get("/corridor/buildings/{point_id}")
def corridor_buildings(point_id: str):
    """Building footprints around one corridor point (A_lingampally, j01..j11, B_lakdikapul) as GeoJSON."""
    ids = [p["id"] for p in corridor_def()["points"]]
    if point_id not in ids:   # only known ids reach the file system: no path traversal
        raise HTTPException(404, f"unknown corridor point {point_id!r}; use one of {', '.join(ids)}")
    path = BUILDINGS / f"{point_id}.geojson"
    if not path.exists():
        raise HTTPException(404, f"no buildings for {point_id} yet (data/corridor/buildings/{point_id}.geojson is missing)")
    return FileResponse(path, media_type="application/geo+json")
