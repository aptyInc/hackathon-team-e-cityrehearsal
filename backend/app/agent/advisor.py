"""Junction advisor: "can we build a flyover here, and if not, what else?" Owner: AI agent workstream.

    advise(junction_id, runner, weather=None)  -> advice dict (see ADVICE_SHAPE below) + decision brief
    latest(junction_id) / latest_all()         -> stored advice (SQLite `agent_advice`, append-only; stale when the
                                                  simulation code or calibration changed since it was computed)

The option set is run cheapest-first against the no-change baseline under identical conditions, then the two best
options are re-tested in heavy rain and at 1.1x traffic. Ranking: minutes saved beyond the simulation's comparison
noise, ripple at neighbouring junctions, robustness (rain, 1.1x) and an ASSUMED cost ladder
(signal retime << one-way < widening < underpass ~ flyover). The advisor recommends; people decide.

Runs go through `runner.run(...)`: in-process (`LocalRunner`, the chat tool: same cache, mock and run budget as
run_corridor) or over HTTP to a running API (`HttpRunner`, the pre-computation CLI advise_all.py, so one SUMO queue
serves everyone and nothing runs twice).
"""
import json, os, time

from .. import corridor as cor
from .. import weather as wx
from . import tools as T

NOISE_SINGLE_MIN = 0.5      # a one-junction change is beyond seed noise above about +-0.5 min (sim/corridor SIGMA_NOTE)
NOISE_CORRIDOR_MIN = 1.5    # a change to every leg (rain) above about +-1.5 min
ROBUST_VOLUME = 1.1         # reviewer re-test level (1.2 overloads the corridor model)
ADVISE_MAX_RUNS = int(os.getenv("CR_AGENT_ADVISE_RUNS", "14"))   # baseline + 6 options + 2 checks x (2 options + baseline)
COST_RANK = {"signal_retime": 1, "one_way": 2, "widening": 3, "underpass": 4, "flyover": 4}
COST_CLASS = {"signal_retime": "low: signal timing (assumed)", "one_way": "low: signage and markings (assumed)",
              "widening": "medium: civil works (assumed)", "underpass": "high: construction (assumed)",
              "flyover": "high: construction (assumed)"}
COST_LADDER = "assumed: signal retime << one-way < widening < underpass ~ flyover (no cost estimates were made)"
# junctions the corridor already crosses on a flyover (from the network: sim/templates/corridor.py existing_flyover)
ELEVATED = {"j03": "Gachibowli flyover", "j04": "Biodiversity flyover", "j06": "Shaikpet flyover",
            "j07": "Tolichowki flyover", "j10": "Masab Tank flyover", "j11": "Masab Tank flyover"}
GROUND = ["j01", "j02", "j05", "j08", "j09"]
LONG_STRUCTURE = {"j08": 1200}   # Nanal Nagar: the junction group needs a 1200 m structure (600 m elsewhere)
VERDICTS = {"build": "build the flyover", "build_underpass": "build the underpass", "widen": "widen the approach first",
            "cheap_first": "signal change first, build nothing yet", "one_way_first": "one-way side road first, build nothing yet",
            "nothing": "nothing tested beats the noise here: look elsewhere", "elevated": "already has a flyover"}

ADVICE_SHAPE = {   # documentation for the frontend; see also backend README
    "junction": "j08", "name": "Nanal Nagar jn", "weather": None, "verdict": "build the flyover", "verdict_code": "build",
    "headline": "one sentence", "options": [{"kind": "flyover", "params": {}, "trip_change_min": -3.1, "noise_min": 0.5,
                                           "beyond_noise": True, "ripple": {"worse": [], "better": []}, "rain_change_min": -2.9,
                                           "at_110_change_min": -4.9, "robust": True, "cost_class": "high: construction (assumed)",
                                           "cost_rank": 4, "run_id": "rc_...", "warnings": [], "applicable": True, "rank": 1}],
    "baseline": {"run_id": "rc_...", "trip_min": 56.6, "tomtom_measured_min": 58.2}, "reasons": [], "caveats": [],
    "data": {"leg_in": {}, "leg_out": {}, "live": {}, "rain": {}, "waterlogging": None, "labels": {}},
    "brief_id": "b_...", "run_ids": [], "fingerprints": {}, "model_version": "sha256[:16]", "computed_at": 0.0,
}


class LocalRunner:
    """Runs in this process through the same path as the run_corridor tool (budget, cache, mock)."""
    def __init__(self, ctx: T.Context):
        self.ctx = ctx

    def run(self, interventions: list[dict], volume_scale: float = 1.0, weather: str | None = None) -> dict:
        body = cor.CorridorRunIn(interventions=interventions, volume_scale=volume_scale, run_by="advisor", weather=weather)
        if not cor.is_cached(body):
            if self.ctx.runs_used >= self.ctx.max_runs:
                raise RuntimeError(f"run budget ({self.ctx.max_runs}) used up")
            self.ctx.runs_used += 1
        res = cor.run_blocking(body)
        self.ctx.run_ids.append(res["run_id"])
        return res


class HttpRunner:
    """Runs on a live API (POST /corridor/runs, one SUMO at a time there). Used by advise_all.py."""
    def __init__(self, base: str, timeout: float = 1200):
        import urllib.request
        self.base, self.timeout, self.run_ids, self._rq = base.rstrip("/"), timeout, [], urllib.request

    def run(self, interventions: list[dict], volume_scale: float = 1.0, weather: str | None = None) -> dict:
        body = {"interventions": interventions, "volume_scale": volume_scale, "run_by": "advisor"}
        if weather:
            body["weather"] = weather
        req = self._rq.Request(self.base + "/corridor/runs", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"}, method="POST")
        with self._rq.urlopen(req, timeout=self.timeout) as r:
            res = json.loads(r.read())
        if "result" in res and "journey" not in res:
            res = res["result"]
        self.run_ids.append(res["run_id"])
        return res


def model_version() -> str:
    """Hash of the simulation code and calibration: advice computed on another version is stale."""
    return cor._file_hash(*cor.SIM_SOURCES, cor.CALIBRATION, cor.CORRIDOR_JSON)[:16]


def option_set(jid: str) -> list[dict]:
    L = LONG_STRUCTURE.get(jid, 600)
    return [{"kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.7}},
            {"kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.5}},
            {"kind": "one_way", "params": {"direction": "in"}},
            {"kind": "widening", "params": {"add_lanes": 1}},
            {"kind": "underpass", "params": {"lanes": 2, "length_m": L}},
            {"kind": "flyover", "params": {"lanes": 2, "length_m": L}}]


def _not_applicable(res: dict, jid: str) -> str | None:
    for w in res.get("warnings", []):
        lw = w.lower()
        if jid in w and ("nothing built" in lw or "nothing to make one-way" in lw or "already has a flyover" in lw or "left out" in lw):
            return w
    return None


def gather_data(jid: str) -> dict:
    """Measured and estimated facts about the junction: TomTom leg in/out, live delay vs usual, rain sensitivity."""
    names = T.points()
    out = {"labels": {"legs": "measured (TomTom probe vehicles, July 2026)", "live": "delay measured, queue and volume estimated (TomTom Junction Analytics)",
                      "rain": "estimated (TomTom hourly x Open-Meteo, July 2026; low to moderate confidence)"}}
    periods = cor.tomtom_periods()
    if periods:
        for l in periods[0]["legs"]:
            key = "leg_in" if l["to_id"] == jid else "leg_out" if l["from_id"] == jid else None
            if key:
                out[key] = {"leg": f"{l['from_id']}->{l['to_id']}", "from": l["from_name"], "to": l["to_name"],
                            "min": T.mins(l["time_s"]), "km": round(l["distance_m"] / 1000, 2), "speed_kmh": l["speed_kmh"]}
        out["trip_total_min"] = T.mins(periods[0]["total_s"])
    try:
        live = cor.corridor_junctions_live(60)
        j = next((x for x in live["junctions"] if x["id"] == jid), None)
        if j and j.get("approaches"):
            worst = max(j["approaches"], key=lambda a: a.get("delay_s") or 0)
            out["live"] = {"time": j["time"], "approach": worst["name"], "delay_s": worst.get("delay_s"),
                           "usual_delay_s": worst.get("usual_delay_s"), "queue_m": worst.get("queue_m"),
                           "last_60min_delay_s": (worst.get("last_60min") or {}).get("delay_s")}
        elif j:
            out["live"] = {"note": j.get("note", "no live feed at this junction")}
    except Exception as e:
        out["live"] = {"note": f"no live data ({type(e).__name__})"}
    try:
        f = wx.weather_factors()
        leg_in = (out.get("leg_in") or {}).get("leg")
        row = next((l for l in f.get("per_leg", []) if l.get("leg") == leg_in), None)
        if row:
            out["rain"] = {"leg": leg_in, "light_pct": (row.get("light") or {}).get("pct"),
                           "sustained_light_pct": ((row.get("sustained") or {}).get("light") or {}).get("pct"),
                           "sim_speed_factor": row.get("sim_speed_factor")}
        out["waterlogging"] = f.get("waterlogging", {}).get(jid) if isinstance(f.get("waterlogging"), dict) else None
    except Exception:
        out["waterlogging"] = None
    out["name"] = names.get(jid, jid)
    return out


def _ripple(res: dict, base: dict, jid: str) -> dict:
    d = T.diff(res, base)
    js = [j for j in d["junctions"] if j["junction"].split()[0] != jid]
    worse = [{"junction": j["junction"], "delay_s": j["delay_s"], "queue_m": j["queue_m"]} for j in js if j["delay_s"][1] > j["delay_s"][0] + 3]
    better = [{"junction": j["junction"], "delay_s": j["delay_s"]} for j in js if j["delay_s"][1] < j["delay_s"][0] - 3]
    return {"worse": worse[:4], "better": better[:4], "slower_legs": [l for l in d["legs"] if l["change_min"] > 0][:3],
            "worse_delay_min": round(sum(j["delay_s"][1] - j["delay_s"][0] for j in worse) / 60, 1)}


def _change(res: dict, base: dict) -> float:
    return round((res["journey"]["total_s"] - base["journey"]["total_s"]) / 60, 1)


def advise(jid: str, runner, weather: str | None = None, session_id: str = "advisor", checks: bool = True) -> dict:
    """The full loop for one junction. Raises for a bad junction; a run budget error ends the loop early (advice says so)."""
    if jid not in cor.junction_ids():
        raise ValueError(f"unknown junction {jid!r}; use one of {', '.join(cor.junction_ids())}")
    data = gather_data(jid)
    adv = {"junction": jid, "name": data["name"], "weather": weather, "options": [], "reasons": [], "caveats": [],
           "data": data, "run_ids": [], "fingerprints": {}, "model_version": model_version(), "computed_at": time.time(),
           "noise_min": NOISE_SINGLE_MIN, "cost_ladder": COST_LADDER}
    if jid in ELEVATED:
        return _elevated(adv, jid)
    runs, budget_hit = [], None
    base = runner.run([], 1.0, weather)
    runs.append(base)
    adv["baseline"] = {"run_id": base["run_id"], "trip_min": T.mins(base["journey"]["total_s"]),
                       "tomtom_measured_min": T.mins(base["journey"]["tomtom_total_s"]) if base["journey"].get("tomtom_total_s") else None,
                       "conditions": T.cond_text(T.conds(base)) or "typical July day 06-23 average, calibrated weather",
                       "mock": bool(base.get("sample"))}
    for o in option_set(jid):
        try:
            res = runner.run([{"junction_id": jid, "kind": o["kind"], "params": o["params"]}], 1.0, weather)
        except Exception as e:
            budget_hit = f"{o['kind']}: {e}"
            break
        runs.append(res)
        na = _not_applicable(res, jid)
        adv["options"].append({"kind": o["kind"], "params": o["params"], "trip_change_min": _change(res, base),
                               "noise_min": NOISE_SINGLE_MIN, "beyond_noise": -_change(res, base) > NOISE_SINGLE_MIN and not na,
                               "ripple": _ripple(res, base, jid), "rain_change_min": None, "at_110_change_min": None, "robust": None,
                               "cost_class": COST_CLASS[o["kind"]], "cost_rank": COST_RANK[o["kind"]], "run_id": res["run_id"],
                               "warnings": res.get("warnings", []), "applicable": na is None, "not_applicable_reason": na,
                               "mock": bool(res.get("sample"))})
    # rank: minutes saved beyond noise (then cheaper first, then raw saving); not-applicable last
    def key(o):
        saved = -o["trip_change_min"]
        return (not o["applicable"], -(saved - o["ripple"]["worse_delay_min"] if saved > NOISE_SINGLE_MIN else 0), o["cost_rank"], o["trip_change_min"])
    ranked = sorted(adv["options"], key=key)
    for i, o in enumerate(ranked, 1):
        o["rank"] = i
    top = [o for o in ranked if o["applicable"] and o["beyond_noise"]][:2]
    if checks and top and not budget_hit:
        for cond in ({"weather": "heavy_rain"}, {"volume_scale": ROBUST_VOLUME}):
            try:
                w, v = cond.get("weather", weather), cond.get("volume_scale", 1.0)
                if cond.get("weather") and weather == "heavy_rain":
                    continue
                b2 = runner.run([], v, w)
                runs.append(b2)
                for o in top:
                    r2 = runner.run([{"junction_id": jid, "kind": o["kind"], "params": o["params"]}], v, w)
                    runs.append(r2)
                    o["rain_change_min" if "weather" in cond else "at_110_change_min"] = _change(r2, b2)
                    o.setdefault("check_run_ids", {})["heavy_rain" if "weather" in cond else "at_110"] = r2["run_id"]
            except Exception as e:
                budget_hit = f"checks: {e}"
                break
        for o in top:
            vals = [x for x in (o["rain_change_min"], o["at_110_change_min"]) if x is not None]
            o["robust"] = bool(vals) and all(-x > NOISE_SINGLE_MIN for x in vals)
    adv["options"] = ranked
    adv["run_ids"] = [r["run_id"] for r in runs]
    adv["fingerprints"] = {r["run_id"]: r.get("fingerprint") or cor.fingerprint(r) for r in runs}
    _verdict(adv, jid, data)
    if budget_hit:
        adv["caveats"].append(f"The loop stopped early (run budget): {budget_hit}. Options not listed were not tested.")
    adv["caveats"] += _caveats(runs, weather)
    try:
        adv["brief_id"] = _brief(adv, runs, session_id)
    except Exception as e:   # a brief must never sink the advice
        adv["caveats"].append(f"no decision brief could be written ({type(e).__name__}: {e})")
        adv["brief_id"] = None
    return adv


def _elevated(adv: dict, jid: str) -> dict:
    on = ELEVATED[jid]
    near = {"j03": "j02", "j04": "j05", "j06": "j05", "j07": "j08", "j10": "j09", "j11": "j09"}[jid]
    adv.update({"verdict_code": "elevated", "verdict": f"{VERDICTS['elevated']}: through traffic already crosses {adv['name']} on the {on}",
                "headline": f"{adv['name']} needs no new flyover: the corridor already crosses it on the {on} (another one cannot be built "
                            f"here; the template refuses it). Time lost nearby is at the ground-level junctions: ask about {near} "
                            f"{T.points().get(near, '')}, or retime this junction's ground-level signal for the turning traffic.",
                "alternatives": [{"kind": "signal_retime", "junction_id": jid, "why": "the ground junction under the flyover still serves "
                                  "turning and cross traffic; a retime is cheap and reversible (not simulated here)"},
                                 {"kind": "advice", "junction_id": near, "why": f"nearest ground-level junction; see GET /agent/advice/{near}"}],
                "simulated": False, "baseline": None, "brief_id": None,
                "reasons": [f"Existing structure: {on} (from the simulation network; label: measured)"],
                "caveats": ["No simulations were run for this junction: a second flyover or underpass here is not buildable in the model."]})
    return adv


def _verdict(adv: dict, jid: str, data: dict):
    opts = [o for o in adv["options"] if o["applicable"]]
    saved = lambda o: -o["trip_change_min"]   # noqa: E731
    cheap = [o for o in opts if o["kind"] in ("signal_retime", "one_way")]
    build = [o for o in opts if o["kind"] in ("widening", "underpass", "flyover")]
    best_cheap = min(cheap, key=lambda o: o["rank"]) if cheap else None
    best_build = min(build, key=lambda o: o["rank"]) if build else None
    fly = next((o for o in opts if o["kind"] == "flyover"), None)
    name, R = adv["name"], adv["reasons"]
    base_min = adv["baseline"]["trip_min"]
    if data.get("leg_in"):
        R.append(f"Measured: the stretch into {name} ({data['leg_in']['leg']}) takes {data['leg_in']['min']} min at {data['leg_in']['speed_kmh']} km/h "
                 f"on a typical July day (TomTom); whole trip {data.get('trip_total_min')} min.")
    lv = data.get("live") or {}
    if lv.get("delay_s") is not None:
        R.append(f"Live: {lv['approach']} delay {lv['delay_s']} s now vs {lv['usual_delay_s']} s usual (TomTom, measured).")
    code = "nothing"
    if best_build and saved(best_build) > NOISE_SINGLE_MIN and (not best_cheap or saved(best_cheap) <= NOISE_SINGLE_MIN
                                                                   or saved(best_build) - saved(best_cheap) > NOISE_SINGLE_MIN):
        code = {"flyover": "build", "underpass": "build_underpass", "widening": "widen"}[best_build["kind"]]
        R.append(f"Simulated: {best_build['kind']} saves {saved(best_build):.1f} min on the {base_min} min trip (beyond the +-{NOISE_SINGLE_MIN} min noise)"
                 + (f"; heavy rain {best_build['rain_change_min']:+.1f} min" if best_build.get("rain_change_min") is not None else "")
                 + (f"; at 1.1x traffic {best_build['at_110_change_min']:+.1f} min" if best_build.get("at_110_change_min") is not None else "") + ".")
        if best_cheap:
            R.append(f"The cheapest option ({best_cheap['kind']} {best_cheap['params']}) changes the trip by {best_cheap['trip_change_min']:+.1f} min: "
                     + ("within noise, so it does not solve it alone." if saved(best_cheap) <= NOISE_SINGLE_MIN else "real but clearly less."))
        if best_build.get("robust") is False:
            R.append("Caution: the saving did not hold in every check (rain or 1.1x traffic); treat it as promising, not proven.")
        if fly and best_build is not fly and fly["applicable"]:
            R.append(f"A flyover here would save {saved(fly):.1f} min: {'not better than ' + best_build['kind'] if saved(fly) <= saved(best_build) else 'similar'} "
                     f"at a higher cost class.")
    elif best_cheap and saved(best_cheap) > NOISE_SINGLE_MIN:
        code = "cheap_first" if best_cheap["kind"] == "signal_retime" else "one_way_first"
        R.append(f"Simulated: {best_cheap['kind']} {best_cheap['params']} saves {saved(best_cheap):.1f} min (beyond the +-{NOISE_SINGLE_MIN} min noise)"
                 + (f"; heavy rain {best_cheap['rain_change_min']:+.1f} min" if best_cheap.get("rain_change_min") is not None else "")
                 + (f"; at 1.1x traffic {best_cheap['at_110_change_min']:+.1f} min" if best_cheap.get("at_110_change_min") is not None else "") + ".")
        if fly and fly["applicable"]:
            R.append(f"A flyover saves {saved(fly):.1f} min here: {'no more than the signal change' if saved(fly) - saved(best_cheap) <= NOISE_SINGLE_MIN else 'more, but'}"
                     f" at a far higher cost class; keep it as a later step.")
    else:
        best = opts[0] if opts else None
        R.append(f"Simulated: no option changes the {base_min} min trip beyond the +-{NOISE_SINGLE_MIN} min noise"
                 + (f" (best: {best['kind']} {best['trip_change_min']:+.1f} min)" if best else "") + f". {name} is not where the corridor loses its time.")
    worse = (best_build or best_cheap or {}).get("ripple", {}).get("worse") if code != "nothing" else None
    if worse:
        R.append("Ripple: " + "; ".join(f"{w['junction']} delay {w['delay_s'][0]}->{w['delay_s'][1]} s" for w in worse[:3]) + " (simulated).")
    na = [o for o in adv["options"] if not o["applicable"]]
    if na:
        R.append("Not buildable here: " + "; ".join(f"{o['kind']} ({o['not_applicable_reason']})" for o in na) + ".")
    adv["verdict_code"], adv["verdict"] = code, VERDICTS[code]
    lead = {"build": f"The data supports a flyover at {name}", "build_underpass": f"The data supports an underpass at {name}",
            "widen": f"Widening the approach at {name} is the option the data supports",
            "cheap_first": f"Change the signal at {name} first; build nothing yet", "one_way_first": f"Make the side road at {name} one-way first; build nothing yet",
            "nothing": f"Nothing tested at {name} beats the noise: the time is lost elsewhere"}[code]
    adv["headline"] = lead + " (recommendation for review, not a decision)."


def _caveats(runs: list[dict], weather: str | None) -> list[str]:
    labels = sorted({f"{r.get('inputs', {}).get('counts_source', '?')} ({r.get('inputs', {}).get('label', 'unlabelled')})" for r in runs})
    out = [f"All option results are simulated (SUMO); only TomTom figures are measured. Input labels: {', '.join(labels)}.",
           f"Comparison noise: about +-{NOISE_SINGLE_MIN} min for a one-junction change, +-{NOISE_CORRIDOR_MIN} min for corridor-wide "
           "changes such as rain (seed test, sim/corridor README).",
           f"Cost classes are {COST_LADDER}.",
           "Rain checks use the 'heavy_rain' what-if (July's wettest hours, estimated road-speed factors; not a cloudburst, no waterlogging)."]
    if any(r.get("sample") for r in runs):
        out.insert(0, "MOCK_SIM=1: these are sample or illustrative numbers, not simulations. Re-run with MOCK_SIM=0 before any decision.")
    if weather:
        out.append(f"All main runs were under the '{weather}' what-if, compared with the baseline under the same what-if.")
    return out


def _brief(adv: dict, runs: list[dict], session_id: str) -> str:
    from . import store
    ctx = T.Context(session_id=session_id, max_runs=0)
    for r in runs:
        if not T.ivs(r):
            ctx.baselines[T.run_key(r)] = r
    inp = {"title": f"{adv['name']} ({adv['junction']}): flyover or something cheaper?",
           "problem": (adv["reasons"][0] if adv["reasons"] else "") + " " + (adv["reasons"][1] if len(adv["reasons"]) > 1 else ""),
           "recommendation": adv["headline"], "reasons": adv["reasons"][2:] + adv["caveats"][:2]}
    md, fps = T.render_brief(ctx, inp, runs)
    # the options table of the advice, ranked, in front of the evidence
    rows = ["", "## Advisor ranking", "", "| Rank | Option | Trip change (min) | Heavy rain | 1.1x traffic | Ripple worse at | Cost class | Run |",
            "|---|---|---|---|---|---|---|---|"]
    for o in adv["options"]:
        f = lambda x: "-" if x is None else f"{x:+.1f}"   # noqa: E731
        rows.append(f"| {o['rank']} | {o['kind']} {json.dumps(o['params'])}{'' if o['applicable'] else ' (not buildable)'} | {f(o['trip_change_min'])} | "
                    f"{f(o['rain_change_min'])} | {f(o['at_110_change_min'])} | {', '.join(w['junction'] for w in o['ripple']['worse']) or 'none'} | "
                    f"{o['cost_class']} | `{o['run_id']}` |")
    md = md.replace("\n## Evidence\n", "\n".join(rows) + "\n\n## Evidence\n", 1)
    b = store.save_brief(session_id, md, list(fps), fps, adv["headline"])
    return b["brief_id"]


def compact(adv: dict) -> dict:
    """What the chat model sees: the advice without the raw ripple detail (keeps the tool result small)."""
    out = {k: v for k, v in adv.items() if k not in ("fingerprints",)}
    out["options"] = [{k: v for k, v in o.items() if k not in ("warnings",)} | {"warnings": o.get("warnings", [])[:2]} for o in adv["options"]]
    return out
