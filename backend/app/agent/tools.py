"""Corridor tools for the planning assistant (Claude tool use). Owner: AI agent workstream.

Every tool goes through the same code as the HTTP API (backend/app/corridor.py), so each simulated option the agent
tries is a stored, fingerprinted run that the UI, the case workflow and reviewers can open (GET /runs/{run_id}).

    get_corridor        TomTom measured leg times (July average) and the slowest stretches        (measured)
    get_live_junctions  latest TomTom Junction Analytics readings per measured junction           (measured / estimated)
    run_corridor        simulate the corridor with interventions (optionally one hour of a July day and a rain what-if)
                        -> compact summary vs the no-change baseline under the same conditions   (simulated)
    compare_runs        side-by-side totals and the biggest per-leg / per-junction differences   (simulated)
    write_brief         one-page markdown decision brief with evidence fingerprints -> brief_id
    advise_junction     "flyover here, or what else?": the advisor loop (advisor.py) over the option set, ranked
"""
import hashlib, json, statistics, time, uuid
from dataclasses import dataclass, field

from fastapi import HTTPException

from .. import corridor as cor
from .. import weather as wx

LOW_COST = {"signal_retime", "one_way", "u_turn"}
COST_CLASS = {"signal_retime": "low (signal timing)", "one_way": "low (signage)", "u_turn": "low (road markings)",
              "widening": "medium (civil works)", "flyover": "high (construction)", "underpass": "high (construction)"}
MAX_RUNS = 6   # new simulations per conversation turn (cache hits and mock runs are free)
WEATHER = list(cor.WEATHER)   # rain what-if settings of POST /corridor/runs {weather}
RAIN_SUMMARY = ("hour by hour, July 2026 (TomTom one-hour trip times x Open-Meteo hourly rain, 558 slots): about +3% trip time in "
                "an hour with rain (+2.7%, 95% range +0.1 to +5.0%, about +1.6 min); once rain has lasted an hour about +4% in light "
                "rain (range +0.5 to +6.9%) and about +8% in the wettest July hours (+7.9%, range -3.9 to +16.1%, only 34 such hours). "
                "Rainy and dry hours of the same day did not differ, so part of it may be 'rainy days are slower days': confidence "
                "low to moderate (estimated). July had no cloudbursts in the data: nothing is known about downpours or waterlogging.")

TOOLS = [
    {"name": "get_corridor",
     "description": "The Lingampally -> Lakdikapul corridor (21 km, junctions j01..j11): every stretch (leg) between "
                    "corridor points with TomTom MEASURED travel time for a typical July 2026 day, the slowest stretches, "
                    "the spread across July days, and what rain does to the trip (estimated, hour by hour, with 95% "
                    "ranges, and the weather what-if settings run_corridor takes). Call this first to find where the trip loses time.",
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
                    "An empty interventions list runs the baseline. At most one intervention of each kind per junction. "
                    "Optional conditions (the summary compares with the no-change run under the same conditions): "
                    "hour 6-22 = that one-hour slot (hh:00-hh+1:00) of a typical July day, or of `day` (a July 2026 date); "
                    "weather = rain what-if: 'dry', 'light_rain' (0.1-1 mm/h for an hour or more) or 'heavy_rain' (the "
                    "wettest July hours, 1-5 mm/h for an hour or more; not a cloudburst). Leave weather out for the calibrated "
                    "run, which already includes July's rain as it fell. The weather only changes road speeds (estimated "
                    "factors per stretch); demand and signals stay. The result's `weather` field gives the expected trip "
                    "effect vs dry with its 95% range: cite it with the simulated minutes.",
     "input_schema": {"type": "object", "properties": {
         "interventions": {"type": "array", "items": {"type": "object", "properties": {
             "junction_id": {"type": "string", "description": "j01..j11"},
             "kind": {"type": "string", "enum": ["flyover", "underpass", "signal_retime", "widening", "one_way", "u_turn"]},
             "params": {"type": "object"}}, "required": ["junction_id", "kind"]}},
         "volume_scale": {"type": "number", "description": "traffic volume multiplier, 1.0 = today's calibrated "
                                                            "demand; 0.8 / 1.2 for sensitivity tests (0.1-3)"},
         "hour": {"type": "integer", "minimum": 6, "maximum": 22,
                  "description": "one-hour slot hh:00-hh+1:00 of a typical July day (or of `day`); leave out for the all-day average"},
         "day": {"type": "string", "description": "with hour: 'july' (typical July day, default) or a date 2026-07-01..2026-07-31"},
         "weather": {"type": "string", "enum": WEATHER,
                     "description": "rain what-if; leave out for the calibrated weather (July's rain as it fell)"}},
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
    {"name": "advise_junction",
     "description": "Answer 'can we build a flyover at this junction, and if not, what else would help?' for one junction. "
                    "Gathers the measured data (TomTom leg times, live delay, rain sensitivity), then simulates the option set "
                    "cheapest-first against the baseline under identical conditions: signal_retime (corridor green share 0.7 and "
                    "0.5), one_way, widening (+1 lane), underpass, flyover (2 lanes), and re-tests the two best in heavy rain and at "
                    "1.1x traffic. Returns a ranked options table (trip change, noise, ripple at neighbours, rain and 1.1x "
                    "checks, cost class), a verdict, reasons, caveats and a decision brief id. Pre-computed advice (same "
                    "simulation version) comes back instantly; otherwise up to ~12 simulations run (several minutes). "
                    "Junctions already crossed on a flyover (j03, j04, j06, j07, j10, j11) get the alternative instead. "
                    "Use this for 'what should we do at X' / 'flyover at X?' questions; use run_corridor for one-off tests.",
     "input_schema": {"type": "object", "properties": {
         "junction_id": {"type": "string", "description": "j01..j11 (Nallagandla j01, ISB Rd/DLF j02, Gachibowli j03, Biodiversity j04, "
                                                          "Khajaguda j05, Shaikpet j06, Tolichowki j07, Nanal Nagar j08, Rethibowli j09, "
                                                          "NMDC j10, Masab Tank j11)"},
         "weather": {"type": "string", "enum": WEATHER, "description": "run the whole option set under this rain what-if (optional)"},
         "fresh": {"type": "boolean", "description": "true: recompute even when pre-computed advice exists (slow)"}},
         "required": ["junction_id"]}},
]


@dataclass
class Context:
    """Per-turn state: run budget, runs made, steps for the UI, baseline memo."""
    session_id: str = ""
    max_runs: int = MAX_RUNS
    runs_used: int = 0
    run_ids: list = field(default_factory=list)
    brief_id: str | None = None
    baselines: dict = field(default_factory=dict)   # (volume_scale, hour, day, weather) -> baseline result


# ---------- helpers shared with the case workflow ----------
def points() -> dict:
    return {p["id"]: p["name"] for p in cor.corridor_def()["points"]}


def ivs(res: dict) -> list[dict]:
    """The interventions a run was asked for (a MOCK_SIM sample may carry the sample's own interventions)."""
    if res.get("sample") and "requested" in res:
        return res["requested"]["interventions"]
    return res.get("interventions", [])


def vol(res: dict) -> float:
    """The traffic volume a run was asked for (a MOCK_SIM sample keeps the sample's own 1.0 in inputs)."""
    if res.get("sample") and "requested" in res:
        return res["requested"].get("volume_scale", 1.0)
    return res.get("inputs", {}).get("volume_scale", 1.0)


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


def conds(res: dict) -> dict:
    """The conditions a run was simulated under, only those set: {hour, day ('july' or a date), weather}."""
    t, rq = res.get("time") or {}, res.get("requested") or {}
    hour = t.get("hour", rq.get("hour"))
    weather = t.get("weather") or rq.get("weather") or ((res.get("inputs") or {}).get("weather") or {}).get("weather")
    out = {}
    if hour is not None:
        out["hour"], out["day"] = int(hour), (t.get("day") or rq.get("day") or "july")
    if weather:
        out["weather"] = weather
    return out


def cond_key(volume_scale: float, hour=None, day=None, weather=None) -> tuple:
    """Runs with the same key can be compared: same traffic volume, hour (and day) and weather."""
    return (round(volume_scale, 3), hour, ((day or "july").lower() if hour is not None else None), weather or None)


def run_key(res: dict) -> tuple:
    c = conds(res)
    return cond_key(vol(res), c.get("hour"), c.get("day"), c.get("weather"))


def cond_text(c: dict) -> str:
    """'typical July day 18:00-19:00, heavy rain (what-if)'; '' for the all-day average in the calibrated weather."""
    bits = []
    if c.get("hour") is not None:
        h, d = c["hour"], c.get("day") or "july"
        bits.append(f"{'typical July day' if d == 'july' else d} {h:02d}:00-{h + 1:02d}:00")
    if c.get("weather"):
        bits.append(f"{c['weather'].replace('_', ' ')} (what-if)")
    return ", ".join(bits)


def option(res: dict) -> str:
    """The option in words with its conditions: 'flyover at j08 ... [heavy rain (what-if)]'."""
    c = cond_text(conds(res))
    return label(ivs(res)) + (f" [{c}]" if c else "")


def weather_info(res: dict) -> dict | None:
    """A weather what-if run's setting and the estimated trip effect vs dry with its 95% range (from the result, else
    data/rain/rain_factors.json). None for a run in the calibrated weather."""
    w = conds(res).get("weather")
    if not w:
        return None
    iw = (res.get("inputs") or {}).get("weather") or {}
    f, ci, meaning = iw.get("expected_trip_time_factor_vs_dry"), iw.get("expected_trip_time_factor_vs_dry_ci95"), iw.get("meaning")
    if f is None:     # mock mode (not applied) or an older runner: the factors file
        try:
            st = wx.factors()["what_if"]["settings"][w]
            f, ci, meaning = st.get("trip_travel_time_factor"), st.get("trip_travel_time_factor_ci95"), meaning or st.get("meaning")
        except Exception:
            pass
    pct = lambda x: None if x is None else round((x - 1) * 100, 1)   # noqa: E731
    out = {"setting": w, "meaning": meaning, "expected_trip_time_vs_dry_pct": pct(f),
           "expected_trip_time_vs_dry_ci95_pct": [pct(x) for x in ci] if ci else None,
           "label": "estimated (TomTom hourly x Open-Meteo rain, July 2026)", "confidence": "low to moderate",
           "applies": "road speed caps per stretch only; demand and signals unchanged (assumed)"}
    if iw.get("note"):
        out["note"] = iw["note"]
    return out


def load_run(run_id: str) -> dict:
    res = cor.stored_run(run_id)
    if res is None or "corridor_id" not in res:
        raise HTTPException(404, f"corridor run {run_id!r} not found")
    return res


def baseline_for(volume_scale: float, ctx: Context | None = None, hour: int | None = None, day: str | None = None,
                 weather: str | None = None) -> dict:
    """The no-change run at this volume, hour (and day) and weather (cached in real mode; memoised per turn)."""
    key = cond_key(volume_scale, hour, day, weather)
    if ctx is not None and key in ctx.baselines:
        return ctx.baselines[key]
    body = cor.CorridorRunIn(volume_scale=volume_scale, run_by="agent", hour=hour, day=day if hour is not None else None,
                             weather=weather or None)
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
    out = {"run_id": res["run_id"], "fingerprint": res.get("fingerprint"), "option": option(res),
           "interventions": ivs(res), "volume_scale": vol(res),
           "conditions": cond_text(conds(res)) or "typical July day (06-23 average), calibrated weather (July's rain as it fell)",
           "total_min": mins(res["journey"]["total_s"]), "data": "SIMULATED (SUMO)",
           "time_window": res.get("time", {}).get("label"), "warnings": res.get("warnings", []),
           "inputs": res.get("inputs", {})}
    if res["journey"].get("tomtom_total_s") and not res.get("sample"):
        out["tomtom_measured_total_min"] = mins(res["journey"]["tomtom_total_s"])
    if weather_info(res):
        out["weather"] = weather_info(res)
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
    out["rain"] = {"summary": RAIN_SUMMARY, "label": "estimated", "confidence": "low to moderate",
                   "how_to_simulate": "run_corridor with the same interventions (and hour) once with weather='dry' and once "
                                      "with weather='heavy_rain' (or 'light_rain'), then compare_runs"}
    try:
        f = wx.weather_factors()
        h, names = f["headline"], points()
        leg_name = lambda k: " -> ".join(names.get(x, x) for x in str(k).split("-", 1))   # noqa: E731
        out["rain"].update({
            "any_rain_in_the_hour_pct": h["any_rain"]["pct"], "any_rain_ci95_pct": h["any_rain"]["ci95_pct"],
            "rain_lasting_an_hour_pct": {k: {"pct": v["pct"], "ci95_pct": v["ci95_pct"]} for k, v in (h.get("sustained") or {}).items()},
            "same_day_check_pct": (h.get("within_day_check") or {}).get("light"),
            "most_affected_stretches": [leg_name(l["leg"]) for l in f.get("per_leg", [])
                                        if ((l.get("sustained") or {}).get("light") or {}).get("ci95_pct", [0])[0] > 0],
            "what_if_settings": {k: {"meaning": v.get("meaning"), "trip_time_pct_vs_dry": v.get("trip_time_pct"),
                                     "ci95_pct": v.get("trip_time_pct_ci95")} for k, v in (f.get("what_if") or {}).items()},
        })
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
    hour = inp.get("hour")
    day = (inp.get("day") or None) if hour is not None else None
    weather = inp.get("weather") or None
    body = cor.CorridorRunIn(interventions=inp.get("interventions") or [], volume_scale=inp.get("volume_scale") or 1.0,
                             run_by="agent", hour=hour, day=day, weather=weather)
    if not cor.is_cached(body):   # validates too (400 for a bad request, 422 for an hour without hourly data)
        if ctx.runs_used >= ctx.max_runs:
            return {"error": f"Run budget reached: {ctx.max_runs} new simulations this turn. Summarise what you have "
                             "and ask the user before running more."}
        ctx.runs_used += 1
    res = cor.run_blocking(body)
    base = res if not ivs(res) else baseline_for(body.volume_scale, ctx, hour=body.hour, day=body.day, weather=body.weather)
    if not ivs(res):
        ctx.baselines[cond_key(body.volume_scale, body.hour, body.day, body.weather)] = res
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
        row = {"run_id": r["run_id"], "option": option(r), "conditions": cond_text(conds(r)) or "calibrated weather, all-day",
               "volume_scale": vol(r), "total_min": mins(r["journey"]["total_s"]),
               "change_vs_reference_min": round((r["journey"]["total_s"] - ref["journey"]["total_s"]) / 60, 1),
               "warnings": len(r.get("warnings", []))}
        if weather_info(r):
            row["weather"] = weather_info(r)
        if r is not ref:
            d = diff(r, ref)
            row["biggest_leg_changes"] = d["legs"][:3]
            row["biggest_junction_changes"] = d["junctions"][:3]
        rows.append(row)
    vols = {vol(r) for r in runs}
    others = {cond_text(conds(r)) or "calibrated weather, all-day" for r in runs}
    caution = []
    if len(vols) > 1:
        caution.append(f"runs use different volume scales {sorted(vols)}; compare like with like")
    if len(others) > 1:
        caution.append(f"runs differ in hour or weather ({'; '.join(sorted(others))}): differences include that effect, "
                       "not only the interventions'")
    return {"reference": ref["run_id"], "data": "SIMULATED", "rows": rows, **({"caution": "; ".join(caution)} if caution else {})}


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
    brief = store.save_brief(ctx.session_id, md, list(fps), fps, inp.get("recommendation", ""))
    ctx.brief_id = brief["brief_id"]
    return {"brief_id": brief["brief_id"], "fingerprint": brief["fingerprint"], "runs": len(runs),
            "kinds_tested": sorted(kinds), "note": "stored; GET /briefs/" + brief["brief_id"]}


def render_brief(ctx: Context, inp: dict, runs: list[dict]) -> tuple[str, dict]:
    bases = {}   # (volume, hour, day, weather) -> the no-change run under the same conditions
    for r in runs:
        if not ivs(r):
            bases.setdefault(run_key(r), r)
    for k in {run_key(r) for r in runs} - set(bases):
        bases[k] = baseline_for(k[0], ctx, hour=k[1], day=k[2], weather=k[3])
    all_runs = list({r["run_id"]: r for r in list(bases.values()) + runs}.values())
    lines = [f"# Decision brief: {inp.get('title', 'corridor option')}", "",
             f"*Lingampally -> Lakdikapul corridor. Prepared by the CityRehearsal planning assistant on "
             f"{time.strftime('%d %b %Y %H:%M')}. This is a recommendation for human review, not a decision.*", "",
             "## Problem", "", inp.get("problem", "").strip(), "",
             "## Options tested", "",
             "| Option | Cost class | Volume | Trip (min, simulated) | Change vs no change (min) | Run |",
             "|---|---|---|---|---|---|"]
    order = lambda r: (lambda k: (k[0], -1 if k[1] is None else k[1], k[2] or "", k[3] or ""))(run_key(r))   # noqa: E731
    for r in sorted(all_runs, key=lambda r: (order(r), bool(ivs(r)), r["journey"]["total_s"])):
        vs = round(vol(r), 3)
        b = bases[run_key(r)]
        cost = ", ".join(sorted({COST_CLASS.get(iv["kind"], iv["kind"]) for iv in ivs(r)})) or "none"
        ch = "-" if r is b else f"{(r['journey']['total_s'] - b['journey']['total_s']) / 60:+.1f}"
        lines.append(f"| {option(r)} | {cost} | {vs} | {mins(r['journey']['total_s'])} | {ch} | `{r['run_id']}` |")
    tt = next((r["journey"].get("tomtom_total_s") for r in all_runs if r["journey"].get("tomtom_total_s") and not r.get("sample")), None)
    periods = cor.tomtom_periods()
    lines += ["", f"Measured reference: TomTom July 2026 typical day trip time {mins(periods[0]['total_s']) if periods else '?'} min"
                  + (f"; TomTom time for the simulated window {mins(tt)} min" if tt else "") + " (measured).", "",
              "## Ripple effects", ""]
    for r in runs:
        if not ivs(r):
            continue
        d = diff(r, bases[run_key(r)])
        target = {iv["junction_id"] for iv in ivs(r)}
        worse = [j for j in d["junctions"] if j["delay_s"][1] > j["delay_s"][0] and j["junction"].split()[0] not in target]
        slower = [l for l in d["legs"] if l["change_min"] > 0]
        txt = []
        if worse:
            txt.append("worse at " + "; ".join(f"{j['junction']} delay {j['delay_s'][0]}->{j['delay_s'][1]} s, "
                                               f"queue {j['queue_m'][0]}->{j['queue_m'][1]} m" for j in worse[:3]))
        if slower:
            txt.append("slower legs: " + "; ".join(f"{l['leg']} {l['change_min']:+} min" for l in slower[:3]))
        lines.append(f"- **{option(r)}** (volume {vol(r)}): "
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
    wet = sorted({conds(r)["weather"].replace("_", " ") for r in all_runs if conds(r).get("weather")})
    lines += ["- Rain: about +3% trip time in a rainy hour, 4-8% when rain persists (estimated from TomTom hourly trip times "
              "x Open-Meteo hourly rain, July 2026; low-moderate confidence: rainy and dry hours of the same day did not differ). "
              + (f"Weather what-ifs simulated here: {', '.join(wet)}; they change road speeds only (estimated factors per "
                 "stretch), demand and signals stay (assumed)." if wet else
                 "The runs above use the calibrated weather (July's rain as it fell); a rain what-if can be simulated "
                 "(weather dry / light rain / heavy rain)."),
              "- Volume sensitivity: reviewers should re-run the options at 0.8x and 1.2x volume before deciding.", "",
              "## Recommendation (for review)", "", inp.get("recommendation", "").strip(), ""]
    lines += [f"- {x}" for x in inp.get("reasons", [])]
    lines += ["", "The decision rests with the reviewing engineer and the approving authority.", "",
              "## Evidence", "", "| Run | SHA-256 fingerprint |", "|---|---|"]
    fps = {r["run_id"]: r.get("fingerprint") or cor.fingerprint(r) for r in all_runs}
    lines += [f"| `{k}` | `{v}` |" for k, v in fps.items()]
    return "\n".join(lines) + "\n", fps


def advise_junction(ctx: Context, inp: dict) -> dict:
    from . import advisor, store
    jid, weather = (inp.get("junction_id") or "").strip().lower(), inp.get("weather") or None
    if jid not in cor.junction_ids():
        return {"error": f"unknown junction {jid!r}; use one of {', '.join(cor.junction_ids())}"}
    ver = advisor.model_version()
    if not inp.get("fresh"):
        hit = store.latest_advice(jid, ver, weather)
        if hit and not hit["stale"] and hit["advice"]:
            ctx.run_ids += [r for r in hit["run_ids"] if r not in ctx.run_ids]
            if hit["brief_id"]:
                ctx.brief_id = hit["brief_id"]
            return advisor.compact(hit["advice"]) | {"precomputed": True, "advice_id": hit["advice_id"],
                                                     "computed_at": hit["finished"], "note": "pre-computed on this simulation version"}
    ctx.max_runs = max(ctx.max_runs, advisor.ADVISE_MAX_RUNS)
    aid = store.create_advice(jid, weather, ver)
    try:
        adv = advisor.advise(jid, advisor.LocalRunner(ctx), weather, session_id=ctx.session_id or "advisor")
    except Exception as e:
        store.finish_advice(aid, None, f"{type(e).__name__}: {e}")
        raise
    store.finish_advice(aid, adv)
    if adv.get("brief_id"):
        ctx.brief_id = adv["brief_id"]
    return advisor.compact(adv) | {"precomputed": False, "advice_id": aid, "runs_left_this_turn": ctx.max_runs - ctx.runs_used}


HANDLERS = {"get_corridor": get_corridor, "get_live_junctions": get_live_junctions, "run_corridor": run_corridor,
            "compare_runs": compare_runs, "write_brief": write_brief, "advise_junction": advise_junction}


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
    if name == "advise_junction":
        top = out["options"][0] if out.get("options") else None
        return (f"{out['junction']} {out.get('name', '')}: {out.get('verdict')}" + (f" (best: {top['kind']} {top['trip_change_min']:+} min)" if top else "")
                + (" [pre-computed]" if out.get("precomputed") else ""))[:200]
    return ""


def sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:8]
