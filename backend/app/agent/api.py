"""Planning assistant endpoints. Owner: AI agent workstream.

    POST /agent/chat            {session_id?, message} -> {session_id, turn_id, reply, steps, run_ids, brief_id, usage}
    POST /agent/chat?async=1    same body -> 202 {session_id, turn_id, status}; poll GET /agent/turns/{turn_id}
    GET  /agent/turns/{id}      {turn_id, session_id, status: running|done|failed, steps, run_ids, reply?, brief_id?, error?}
    GET  /agent/sessions/{id}   {session_id, model, turns: [...], brief_ids}
    GET  /briefs/{brief_id}     {brief_id, markdown, run_ids, fingerprints, fingerprint, recommendation, created_at}
"""
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import agent, store

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
