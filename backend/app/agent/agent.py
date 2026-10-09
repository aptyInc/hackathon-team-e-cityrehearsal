"""Planning assistant: a Claude tool-use loop over the corridor tools (tools.py). Owner: AI agent workstream.

    run_turn(session_id, message)  one user message -> tool calls -> markdown reply; history kept per session in SQLite

Model: env CR_AGENT_MODEL (default claude-sonnet-5-5; claude-opus-5-5 also works). Effort: CR_AGENT_EFFORT (default
medium). Every request uses prompt caching (tools + system prompt + history prefix) and, on models that support it,
server-side refusal fallbacks (CR_AGENT_FALLBACK=0 turns that off). Missing ANTHROPIC_API_KEY or any Claude API failure
raises AgentUnavailable (the API answers 503 with a plain message). Tests swap the client with set_client_factory().
"""
import json, os, threading, time
from pathlib import Path

from . import store
from .tools import TOOLS, Context, execute, one_line

MODEL = os.getenv("CR_AGENT_MODEL", "claude-sonnet-5-5")
EFFORT = os.getenv("CR_AGENT_EFFORT", "medium")
MAX_CALLS = int(os.getenv("CR_AGENT_MAX_CALLS", "16"))      # Claude requests per turn
MAX_RUNS = int(os.getenv("CR_AGENT_MAX_RUNS", "6"))         # new simulations per turn
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
_fallback = os.getenv("CR_AGENT_FALLBACK", "1") == "1"
PRICES = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}   # $ per million tokens in / out
SYSTEM = (Path(__file__).with_name("prompt.md")).read_text()

_client_factory = None
_session_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class AgentUnavailable(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.message, self.status = message, status


def set_client_factory(fn):
    """Tests: fn() returns an object with .beta.messages.create(**kwargs) like anthropic.Anthropic."""
    global _client_factory
    _client_factory = fn


def client():
    if _client_factory:
        return _client_factory()
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise AgentUnavailable("The planning assistant is not set up: ANTHROPIC_API_KEY is missing from .env. "
                               "Everything else in CityRehearsal still works.")
    try:
        import anthropic, certifi
    except ImportError:
        raise AgentUnavailable("The planning assistant needs the `anthropic` package: run `make setup`.")
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())   # some Macs lack a CA bundle for Python
    return anthropic.Anthropic(api_key=key, max_retries=2, timeout=300)


def session_lock(session_id: str) -> threading.Lock:
    with _locks_guard:
        return _session_locks.setdefault(session_id, threading.Lock())


def _block(b) -> dict:
    """Content block -> dict, unchanged (thinking and fallback blocks must go back to the API exactly as received)."""
    if isinstance(b, dict):
        return b
    return b.to_dict() if hasattr(b, "to_dict") else b.model_dump(exclude_none=True)


def _create(c, messages: list[dict], last: bool):
    global _fallback
    kwargs = dict(model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
                  cache_control={"type": "ephemeral"}, output_config={"effort": EFFORT})
    if last:   # out of steps: answer with what is known
        kwargs["tool_choice"] = {"type": "none"}
    if _fallback and MODEL in FALLBACK_MODELS:
        kwargs |= {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    try:
        return c.beta.messages.create(**kwargs)
    except Exception as e:
        if kwargs.get("fallbacks") and getattr(e, "status_code", None) == 400 and "fallback" in str(e).lower():
            _fallback = False   # account or model without the beta: carry on without it
            for k in ("betas", "fallbacks"):
                kwargs.pop(k)
            return c.beta.messages.create(**kwargs)
        raise


def _api_error(e: Exception) -> AgentUnavailable:
    status = getattr(e, "status_code", None)
    name = type(e).__name__
    if status == 401:
        return AgentUnavailable("The Claude API key in .env was rejected (401). Check ANTHROPIC_API_KEY.")
    if status == 429:
        return AgentUnavailable("The Claude API is rate-limiting us right now (429). Try again in a minute.")
    if status is None and "Connection" in name:
        return AgentUnavailable(f"Cannot reach the Claude API ({e}). Check the network; on macOS set "
                                "SSL_CERT_FILE=$(python -m certifi).")
    return AgentUnavailable(f"The Claude API returned an error ({name}{' ' + str(status) if status else ''}): {str(e)[:300]}")


def _add_usage(total: dict, u):
    for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        total[k] = total.get(k, 0) + (getattr(u, k, 0) or 0)


def cost_usd(u: dict, model: str = MODEL) -> float:
    pin, pout = PRICES.get(model, (4.0, 20.0))
    return round((u.get("input_tokens", 0) * pin + u.get("cache_creation_input_tokens", 0) * pin * 1.25
                  + u.get("cache_read_input_tokens", 0) * pin * 0.1 + u.get("output_tokens", 0) * pout) / 1e6, 4)


def run_turn(session_id: str, message: str, turn_id: str) -> dict:
    """One conversation turn. Progress (steps, run_ids) is written to the turn row after every tool call so
    GET /agent/turns/{id} can show it. Only a completed turn is added to the session history."""
    lock = session_lock(session_id)
    if not lock.acquire(blocking=False):
        raise AgentUnavailable("This conversation is still working on the previous message.", 409)
    try:
        return _run_turn(session_id, message, turn_id)
    except AgentUnavailable as e:
        store.update_turn(turn_id, status="failed", error=e.message, http_status=e.status, finished=time.time())
        raise
    except Exception as e:
        err = _api_error(e) if "anthropic" in type(e).__module__ else AgentUnavailable(f"The assistant failed: {type(e).__name__}: {e}", 500)
        store.update_turn(turn_id, status="failed", error=err.message, http_status=err.status, finished=time.time())
        raise err
    finally:
        lock.release()


def _run_turn(session_id: str, message: str, turn_id: str) -> dict:
    c = client()
    ctx = Context(session_id=session_id, max_runs=MAX_RUNS)
    new = [{"role": "user", "content": message}]
    messages = store.history(session_id) + new
    steps, usage, reply, keep = [], {}, "", True
    for call in range(MAX_CALLS):
        resp = _create(c, messages, last=call == MAX_CALLS - 1)
        _add_usage(usage, getattr(resp, "usage", None))
        if resp.stop_reason == "refusal":
            reply = ("I can't help with that request. I can help find where the corridor loses time and test road "
                     "changes on the simulation.")
            keep = False   # a declined turn stays out of the history
            break
        content = [_block(b) for b in resp.content]
        assistant = {"role": "assistant", "content": content}
        messages.append(assistant)
        new.append(assistant)
        texts = [b["text"] for b in content if b.get("type") == "text"]
        if resp.stop_reason == "pause_turn":
            continue
        if resp.stop_reason != "tool_use":
            reply = "\n\n".join(texts).strip()
            if resp.stop_reason == "max_tokens":
                reply += "\n\n*(reply cut short)*"
            break
        results = []
        for b in content:
            if b.get("type") != "tool_use":
                continue
            out, is_err = execute(ctx, b["name"], b.get("input") or {})
            step = {"tool": b["name"], "input": b.get("input") or {}, "summary": one_line(b["name"], b.get("input") or {}, out)}
            if b["name"] == "run_corridor" and "run_id" in out:
                step["run_id"] = out["run_id"]
            if b["name"] in ("write_brief", "advise_junction") and out.get("brief_id"):
                step["brief_id"] = out["brief_id"]
            if b["name"] == "advise_junction" and "verdict" in out:
                step["advice"] = {"junction": out["junction"], "verdict": out["verdict"], "verdict_code": out.get("verdict_code"),
                                  "advice_id": out.get("advice_id"), "precomputed": out.get("precomputed")}
            steps.append(step)
            results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(out, default=str),
                            **({"is_error": True} if is_err else {})})
            store.update_turn(turn_id, steps=steps, run_ids=ctx.run_ids, brief_id=ctx.brief_id)
        tool_msg = {"role": "user", "content": results}
        messages.append(tool_msg)
        new.append(tool_msg)
    else:
        reply = "I stopped after the maximum number of steps for one message. Ask me to continue."
        keep = False
    if keep:
        store.append_messages(session_id, turn_id, new)
    usage["cost_usd"] = cost_usd(usage)
    usage["model"] = MODEL
    store.update_turn(turn_id, status="done", reply=reply, steps=steps, run_ids=ctx.run_ids, brief_id=ctx.brief_id,
                      usage=usage, finished=time.time())
    return {"session_id": session_id, "turn_id": turn_id, "reply": reply, "steps": steps, "run_ids": ctx.run_ids,
            "brief_id": ctx.brief_id, "usage": usage}
