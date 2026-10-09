"""Corridor decision workflow: proposed -> in_review -> decided. Owner: AI agent workstream.

    POST /corridor/cases                 {title, run_ids, brief_id?, created_by?} -> case (stage "proposed")
    POST /corridor/cases/{id}/review     {reviewer, volume_scale?, note?} -> re-runs every option in the case (and the
                                         baseline) at that volume, appends the results; stage "in_review"
    POST /corridor/cases/{id}/decide     {decider, decision: approve|reject|revise, reason} -> stage "decided"
    GET  /corridor/cases/{id}            case with runs, events, fingerprints
    GET  /corridor/cases/{id}/verify     {ok, events: [{seq, fingerprint, recomputed, matches, prev_ok}], evidence: [...]}
    GET  /corridor/cases                 list, each row with its latest decision and decided_at

Append-only: runs and events are never changed or deleted. Every event carries a SHA-256 fingerprint of the evidence
it rests on (run fingerprints, brief fingerprint, its own body) chained to the previous event's fingerprint, so any
later change to the record shows. A "revise" decision reopens the case for another review and decision.
"""
import hashlib, json, time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import corridor as cor
from .agent import store as agent_store
from .agent.tools import ivs, label, load_run, mins, new_id, vol

router = APIRouter()

with cor.db() as _c:
    _c.executescript("""
    CREATE TABLE IF NOT EXISTS corridor_cases(id TEXT PRIMARY KEY, title TEXT, created_by TEXT, brief_id TEXT,
        stage TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS corridor_case_runs(case_id TEXT, run_id TEXT, role TEXT, added_by TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS corridor_case_events(case_id TEXT, seq INTEGER, kind TEXT, actor TEXT, body TEXT,
        fingerprint TEXT, prev TEXT, created REAL, PRIMARY KEY(case_id, seq));
    """)
    if "volume_scale" not in [r[1] for r in _c.execute("PRAGMA table_info(corridor_case_runs)")]:
        _c.execute("ALTER TABLE corridor_case_runs ADD COLUMN volume_scale REAL")   # the level the run was asked for


class CaseIn(BaseModel):
    title: str
    run_ids: list[str]
    brief_id: str | None = None
    created_by: str = "engineer"


class ReviewIn(BaseModel):
    reviewer: str
    volume_scale: float = 1.0
    note: str = ""


class DecideIn(BaseModel):
    decider: str
    decision: str   # approve | reject | revise
    reason: str


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _run_fp(res: dict) -> str:
    return res.get("fingerprint") or cor.fingerprint(res)


def _event(case_id: str, kind: str, actor: str, body: dict) -> str:
    with cor.db() as c:
        last = c.execute("SELECT seq, fingerprint FROM corridor_case_events WHERE case_id=? ORDER BY seq DESC LIMIT 1",
                         (case_id,)).fetchone()
        seq, prev = (last["seq"] + 1, last["fingerprint"]) if last else (0, None)
        fp = _sha({"case_id": case_id, "seq": seq, "kind": kind, "actor": actor, "body": body, "prev": prev})
        c.execute("INSERT INTO corridor_case_events VALUES(?,?,?,?,?,?,?,?)",
                  (case_id, seq, kind, actor, json.dumps(body), fp, prev, time.time()))
    return fp


def _add_runs(case_id: str, runs: list[dict], role: str, by: str, volume_scale: float | None = None):
    with cor.db() as c:
        for r in runs:
            c.execute("INSERT INTO corridor_case_runs(case_id, run_id, role, added_by, created, volume_scale) "
                      "VALUES(?,?,?,?,?,?)", (case_id, r["run_id"], role, by, time.time(),
                                             volume_scale if volume_scale is not None else vol(r)))


def _row(c, case_id: str):
    row = c.execute("SELECT * FROM corridor_cases WHERE id=?", (case_id,)).fetchone()
    if not row:
        raise HTTPException(404, "corridor case not found")
    return row


@router.get("/corridor/cases")
def list_cases():
    """Every corridor case, newest first, with its latest decision (approve/reject/revise) and when it was made."""
    with cor.db() as c:
        rows = c.execute("""SELECT k.*, (SELECT COUNT(*) FROM corridor_case_runs r WHERE r.case_id=k.id) AS runs
                            FROM corridor_cases k ORDER BY created DESC""").fetchall()
        last = {}
        for e in c.execute("SELECT case_id, body, created FROM corridor_case_events WHERE kind='decision' ORDER BY seq"):
            last[e["case_id"]] = (json.loads(e["body"]).get("decision"), e["created"])
    return [{"case_id": r["id"], "title": r["title"], "stage": r["stage"], "brief_id": r["brief_id"],
             "created_by": r["created_by"], "created": r["created"], "runs": r["runs"],
             "decision": last.get(r["id"], (None, None))[0], "decided_at": last.get(r["id"], (None, None))[1]}
            for r in rows]


@router.get("/corridor/cases/{case_id}")
def get_case(case_id: str):
    with cor.db() as c:
        row = _row(c, case_id)
        links = c.execute("SELECT * FROM corridor_case_runs WHERE case_id=? ORDER BY created", (case_id,)).fetchall()
        events = c.execute("SELECT * FROM corridor_case_events WHERE case_id=? ORDER BY seq", (case_id,)).fetchall()
    runs, fps = [], {}
    for l in links:
        res = load_run(l["run_id"])
        fps[res["run_id"]] = _run_fp(res)
        runs.append({"run_id": res["run_id"], "role": l["role"], "added_by": l["added_by"],
                     "option": label(ivs(res)), "interventions": ivs(res),
                     "volume_scale": l["volume_scale"] if l["volume_scale"] is not None else vol(res),
                     "total_min": mins(res["journey"]["total_s"]),
                     "inputs": res["inputs"], "warnings": res.get("warnings", []), "sample": bool(res.get("sample")),
                     "fingerprint": fps[res["run_id"]]})
    if row["brief_id"]:
        fps["brief:" + row["brief_id"]] = agent_store.get_brief(row["brief_id"])["fingerprint"]
    evs = [{"seq": e["seq"], "kind": e["kind"], "actor": e["actor"], "body": json.loads(e["body"]),
            "fingerprint": e["fingerprint"], "prev": e["prev"], "created": e["created"]} for e in events]
    decision = next((e for e in reversed(evs) if e["kind"] == "decision"), None)
    return {"case_id": row["id"], "title": row["title"], "stage": row["stage"], "created_by": row["created_by"],
            "brief_id": row["brief_id"], "created": row["created"], "runs": runs, "fingerprints": fps, "events": evs,
            "decision": decision and decision["body"], "fingerprint": evs[-1]["fingerprint"] if evs else None}


@router.post("/corridor/cases")
def create_case(body: CaseIn):
    if not body.title.strip() or not body.run_ids:
        raise HTTPException(400, "a case needs a title and at least one run_id")
    runs = [load_run(r) for r in dict.fromkeys(body.run_ids)]
    brief_fp = agent_store.get_brief(body.brief_id)["fingerprint"] if body.brief_id else None
    cid = new_id("cc_")
    with cor.db() as c:
        c.execute("INSERT INTO corridor_cases VALUES(?,?,?,?,?,?)",
                  (cid, body.title, body.created_by, body.brief_id, "proposed", time.time()))
    _add_runs(cid, runs, "option", body.created_by)
    _event(cid, "proposed", body.created_by, {"title": body.title, "brief_id": body.brief_id, "brief_fingerprint": brief_fp,
                                              "runs": {r["run_id"]: _run_fp(r) for r in runs}})
    return get_case(cid)


@router.post("/corridor/cases/{case_id}/review")
def review(case_id: str, body: ReviewIn):
    """Re-run each option of the case (and the no-change baseline) at `volume_scale`. With real simulations this takes
    1-2 minutes per option not already cached."""
    case = get_case(case_id)
    if case["stage"] == "decided" and (case["decision"] or {}).get("decision") != "revise":
        raise HTTPException(409, "this case is decided; open a new case to revisit it")
    if not body.reviewer.strip():
        raise HTTPException(400, "reviewer is required")
    options = {}
    for r in case["runs"]:
        if r["role"] == "option":
            options.setdefault(json.dumps(ivs(r), sort_keys=True), ivs(r))
    options.setdefault("[]", [])
    results = []
    for option in options.values():
        res = cor.run_blocking(cor.CorridorRunIn(interventions=option, volume_scale=body.volume_scale,
                                                 run_by=body.reviewer, case_id=case_id))
        results.append(res)
    _add_runs(case_id, results, "review", body.reviewer, body.volume_scale)
    base = next(r for r in results if not ivs(r))
    summary = [{"run_id": r["run_id"], "option": label(ivs(r)), "total_min": mins(r["journey"]["total_s"]),
                "change_vs_baseline_min": round((r["journey"]["total_s"] - base["journey"]["total_s"]) / 60, 1),
                "fingerprint": _run_fp(r)} for r in results]
    _event(case_id, "review", body.reviewer, {"volume_scale": body.volume_scale, "note": body.note, "results": summary})
    with cor.db() as c:
        c.execute("UPDATE corridor_cases SET stage='in_review' WHERE id=?", (case_id,))
    return get_case(case_id)


@router.post("/corridor/cases/{case_id}/decide")
def decide(case_id: str, body: DecideIn):
    case = get_case(case_id)
    if body.decision not in ("approve", "reject", "revise") or not body.reason.strip() or not body.decider.strip():
        raise HTTPException(400, "decision must be approve, reject or revise, with a decider and a reason")
    if case["stage"] != "in_review":
        raise HTTPException(409, f"a case is decided after a review re-run (stage is {case['stage']!r}); "
                                 "POST /corridor/cases/{id}/review first")
    _event(case_id, "decision", body.decider, {"decision": body.decision, "reason": body.reason,
                                               "evidence": case["fingerprints"], "review_fingerprint": case["fingerprint"]})
    with cor.db() as c:
        c.execute("UPDATE corridor_cases SET stage='decided' WHERE id=?", (case_id,))
    return get_case(case_id)


@router.get("/corridor/cases/{case_id}/verify")
def verify_case(case_id: str):
    """Recompute every event's SHA-256 on the server (same JSON encoding as when it was written) and check the chain;
    also re-check the fingerprints of the runs and the brief the events rest on against what is stored now."""
    with cor.db() as c:
        _row(c, case_id)
        events = c.execute("SELECT * FROM corridor_case_events WHERE case_id=? ORDER BY seq", (case_id,)).fetchall()
    out, prev_fp, recorded = [], None, {}
    for e in events:
        body = json.loads(e["body"])
        recomputed = _sha({"case_id": case_id, "seq": e["seq"], "kind": e["kind"], "actor": e["actor"], "body": body,
                           "prev": e["prev"]})
        out.append({"seq": e["seq"], "kind": e["kind"], "fingerprint": e["fingerprint"], "recomputed": recomputed,
                    "matches": recomputed == e["fingerprint"], "prev_ok": e["prev"] == prev_fp})
        prev_fp = e["fingerprint"]
        recorded |= body.get("runs") or {}
        recorded |= body.get("evidence") or {}
        recorded |= {r["run_id"]: r["fingerprint"] for r in body.get("results") or []}
        if body.get("brief_id") and body.get("brief_fingerprint"):
            recorded["brief:" + body["brief_id"]] = body["brief_fingerprint"]
    evidence = []
    for key, fp in recorded.items():
        if key.startswith("brief:"):
            try:
                b = agent_store.get_brief(key[6:])
                now = hashlib.sha256(json.dumps({"markdown": b["markdown"], "fingerprints": b["fingerprints"]},
                                                sort_keys=True).encode()).hexdigest()
            except HTTPException:
                now = None
        else:
            res = cor.stored_run(key)
            now = cor.fingerprint(res) if res else None
        evidence.append({"id": key, "recorded": fp, "recomputed": now, "matches": now == fp})
    ok = bool(out) and all(e["matches"] and e["prev_ok"] for e in out) and all(x["matches"] for x in evidence)
    return {"case_id": case_id, "ok": ok, "events": out, "evidence": evidence,
            "method": "sha256 of json.dumps({case_id, seq, kind, actor, body, prev}, sort_keys=True), recomputed server-side"}
