"""Planning assistant endpoints. Owner: AI agent workstream.

    POST /agent/chat            {session_id?, message} -> {session_id, turn_id, reply, steps, run_ids, brief_id, usage}
    POST /agent/chat?async=1    same body -> 202 {session_id, turn_id, status}; poll GET /agent/turns/{turn_id}
    GET  /agent/turns/{id}      {turn_id, session_id, status: running|done|failed, steps, run_ids, reply?, brief_id?, error?}
    GET  /agent/sessions/{id}   {session_id, model, turns: [...], brief_ids}
    GET  /briefs/{brief_id}     {brief_id, markdown, run_ids, fingerprints, fingerprint, recommendation, created_at}
    GET  /agent/suggestions     {questions: [...], junctions, ground_junctions, elevated} starter questions for the chat UI
    POST /agent/advise/{jid}    ?async=1 [&weather=heavy_rain&fresh=1] -> 202 {advice_id, junction, status}; sync -> the advice row
    GET  /agent/advice          {model_version, junctions: [advice row per junction (latest; `stale` when the sim changed)]}
    GET  /agent/advice/{jid}    latest advice row for one junction (404 when none); ?weather=heavy_rain for a what-if row
    GET  /agent/advice/id/{id}  one advice row by id (status running|done|failed)
    An advice row: {advice_id, junction, weather, status, model_version, stale, brief_id, run_ids, fingerprint, advice: {...}}
    (advice shape: advisor.ADVICE_SHAPE: verdict, verdict_code, headline, options[], reasons[], caveats[], data, baseline).
"""
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import advisor, agent, store

router = APIRouter()


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str


def _start(body: ChatIn) -> tuple[str, str]:
    if not body.message.strip():
        raise HTTPException(400, "message is empty")
    try:
        agent.client()   # fail fast (503) when the key is missing, before anything is stored
    except agent.AgentUnavailable as e:
        raise HTTPException(e.status, e.message)
    sid = store.ensure_session(body.session_id, agent.MODEL)
    if agent.session_lock(sid).locked():
        raise HTTPException(409, "This conversation is still working on the previous message.")
    return sid, store.create_turn(sid, body.message)


@router.post("/agent/chat")
def chat(body: ChatIn, request: Request):
    """One message to the planning assistant. With real simulations a turn can take several minutes; use ?async=1
    and poll GET /agent/turns/{turn_id} to show progress."""
    sid, tid = _start(body)
    if request.query_params.get("async") in ("1", "true", "yes"):
        def work():
            try:
                agent.run_turn(sid, body.message, tid)
            except agent.AgentUnavailable:
                pass   # already recorded on the turn
        threading.Thread(target=work, name=f"agent-{tid}", daemon=True).start()
        return JSONResponse({"session_id": sid, "turn_id": tid, "status": "running"}, 202)
    try:
        return agent.run_turn(sid, body.message, tid)
    except agent.AgentUnavailable as e:
        raise HTTPException(e.status, e.message)


@router.get("/agent/turns/{turn_id}")
def turn(turn_id: str):
    return store.get_turn(turn_id)


@router.get("/agent/sessions/{session_id}")
def session(session_id: str):
    return store.get_session(session_id)


@router.get("/briefs/{brief_id}")
def brief(brief_id: str):
    return store.get_brief(brief_id)


SUGGESTIONS = ["What should we do at Nanal Nagar?",
               "Can we build a flyover at ISB Rd / DLF? If not, what else?",
               "Where does the Lingampally to Lakdikapul trip lose the most time?",
               "Would a signal retime at Rethibowli help, and what does heavy rain do to it?"]


@router.get("/agent/suggestions")
def suggestions():
    from .tools import points
    return {"questions": SUGGESTIONS, "junctions": {j: n for j, n in points().items() if j.startswith("j")},
            "ground_junctions": advisor.GROUND, "elevated": advisor.ELEVATED}


@router.post("/agent/advise/{junction_id}")
def advise(junction_id: str, request: Request):
    """Compute (or recompute) the advisor's answer for one junction with real simulations through the same queue as the
    chat; `?async=1` returns at once and the row is filled when done (poll GET /agent/advice/id/{advice_id})."""
    from .. import corridor as _cor
    jid = junction_id.lower()
    if jid not in _cor.junction_ids():
        raise HTTPException(400, f"unknown junction {jid!r}; use one of {', '.join(_cor.junction_ids())}")
    q = request.query_params
    weather = q.get("weather") or None
    if weather and weather not in _cor.WEATHER:
        raise HTTPException(400, f"weather must be one of {', '.join(_cor.WEATHER)}")
    ver = advisor.model_version()
    if q.get("fresh") not in ("1", "true", "yes"):
        hit = store.latest_advice(jid, ver, weather)
        if hit and not hit["stale"]:
            return hit
    aid = store.create_advice(jid, weather, ver)

    def work():
        from .tools import Context
        try:
            adv = advisor.advise(jid, advisor.LocalRunner(Context(session_id="advisor", max_runs=advisor.ADVISE_MAX_RUNS)), weather)
            store.finish_advice(aid, adv)
        except Exception as e:
            store.finish_advice(aid, None, f"{type(e).__name__}: {e}")
    if q.get("async") in ("1", "true", "yes"):
        threading.Thread(target=work, name=f"advise-{aid}", daemon=True).start()
        return JSONResponse({"advice_id": aid, "junction": jid, "weather": weather, "status": "running"}, 202)
    work()
    return store.get_advice(aid, ver)


@router.get("/agent/advice")
def advice_all():
    ver = advisor.model_version()
    return {"model_version": ver, "ground_junctions": advisor.GROUND, "elevated": advisor.ELEVATED, "junctions": store.all_advice(ver)}


@router.get("/agent/advice/id/{advice_id}")
def advice_by_id(advice_id: str):
    return store.get_advice(advice_id, advisor.model_version())


@router.get("/agent/advice/{junction_id}")
def advice_one(junction_id: str, weather: str | None = None):
    hit = store.latest_advice(junction_id.lower(), advisor.model_version(), weather or None, done_only=False)
    if not hit:
        raise HTTPException(404, f"no advice for {junction_id} yet: POST /agent/advise/{junction_id}?async=1")
    return hit
