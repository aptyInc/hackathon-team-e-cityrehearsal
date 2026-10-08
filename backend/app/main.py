"""CityRehearsal backend (C4 workflow API). Owner: AI agent workstream.

MOCK_SIM=1 serves sample C2 results and replays sample C1 frames from /contracts/samples,
so frontend and agent work never wait for SUMO. Set MOCK_SIM=0 once /sim provides a runner.
"""
import asyncio, hashlib, json, os, sqlite3, time, uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MOCK = os.getenv("MOCK_SIM", "1") == "1"
SAMPLES = ROOT / "contracts" / "samples"
DB = ROOT / "backend" / "cityrehearsal.db"

app = FastAPI(title="CityRehearsal API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
def run_simulation(variant_id: str, template: str, volume_scale: float) -> dict:
    if MOCK:
        samples = json.loads((SAMPLES / "run_results.sample.json").read_text())
        key = variant_id if variant_id in samples else ("flyover_3lane_400m" if template == "flyover" else "baseline")
        result = json.loads(json.dumps(samples[key]))
        for j in result["junctions"]:  # crude illustrative scaling for sensitivity tests in mock mode
            j["avg_delay_s"] = round(j["avg_delay_s"] * volume_scale ** 2, 1)
        result["inputs"]["volume_scale"] = volume_scale
        result["variant_id"] = variant_id
        return result
    # TODO (sim workstream): call the real SUMO runner and return a C2 dict
    raise HTTPException(501, "Real SUMO runner not wired yet; set MOCK_SIM=1")


# ---------- endpoints ----------
@app.get("/health")
def health():
    return {"status": "ok", "mock": MOCK}


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
    result = run_simulation(body.variant_id, template, body.volume_scale)
    result["run_id"] = "r_" + uuid.uuid4().hex[:8]
    with db() as c:
        c.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)",
                  (result["run_id"], body.case_id, body.variant_id, body.run_by, json.dumps(result), time.time()))
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
    frames = json.loads((SAMPLES / "vehicle_frames.sample.json").read_text()) if MOCK else []
    for f in frames:  # TODO (sim workstream): stream real C1 frames when MOCK_SIM=0
        await ws.send_json(f)
        await asyncio.sleep(0.1)
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
