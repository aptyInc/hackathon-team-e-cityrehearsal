"""SQLite storage for the planning assistant: sessions (raw Claude message history), turns (what the UI shows) and
decision briefs. Same database as the rest of the API (backend/cityrehearsal.db). Append-only except a turn's own
progress fields while it runs."""
import hashlib, json, time

from fastapi import HTTPException

from ..corridor import db
from .tools import new_id

with db() as _c:
    _c.executescript("""
    CREATE TABLE IF NOT EXISTS agent_sessions(id TEXT PRIMARY KEY, model TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS agent_messages(session_id TEXT, seq INTEGER, turn_id TEXT, role TEXT, content TEXT,
        created REAL, PRIMARY KEY(session_id, seq));
    CREATE TABLE IF NOT EXISTS agent_turns(id TEXT PRIMARY KEY, session_id TEXT, status TEXT, message TEXT, reply TEXT,
        steps TEXT, run_ids TEXT, brief_id TEXT, error TEXT, http_status INTEGER, usage TEXT, created REAL, finished REAL);
    CREATE TABLE IF NOT EXISTS briefs(id TEXT PRIMARY KEY, session_id TEXT, markdown TEXT, run_ids TEXT,
        fingerprints TEXT, recommendation TEXT, fingerprint TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS agent_advice(id TEXT PRIMARY KEY, junction_id TEXT, weather TEXT, status TEXT, model_version TEXT,
        advice TEXT, brief_id TEXT, run_ids TEXT, fingerprint TEXT, error TEXT, created REAL, finished REAL);
    """)


def ensure_session(session_id: str | None, model: str) -> str:
    with db() as c:
        if session_id and c.execute("SELECT 1 FROM agent_sessions WHERE id=?", (session_id,)).fetchone():
            return session_id
        sid = session_id or new_id("s_")
        c.execute("INSERT INTO agent_sessions VALUES(?,?,?)", (sid, model, time.time()))
    return sid


def history(session_id: str) -> list[dict]:
    with db() as c:
        rows = c.execute("SELECT role, content FROM agent_messages WHERE session_id=? ORDER BY seq", (session_id,)).fetchall()
    return [{"role": r["role"], "content": json.loads(r["content"])} for r in rows]


def append_messages(session_id: str, turn_id: str, messages: list[dict]):
    with db() as c:
        seq = c.execute("SELECT COALESCE(MAX(seq), -1) + 1 FROM agent_messages WHERE session_id=?", (session_id,)).fetchone()[0]
        for k, m in enumerate(messages):
            c.execute("INSERT INTO agent_messages VALUES(?,?,?,?,?,?)",
                      (session_id, seq + k, turn_id, m["role"], json.dumps(m["content"]), time.time()))


def create_turn(session_id: str, message: str) -> str:
    tid = new_id("t_")
    with db() as c:
        c.execute("INSERT INTO agent_turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (tid, session_id, "running", message, None, "[]", "[]", None, None, None, None, time.time(), None))
    return tid


def update_turn(turn_id: str, **fields):
    for k in ("steps", "run_ids", "usage"):
        if k in fields:
            fields[k] = json.dumps(fields[k])
    sets = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE agent_turns SET {sets} WHERE id=?", (*fields.values(), turn_id))


def _turn(r) -> dict:
    out = {"turn_id": r["id"], "session_id": r["session_id"], "status": r["status"], "message": r["message"],
           "reply": r["reply"], "steps": json.loads(r["steps"]), "run_ids": json.loads(r["run_ids"]),
           "brief_id": r["brief_id"], "created": r["created"], "finished": r["finished"]}
    if r["error"]:
        out |= {"error": r["error"], "http_status": r["http_status"]}
    if r["usage"]:
        out["usage"] = json.loads(r["usage"])
    return out


def get_turn(turn_id: str) -> dict:
    with db() as c:
        r = c.execute("SELECT * FROM agent_turns WHERE id=?", (turn_id,)).fetchone()
    if not r:
        raise HTTPException(404, "turn not found")
    return _turn(r)


def get_session(session_id: str) -> dict:
    with db() as c:
        s = c.execute("SELECT * FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
        if not s:
            raise HTTPException(404, "session not found")
        turns = [_turn(r) for r in c.execute("SELECT * FROM agent_turns WHERE session_id=? ORDER BY created", (session_id,))]
        briefs = [r["id"] for r in c.execute("SELECT id FROM briefs WHERE session_id=? ORDER BY created", (session_id,))]
    return {"session_id": session_id, "model": s["model"], "created": s["created"], "turns": turns, "brief_ids": briefs}


def save_brief(session_id: str, markdown: str, run_ids: list[str], fingerprints: dict, recommendation: str) -> dict:
    bid = new_id("b_")
    fp = hashlib.sha256(json.dumps({"markdown": markdown, "fingerprints": fingerprints}, sort_keys=True).encode()).hexdigest()
    with db() as c:
        c.execute("INSERT INTO briefs VALUES(?,?,?,?,?,?,?,?)", (bid, session_id, markdown, json.dumps(run_ids),
                                                                json.dumps(fingerprints), recommendation, fp, time.time()))
    return get_brief(bid)


def get_brief(brief_id: str) -> dict:
    with db() as c:
        r = c.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone()
    if not r:
        raise HTTPException(404, "brief not found")
    return {"brief_id": r["id"], "session_id": r["session_id"], "markdown": r["markdown"], "run_ids": json.loads(r["run_ids"]),
            "fingerprints": json.loads(r["fingerprints"]), "recommendation": r["recommendation"],
            "fingerprint": r["fingerprint"], "created_at": r["created"]}


# ---------- junction advice (advisor.py): append-only, one row per computation ----------
def create_advice(junction_id: str, weather: str | None, model_version: str) -> str:
    aid = new_id("adv_")
    with db() as c:
        c.execute("INSERT INTO agent_advice VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  (aid, junction_id, weather, "running", model_version, None, None, "[]", None, None, time.time(), None))
    return aid


def finish_advice(aid: str, advice: dict | None, error: str | None = None):
    fp = hashlib.sha256(json.dumps(advice, sort_keys=True, default=str).encode()).hexdigest() if advice else None
    with db() as c:
        c.execute("UPDATE agent_advice SET status=?, advice=?, brief_id=?, run_ids=?, fingerprint=?, error=?, finished=? WHERE id=?",
                  ("done" if advice else "failed", json.dumps(advice, default=str) if advice else None,
                   (advice or {}).get("brief_id"), json.dumps((advice or {}).get("run_ids", [])), fp, error, time.time(), aid))


def _advice_row(r, current_version: str) -> dict:
    adv = json.loads(r["advice"]) if r["advice"] else None
    out = {"advice_id": r["id"], "junction": r["junction_id"], "weather": r["weather"], "status": r["status"],
           "model_version": r["model_version"], "stale": r["model_version"] != current_version, "fingerprint": r["fingerprint"],
           "brief_id": r["brief_id"], "run_ids": json.loads(r["run_ids"] or "[]"), "created": r["created"], "finished": r["finished"],
           "advice": adv}
    if r["error"]:
        out["error"] = r["error"]
    return out


def get_advice(aid: str, current_version: str) -> dict:
    with db() as c:
        r = c.execute("SELECT * FROM agent_advice WHERE id=?", (aid,)).fetchone()
    if not r:
        raise HTTPException(404, "advice not found")
    return _advice_row(r, current_version)


def latest_advice(junction_id: str, current_version: str, weather: str | None = None, done_only: bool = True) -> dict | None:
    """The newest advice row for a junction (and weather what-if); fresh rows before stale ones."""
    with db() as c:
        rows = c.execute("SELECT * FROM agent_advice WHERE junction_id=? AND COALESCE(weather,'')=? ORDER BY created DESC",
                         (junction_id, weather or "")).fetchall()
    rows = [r for r in rows if r["status"] == "done"] if done_only else rows
    rows.sort(key=lambda r: (r["model_version"] != current_version, -r["created"]))
    return _advice_row(rows[0], current_version) if rows else None


def all_advice(current_version: str) -> list[dict]:
    with db() as c:
        ids = [r[0] for r in c.execute("SELECT DISTINCT junction_id FROM agent_advice ORDER BY junction_id")]
    return [a for a in (latest_advice(j, current_version, None, done_only=False) for j in ids) if a]
