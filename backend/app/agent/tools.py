"""Corridor tools for the planning assistant (Claude tool use). Owner: AI agent workstream.

Every tool goes through the same code as the HTTP API (backend/app/corridor.py), so each simulated option the agent
tries is a stored, fingerprinted run that the UI, the case workflow and reviewers can open (GET /runs/{run_id}).

    get_corridor        TomTom measured leg times (July average) and the slowest stretches        (measured)
    get_live_junctions  latest TomTom Junction Analytics readings per measured junction           (measured / estimated)
    run_corridor        simulate the corridor with interventions -> compact summary vs baseline  (simulated)
    compare_runs        side-by-side totals and the biggest per-leg / per-junction differences   (simulated)
    write_brief         one-page markdown decision brief with evidence fingerprints -> brief_id
"""
import hashlib, json, statistics, time, uuid
from dataclasses import dataclass, field

from fastapi import HTTPException

from .. import corridor as cor

LOW_COST = {"signal_retime", "one_way", "u_turn"}
COST_CLASS = {"signal_retime": "low (signal timing)", "one_way": "low (signage)", "u_turn": "low (road markings)",
              "widening": "medium (civil works)", "flyover": "high (construction)", "underpass": "high (construction)"}
MAX_RUNS = 6   # new simulations per conversation turn (cache hits and mock runs are free)

TOOLS = [
    {"name": "get_corridor",
     "description": "The Lingampally -> Lakdikapul corridor (21 km, junctions j01..j11): every stretch (leg) between "
                    "corridor points with TomTom MEASURED travel time for a typical July 2026 day, the slowest stretches, "
                    "the spread across July days, and the rain effect. Call this first to find where the trip loses time.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_live_junctions",
     "description": "Latest TomTom Junction Analytics readings for the corridor junctions that have a live feed: delay "
                    "now vs usual delay (measured), queue length and volume (estimated by TomTom), per approach road, "
                    "plus the mean of the last 60 minutes.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "run_corridor",
     "description": "Simulate the whole corridor trip with interventions built at junctions (SUMO, ~1-2 minutes per new "
                    "run; identical requests come back instantly from the cache). Returns total trip minutes, change vs "
                    "the no-change baseline at the same volume, per-leg changes over 0.5 min, junction delay/queue "
                    "changes (ripple), warnings, input labels, run_id and SHA-256 fingerprint. Kinds and params "
                    "(all params optional): signal_retime {cycle_s 40-240, corridor_green_share 0.1-0.9}; "
                    "widening {add_lanes 1-2, length_m}; one_way {road, direction in|out, length_m}; "
                    "flyover / underpass {lanes, speed_kmh, length_m}. u_turn is not built yet. "
                    "An empty interventions list runs the baseline. At most one intervention of each kind per junction.",
     "input_schema": {"type": "object", "properties": {
         "interventions": {"type": "array", "items": {"type": "object", "properties": {
             "junction_id": {"type": "string", "description": "j01..j11"},
             "kind": {"type": "string", "enum": ["flyover", "underpass", "signal_retime", "widening", "one_way", "u_turn"]},
             "params": {"type": "object"}}, "required": ["junction_id", "kind"]}},
         "volume_scale": {"type": "number", "description": "traffic volume multiplier, 1.0 = today's calibrated "
                                                            "demand; 0.8 / 1.2 for sensitivity tests (0.1-3)"}},
         "required": ["interventions"]}},
    {"name": "compare_runs",
     "description": "Compare runs already made (by run_id): total trip minutes, change vs the first run (or the "
                    "baseline if one is included) and the biggest per-leg and per-junction differences.",
     "input_schema": {"type": "object", "properties": {"run_ids": {"type": "array", "items": {"type": "string"}}},
                      "required": ["run_ids"]}},
    {"name": "write_brief",
     "description": "Write and store the one-page decision brief for human reviewers from runs already made. Needs at "
                    "least one low-cost option (signal_retime / one_way) among the runs. The brief states the problem, "
                    "options tested, results table, ripple effects, risks and assumptions with counted/estimated/"
                    "assumed labels, your recommendation (not a decision) and the evidence fingerprints.",
     "input_schema": {"type": "object", "properties": {
         "title": {"type": "string", "description": "short title, e.g. 'Tolichowki (j07) morning delay'"},
         "problem": {"type": "string", "description": "2-3 sentences: where and how much time is lost, with sources"},
         "run_ids": {"type": "array", "items": {"type": "string"}},
         "recommendation": {"type": "string", "description": "the option you recommend reviewers approve, and any condition"},
         "reasons": {"type": "array", "items": {"type": "string"}}},
         "required": ["title", "problem", "run_ids", "recommendation", "reasons"]}},
]


@dataclass
class Context:
    """Per-turn state: run budget, runs made, steps for the UI, baseline memo."""
    session_id: str = ""
    max_runs: int = MAX_RUNS
    runs_used: int = 0
    run_ids: list = field(default_factory=list)
    brief_id: str | None = None
    baselines: dict = field(default_factory=dict)   # volume_scale -> baseline result


# ---------- helpers shared with the case workflow ----------
def points() -> dict:
    return {p["id"]: p["name"] for p in cor.corridor_def()["points"]}


def ivs(res: dict) -> list[dict]:
    """The interventions a run was asked for (a MOCK_SIM sample may carry the sample's own interventions)."""
    if res.get("sample") and "requested" in res:
        return res["requested"]["interventions"]
    return res.get("interventions", [])


def label(interventions: list[dict]) -> str:
    if not interventions:
        return "baseline (no change)"
    names = points()
    parts = []
    for iv in interventions:
        p = ", ".join(f"{k}={v}" for k, v in (iv.get("params") or {}).items())
        parts.append(f"{iv['kind']} at {iv['junction_id']} {names.get(iv['junction_id'], '')}".strip() + (f" ({p})" if p else ""))
    return " + ".join(parts)


def mins(s) -> float | None:
    return None if s is None else round(s / 60, 1)


def load_run(run_id: str) -> dict:
    res = cor.stored_run(run_id)
    if res is None or "corridor_id" not in res:
        raise HTTPException(404, f"corridor run {run_id!r} not found")
    return res


def baseline_for(volume_scale: float, ctx: Context | None = None) -> dict:
    """The no-change run at this volume (cached in real mode; memoised per turn)."""
    key = round(volume_scale, 3)
    if ctx is not None and key in ctx.baselines:
        return ctx.baselines[key]
    body = cor.CorridorRunIn(volume_scale=volume_scale, run_by="agent")
    if ctx is not None and not cor.is_cached(body):
        if ctx.runs_used >= ctx.max_runs:
            raise HTTPException(429, "run budget for this turn is used up; the baseline is needed first")
        ctx.runs_used += 1
    res = cor.run_blocking(body)
    if ctx is not None:
        ctx.baselines[key] = res
    return res


def diff(res: dict, base: dict, leg_min: float = 0.5) -> dict:
    """Per-leg (> leg_min minutes) and per-junction (>= 3 s delay or >= 20 m queue) changes of res vs base."""
    bl = {(l["from_id"], l["to_id"]): l for l in base["journey"]["legs"]}
    legs = []
    for l in res["journey"]["legs"]:
        b = bl.get((l["from_id"], l["to_id"]))
        if b and abs(l["time_s"] - b["time_s"]) / 60 > leg_min:
            legs.append({"leg": f"{l['from_id']}->{l['to_id']} ({l.get('from_name', '')} -> {l.get('to_name', '')})",
                         "before_min": mins(b["time_s"]), "after_min": mins(l["time_s"]),
                         "change_min": round((l["time_s"] - b["time_s"]) / 60, 1)})
    bj = {j["id"]: j for j in base["junctions"]}
    juncs = []
    for j in res["junctions"]:
        b = bj.get(j["id"])
        if b and (abs(j["avg_delay_s"] - b["avg_delay_s"]) >= 3 or abs(j["max_queue_m"] - b["max_queue_m"]) >= 20):
            juncs.append({"junction": f"{j['id']} {j.get('name', '')}".strip(),
                          "delay_s": [b["avg_delay_s"], j["avg_delay_s"]], "queue_m": [b["max_queue_m"], j["max_queue_m"]]})
    legs.sort(key=lambda x: -abs(x["change_min"]))
    juncs.sort(key=lambda x: -abs(x["delay_s"][1] - x["delay_s"][0]))
    return {"legs": legs, "junctions": juncs}


def summarize(res: dict, base: dict | None) -> dict:
    out = {"run_id": res["run_id"], "fingerprint": res.get("fingerprint"), "option": label(ivs(res)),
           "interventions": ivs(res), "volume_scale": res["inputs"].get("volume_scale"),
           "total_min": mins(res["journey"]["total_s"]), "data": "SIMULATED (SUMO)",
           "time_window": res.get("time", {}).get("label"), "warnings": res.get("warnings", []),
           "inputs": res.get("inputs", {})}
    if res["journey"].get("tomtom_total_s") and not res.get("sample"):
        out["tomtom_measured_total_min"] = mins(res["journey"]["tomtom_total_s"])
    if res.get("sample"):
        out["mock"] = "MOCK_SIM=1: sample or illustrative numbers, not a real simulation; say so when you report them"
    if res.get("cached"):
        out["cached"] = True
    if base is not None and base["run_id"] != res["run_id"]:
        out["baseline_run_id"] = base["run_id"]
        out["baseline_total_min"] = mins(base["journey"]["total_s"])
        out["change_vs_baseline_min"] = round((res["journey"]["total_s"] - base["journey"]["total_s"]) / 60, 1)
        d = diff(res, base)
        out["legs_changed"] = d["legs"][:8]
        out["junctions_changed"] = d["junctions"][:8]
    else:
        slow = sorted(res["junctions"], key=lambda j: -j["avg_delay_s"])[:4]
        out["worst_junctions"] = [{"junction": f"{j['id']} {j.get('name', '')}", "delay_s": j["avg_delay_s"],
                                   "queue_m": j["max_queue_m"]} for j in slow]
    return out


# ---------- tools ----------
def get_corridor(ctx: Context, _: dict) -> dict:
    periods = cor.tomtom_periods()
    if not periods:
        return {"error": "TomTom leg times are missing (data/raw/corridor_legs_tomtom.csv)"}
    avg = periods[0]
    legs = [{"leg": f"{l['from_id']}->{l['to_id']}", "from": l["from_name"], "to": l["to_name"],
             "km": round(l["distance_m"] / 1000, 2), "min": mins(l["time_s"]), "speed_kmh": l["speed_kmh"],
             "min_per_km": round(l["time_s"] / 60 / (l["distance_m"] / 1000), 2)} for l in avg["legs"]]
    days = [p["total_s"] / 60 for p in periods if p["kind"] == "day"]
    out = {"source": avg["source"] + f", {avg['label']}", "data": "MEASURED (TomTom probe vehicles)",
           "trip_total_min": mins(avg["total_s"]), "distance_km": round(avg["distance_m"] / 1000, 1),
           "legs": legs,
           "slowest_by_minutes": [x["leg"] for x in sorted(legs, key=lambda x: -x["min"])[:4]],
           "slowest_by_min_per_km": [x["leg"] for x in sorted(legs, key=lambda x: -x["min_per_km"])[:4]],
           "note": "a leg's time includes the wait at the junction it ends at (e.g. j06->j07 includes Tolichowki)"}
    if days:
        out["daily_08_20_trip_min"] = {"days": len(days), "min": round(min(days), 1), "median": round(statistics.median(days), 1),
                                       "max": round(max(days), 1), "data": "MEASURED, one TomTom average per day 08-20"}
    try:
        rain = json.loads((cor.ROOT / "data/rain/rain_factors.json").read_text())
        out["rain"] = {"travel_time_factor_while_raining": rain["overall_travel_time_factor"],
                       "label": rain.get("label"), "confidence": rain.get("confidence")}
    except Exception:
        pass
    return out


def get_live_junctions(ctx: Context, _: dict) -> dict:
    try:
        live = cor.corridor_junctions_live(60)
    except HTTPException as e:
        return {"available": False, "message": e.detail}
    out = []
    for j in live["junctions"]:
        aps = sorted(j["approaches"], key=lambda a: -(a.get("delay_s") or 0))[:4]
        out.append({"junction": f"{j['id']} {j['name']}", "time": j["time"],
                    "age_min": round(j["age_s"] / 60) if j.get("age_s") is not None else None,
                    "approaches": [{"road": a["name"], "delay_s": a.get("delay_s"), "usual_delay_s": a.get("usual_delay_s"),
                                    "queue_m": a.get("queue_m"), "volume_per_hour": a.get("volume_per_hour"),
                                    "last_60min_delay_s": a.get("last_60min", {}).get("delay_s")} for a in aps],
                    **({"note": j["note"]} if j.get("note") else {})})
    return {"source": live["source"], "labels": live["labels"], "junctions": out}


def run_corridor(ctx: Context, inp: dict) -> dict:
    body = cor.CorridorRunIn(interventions=inp.get("interventions") or [], volume_scale=inp.get("volume_scale") or 1.0,
                             run_by="agent")
    if not cor.is_cached(body):   # validates too (400 for a bad request)
        if ctx.runs_used >= ctx.max_runs:
            return {"error": f"Run budget reached: {ctx.max_runs} new simulations this turn. Summarise what you have "
                             "and ask the user before running more."}
        ctx.runs_used += 1
    res = cor.run_blocking(body)
    base = res if not ivs(res) else baseline_for(body.volume_scale, ctx)
    if not ivs(res):
        ctx.baselines[round(body.volume_scale, 3)] = res
    ctx.run_ids.append(res["run_id"])
    out = summarize(res, base)
    out["runs_left_this_turn"] = ctx.max_runs - ctx.runs_used
    return out


def compare_runs(ctx: Context, inp: dict) -> dict:
    runs = [load_run(r) for r in inp.get("run_ids", [])]
    if len(runs) < 2:
        return {"error": "give at least two run_ids"}
    ref = next((r for r in runs if not ivs(r)), runs[0])
    rows = []
    for r in runs:
        row = {"run_id": r["run_id"], "option": label(ivs(r)),
               "volume_scale": r["inputs"].get("volume_scale"), "total_min": mins(r["journey"]["total_s"]),
               "change_vs_reference_min": round((r["journey"]["total_s"] - ref["journey"]["total_s"]) / 60, 1),
               "warnings": len(r.get("warnings", []))}
        if r is not ref:
            d = diff(r, ref)
            row["biggest_leg_changes"] = d["legs"][:3]
            row["biggest_junction_changes"] = d["junctions"][:3]
        rows.append(row)
    vols = {r["inputs"].get("volume_scale") for r in runs}
    return {"reference": ref["run_id"], "data": "SIMULATED", "rows": rows,
            **({"caution": f"runs use different volume scales {sorted(vols)}; compare like with like"} if len(vols) > 1 else {})}


def write_brief(ctx: Context, inp: dict) -> dict:
    from . import store
    runs = [load_run(r) for r in dict.fromkeys(inp.get("run_ids", []))]
    options = [r for r in runs if ivs(r)]
    if not options:
        return {"error": "the brief needs at least one option run (with interventions)"}
    kinds = {iv["kind"] for r in options for iv in ivs(r)}
    if not any(all(iv["kind"] in LOW_COST for iv in ivs(r)) for r in options):
        return {"error": "No low-cost option among these runs. Test at least one low-cost option (signal_retime or "
                         "one_way) at the same junction before writing a brief that includes construction."}
    md, fps = render_brief(ctx, inp, runs)
    brief = store.save_brief(ctx.session_id, md, [r["run_id"] for r in runs], fps, inp.get("recommendation", ""))
    ctx.brief_id = brief["brief_id"]
    return {"brief_id": brief["brief_id"], "fingerprint": brief["fingerprint"], "runs": len(runs),
            "kinds_tested": sorted(kinds), "note": "stored; GET /briefs/" + brief["brief_id"]}


def render_brief(ctx: Context, inp: dict, runs: list[dict]) -> tuple[str, dict]:
    bases = {}
    for r in runs:
        if not ivs(r):
            bases.setdefault(round(r["inputs"].get("volume_scale", 1.0), 3), r)
    for vs in {round(r["inputs"].get("volume_scale", 1.0), 3) for r in runs} - set(bases):
        bases[vs] = baseline_for(vs, ctx)
    all_runs = list({r["run_id"]: r for r in list(bases.values()) + runs}.values())
    lines = [f"# Decision brief: {inp.get('title', 'corridor option')}", "",
             f"*Lingampally -> Lakdikapul corridor. Prepared by the CityRehearsal planning assistant on "
             f"{time.strftime('%d %b %Y %H:%M')}. This is a recommendation for human review, not a decision.*", "",
             "## Problem", "", inp.get("problem", "").strip(), "",
             "## Options tested", "",
             "| Option | Cost class | Volume | Trip (min, simulated) | Change vs no change (min) | Run |",
             "|---|---|---|---|---|---|"]
    for r in sorted(all_runs, key=lambda r: (r["inputs"].get("volume_scale", 1), bool(ivs(r)), r["journey"]["total_s"])):
        vs = round(r["inputs"].get("volume_scale", 1.0), 3)
        b = bases[vs]
        cost = ", ".join(sorted({COST_CLASS.get(iv["kind"], iv["kind"]) for iv in ivs(r)})) or "none"
        ch = "-" if r is b else f"{(r['journey']['total_s'] - b['journey']['total_s']) / 60:+.1f}"
        lines.append(f"| {label(ivs(r))} | {cost} | {vs} | {mins(r['journey']['total_s'])} | {ch} | `{r['run_id']}` |")
    tt = next((r["journey"].get("tomtom_total_s") for r in all_runs if r["journey"].get("tomtom_total_s") and not r.get("sample")), None)
    periods = cor.tomtom_periods()
    lines += ["", f"Measured reference: TomTom July 2026 typical day trip time {mins(periods[0]['total_s']) if periods else '?'} min"
                  + (f"; TomTom time for the simulated window {mins(tt)} min" if tt else "") + " (measured).", "",
              "## Ripple effects", ""]
    for r in runs:
        if not ivs(r):
            continue
        d = diff(r, bases[round(r["inputs"].get("volume_scale", 1.0), 3)])
        target = {iv["junction_id"] for iv in ivs(r)}
        worse = [j for j in d["junctions"] if j["delay_s"][1] > j["delay_s"][0] and j["junction"].split()[0] not in target]
        slower = [l for l in d["legs"] if l["change_min"] > 0]
        txt = []
        if worse:
            txt.append("worse at " + "; ".join(f"{j['junction']} delay {j['delay_s'][0]}->{j['delay_s'][1]} s, "
                                               f"queue {j['queue_m'][0]}->{j['queue_m'][1]} m" for j in worse[:3]))
        if slower:
            txt.append("slower legs: " + "; ".join(f"{l['leg']} {l['change_min']:+} min" for l in slower[:3]))
        lines.append(f"- **{label(ivs(r))}** (volume {r['inputs'].get('volume_scale')}): "
                     + (". ".join(txt) if txt else "no nearby junction or leg got noticeably worse") + ".")
    lines += ["", "## Risks and assumptions", "",
              "- All trip and junction times for options are **simulated** (SUMO traffic model); only TomTom figures are measured.",
              "- Input labels: " + "; ".join(sorted({f"{r['inputs'].get('counts_source', '?')} ({r['inputs'].get('label', 'unlabelled')})"
                                                     for r in all_runs})) + "."]
    if any(r.get("sample") for r in all_runs):
        lines.append("- **Mock mode (MOCK_SIM=1): these numbers are sample or illustrative data, not simulations. "
                     "Re-run with MOCK_SIM=0 before any decision.**")
    warns = list(dict.fromkeys(w for r in all_runs for w in r.get("warnings", []) if "MOCK_SIM" not in w))
    lines += [f"- Simulation warning: {w}" for w in warns[:8]]
    lines += ["- Rain: about +5% travel time while raining (estimated from 15 July days, low confidence); not simulated here.",
              "- Volume sensitivity: reviewers should re-run the options at 0.8x and 1.2x volume before deciding.", "",
              "## Recommendation (for review)", "", inp.get("recommendation", "").strip(), ""]
    lines += [f"- {x}" for x in inp.get("reasons", [])]
    lines += ["", "The decision rests with the reviewing engineer and the approving authority.", "",
              "## Evidence", "", "| Run | SHA-256 fingerprint |", "|---|---|"]
    fps = {r["run_id"]: r.get("fingerprint") or cor.fingerprint(r) for r in all_runs}
    lines += [f"| `{k}` | `{v}` |" for k, v in fps.items()]
    return "\n".join(lines) + "\n", fps


HANDLERS = {"get_corridor": get_corridor, "get_live_junctions": get_live_junctions, "run_corridor": run_corridor,
            "compare_runs": compare_runs, "write_brief": write_brief}


def execute(ctx: Context, name: str, inp: dict) -> tuple[dict, bool]:
    """Run one tool -> (result, is_error). Request errors come back to the model as plain text, never crash the turn."""
    fn = HANDLERS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}, True
    try:
        out = fn(ctx, inp or {})
        return out, "error" in out
    except HTTPException as e:
        return {"error": str(e.detail), "status": e.status_code}, True
    except Exception as e:  # never let a tool crash the conversation
        return {"error": f"{type(e).__name__}: {e}"}, True


def one_line(name: str, inp: dict, out: dict) -> str:
    """Short human summary of a tool call for the UI's step list."""
    if "error" in out:
        return f"error: {out['error']}"[:200]
    if name == "get_corridor":
        return f"TomTom July average trip {out['trip_total_min']} min; slowest: {', '.join(out['slowest_by_minutes'][:3])}"
    if name == "get_live_junctions":
        if not out.get("available", True):
            return "no live junction data"
        return f"live data for {len(out['junctions'])} junctions"
    if name == "run_corridor":
        ch = out.get("change_vs_baseline_min")
        s = f"{out['option']} @ {out['volume_scale']}x: {out['total_min']} min"
        return s + (f" ({ch:+} min vs baseline)" if ch is not None else "") + (" [mock]" if out.get("mock") else "")
    if name == "compare_runs":
        return "; ".join(f"{r['option']}: {r['total_min']} min" for r in out["rows"])[:200]
    if name == "write_brief":
        return f"brief {out['brief_id']} written"
    return ""


def sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:8]
