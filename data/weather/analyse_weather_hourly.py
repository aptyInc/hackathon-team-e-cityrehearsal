"""Does rain slow the Lingampally -> Lakdikapul trip, hour by hour? (Data and proof workstream)

Inputs
  data/raw/corridor_legs_tomtom.csv   TomTom Traffic Stats, every day 1-31 July 2026, every hour, 12 legs (measured;
                                      jobs 10053357 and 10053399)
  Open-Meteo archive API              hourly weather, July 2026, 3 points along the corridor (downloaded with curl)

Outputs
  data/raw/weather_july_hourly.csv    one row per hour slot (date, hh:00-hh+1:00): weather per point + corridor mean
                                      (measured (Open-Meteo reanalysis))
  data/weather/results.json           every number the README quotes (models, per-leg table, uncertainty)
  data/rain/rain_factors.json         rain factors for the simulation, per rain class (estimated)
  stdout                              a short summary

Alignment: Open-Meteo stamps an hour by its END (precipitation at 09:00 fell between 08:00 and 09:00). TomTom's
slot "08:00-09:00" therefore gets the Open-Meteo row stamped 09:00: precipitation is the total over the slot, and
temperature, humidity, wind, cloud cover and weather code are the values at the end of the slot.

Model (per day d and hour h, hours 06-23, 31 days = 558 hour slots):
    log(trip time) = hour-of-day effect + day-of-week effect + rain class in that hour + rain in the previous hour
Rain classes from the corridor mean (3 points): dry < 0.1 mm, light 0.1-1 mm, moderate 1-5 mm, heavy > 5 mm in the hour.
Uncertainty: standard errors clustered by day (an hour's traffic is not independent of the next hour's), a day-block
bootstrap (resample whole days) for 95% ranges, and a permutation test (give each day another day's rain pattern;
how often is the effect as large by chance?). Per leg: the same model on each leg's time, then each leg's effect is
pulled towards the corridor-wide one in proportion to how noisy it is (empirical Bayes), for the simulation.

Usage: .venv/bin/python -I data/weather/analyse_weather_hourly.py            (downloads weather with curl)
       .venv/bin/python -I data/weather/analyse_weather_hourly.py --offline  (reuses data/weather/_cache/)
No TomTom jobs are created: this only reads results already downloaded.
"""
import csv, datetime as dt, json, re, subprocess, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
OUT = ROOT / "data/weather"
CACHE = OUT / "_cache"            # raw API answers, git-ignored
LEGS_CSV = RAW / "corridor_legs_tomtom.csv"
WEATHER_CSV = RAW / "weather_july_hourly.csv"
RESULTS = OUT / "results.json"
FACTORS = ROOT / "data/rain/rain_factors.json"

POINTS = {  # start, middle (Gachibowli / Khajaguda), end of the corridor (as data/rain/analyse_rain.py)
    "A_lingampally": (17.4878, 78.3142),
    "M_gachibowli": (17.4227, 78.3821),
    "B_lakdikapul": (17.4042, 78.4647),
}
VARS = ["precipitation", "rain", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "weather_code", "cloud_cover"]
URL = ("https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
       "&start_date=2026-07-01&end_date=2026-08-01&hourly=" + ",".join(VARS) + "&timezone=Asia%2FKolkata")
SOURCE = "Open-Meteo historical weather archive (ERA5-based reanalysis, ~9 km grid)"
LABEL = "measured (Open-Meteo reanalysis)"
TOMTOM_JOBS = ("10053357", "10053399")
HOURS = range(6, 24)              # slots 06:00-07:00 .. 23:00-24:00 (the simulation's hours)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CLASSES = [("dry", 0.0, 0.1), ("light", 0.1, 1.0), ("moderate", 1.0, 5.0), ("heavy", 5.0, 1e9)]   # mm in the hour
N_BOOT, N_PERM, SEED = 2000, 2000, 7
WMO = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
       51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
       61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
       71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers", 81: "Showers",
       82: "Violent showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail",
       99: "Thunderstorm with hail"}


def dumps(obj):
    """JSON with one key per line but short lists of numbers on one line."""
    s = json.dumps(obj, indent=1)
    return re.sub(r"\[\s+([-\d.eE+,\snul]+?)\s+\]", lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", s) + "\n"


def rain_class(mm):
    for name, lo, hi in CLASSES:
        if lo <= mm < hi:
            return name
    return "dry"


# ---------------------------------------------------------------- weather
def fetch(offline):
    CACHE.mkdir(exist_ok=True)
    (CACHE / ".gitignore").write_text("*\n")
    data = {}
    for name, (lat, lon) in POINTS.items():
        f = CACHE / f"{name}.json"
        if not (offline and f.exists()):
            # Python's certificate check fails on some team Macs, so download with curl
            subprocess.run(["curl", "-sSf", "--max-time", "60", "-o", str(f), URL.format(lat=lat, lon=lon)], check=True)
        j = json.loads(f.read_text())
        h = j["hourly"]
        data[name] = {"grid": (j["latitude"], j["longitude"]),
                      "vals": {t: {v: h[v][i] for v in VARS} for i, t in enumerate(h["time"])}}
    return data


def slots(om):
    """{(date, hour): row} for every July slot: the Open-Meteo values stamped at the slot's end, per point and mean."""
    out = {}
    for day in range(1, 32):
        d = dt.date(2026, 7, day)
        for h in range(24):
            end = dt.datetime(2026, 7, day, h) + dt.timedelta(hours=1)
            stamp = end.strftime("%Y-%m-%dT%H:%M")
            row = {"date": d.isoformat(), "hour": h, "time_ist": f"{d.isoformat()}T{h:02d}:00",
                   "slot": f"{h:02d}:00-{h + 1:02d}:00", "openmeteo_time_ist": stamp}
            per = {p: om[p]["vals"][stamp] for p in om}
            for p, v in per.items():
                for var in VARS:
                    row[f"{var}_{p}"] = v[var]
            for var in VARS:
                vals = [per[p][var] for p in per if per[p][var] is not None]
                if var == "weather_code":
                    row[f"{var}_mean"] = max(vals) if vals else None     # the most severe of the 3 points
                else:
                    row[f"{var}_mean"] = round(sum(vals) / len(vals), 2) if vals else None
            row["rain_class"] = rain_class(row["precipitation_mean"] or 0.0)
            row["weather_text"] = WMO.get(row["weather_code_mean"], "Unknown")
            out[(d.isoformat(), h)] = row
    return out


def write_weather_csv(rows, om):
    cols = ["date", "hour", "time_ist", "slot", "openmeteo_time_ist"]
    cols += [f"{v}_{p}" for p in om for v in VARS] + [f"{v}_mean" for v in VARS]
    cols += ["rain_class", "weather_text", "source", "label"]
    with open(WEATHER_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for k in sorted(rows):
            r = rows[k] | {"source": SOURCE, "label": LABEL}
            w.writerow(["" if r[c] is None else r[c] for c in cols])


# ---------------------------------------------------------------- traffic
def tomtom():
    """{(date, hour): {"trip_s", "legs": [12 times]}} and the leg list, single days only (one-hour periods)."""
    data, legs = {}, []
    for r in csv.DictReader(LEGS_CSV.open()):
        if r["job"] not in TOMTOM_JOBS:
            continue
        dates, hours = r["period"].split(" ")
        d0, d1 = dates.split("..")
        a, b = (int(x.split(":")[0]) for x in hours.split("-"))
        if d0 != d1 or b - a != 1:
            continue
        e = data.setdefault((d0, a), {"trip_s": float(r["trip_total_s"]), "legs": []})
        e["legs"].append(float(r["time_s"]))
        leg = f"{r['from_id']}-{r['to_id']}"
        if leg not in [l["leg"] for l in legs]:
            legs.append({"leg": leg, "from": r["from"], "to": r["to"], "distance_m": float(r["distance_m"])})
    return data, legs


# ---------------------------------------------------------------- model
RAIN_COLS = {"classes": ["light", "moderate", "heavy", "rain_prev_mm"], "linear": ["rain_now_mm", "rain_prev_mm"],
             "dayfe": ["light", "moderate", "heavy", "rain_prev_mm"]}


def base_matrix(obs, spec):
    """Time-of-week columns. "classes"/"linear": hour-of-day + day-of-week. "dayfe": one level per day (absorbs
    anything that made a whole day slow or fast) + hour-of-day shapes for weekdays and weekends separately."""
    H = np.array([o["hour"] for o in obs])
    hours = list(HOURS)[1:]
    cols = [np.ones(len(obs))]
    if spec == "dayfe":
        D = np.array([o["date"] for o in obs])
        wk = np.array([o["weekend"] for o in obs])
        cols += [D == d for d in sorted(set(D))[1:]]
        cols += [(H == h) & ~wk for h in hours] + [(H == h) & wk for h in hours]
    else:
        W = np.array([o["dow"] for o in obs])
        cols += [H == h for h in hours] + [W == k for k in range(1, 7)]
    return np.column_stack(cols).astype(float)


def rain_matrix(now, prev, cls, names):
    col = {"rain_now_mm": now, "rain_prev_mm": prev, "light": cls == "light", "moderate": cls == "moderate", "heavy": cls == "heavy"}
    return np.column_stack([col[n] for n in names]).astype(float)


def ols(X, y, day_idx):
    """Coefficients and CR1 cluster-robust SEs (clusters = days)."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    S = np.zeros((day_idx.max() + 1, X.shape[1]))
    np.add.at(S, day_idx, X * e[:, None])
    n, k = X.shape
    G = S.shape[0]
    V = G / (G - 1) * (n - 1) / (n - k) * XtX_inv @ (S.T @ S) @ XtX_inv
    return b, np.sqrt(np.clip(np.diag(V), 0, None)), e


def fit(obs, y, spec, rng, boot=N_BOOT, perm=N_PERM):
    """Rain effects (log scale): cluster SEs, day-block bootstrap 95% ranges and permutation p-values.
    obs must be whole days in (date, hour) order (the permutation moves whole days' rain patterns)."""
    n_days = len({o["date"] for o in obs})
    per_day = len(obs) // n_days
    now = np.array([o["rain_now"] for o in obs])
    prev = np.array([o["rain_prev"] for o in obs])
    cls = np.array([o["cls"] for o in obs])
    names = [n for n in RAIN_COLS[spec] if n not in ("light", "moderate", "heavy") or (cls == n).any()]
    B = base_matrix(obs, spec)
    X = np.hstack([B, rain_matrix(now, prev, cls, names)])
    day_idx = np.repeat(np.arange(n_days), per_day)
    b, se, e = ols(X, y, day_idx)
    k = len(names)
    est, ses = b[-k:], se[-k:]
    rows = np.arange(len(obs)).reshape(n_days, per_day)
    bs = np.array([np.linalg.lstsq(X[rows[p].ravel()], y[rows[p].ravel()], rcond=None)[0][-k:]
                   for p in (rng.integers(0, n_days, n_days) for _ in range(boot))]) if boot else np.zeros((1, k))
    hits = np.zeros(k)
    for _ in range(perm):    # each day keeps its own traffic and gets another day's whole rain pattern, hour by hour
        sh = rows[rng.permutation(n_days)].ravel()
        Xp = np.hstack([B, rain_matrix(now[sh], prev[sh], cls[sh], names)])
        bp = np.linalg.lstsq(Xp, y, rcond=None)[0][-k:]
        hits += np.abs(bp) >= np.abs(est)
    out = {}
    for j, n in enumerate(names):
        lo, hi = np.percentile(bs[:, j], [2.5, 97.5])
        out[n] = {"log_effect": float(est[j]), "se_cluster": float(ses[j]),
                  "ci95_cluster": [float(est[j] - 1.96 * ses[j]), float(est[j] + 1.96 * ses[j])],
                  "ci95_bootstrap": [float(lo), float(hi)],
                  "p_permutation": float((hits[j] + 1) / (perm + 1)) if perm else None}
    return out, float(np.std(e)), X.shape, {n: bs[:, j] for j, n in enumerate(names)}


def pct(x):
    return float(round((np.exp(x) - 1) * 100, 1)) + 0.0     # + 0.0: no "-0.0"


def build_obs(tt, wx):
    obs = []
    for (d, h), t in sorted(tt.items()):
        if h not in HOURS:
            continue
        w, wp = wx[(d, h)], wx.get((d, h - 1))
        date = dt.date.fromisoformat(d)
        obs.append({"date": d, "hour": h, "dow": date.weekday(), "weekend": date.weekday() >= 5,
                    "rain_now": w["precipitation_mean"] or 0.0, "rain_prev": (wp["precipitation_mean"] or 0.0) if wp else 0.0,
                    "cls": w["rain_class"], "trip_s": t["trip_s"], "legs": t["legs"]})
    return obs


def shrink(effects, ses, target):
    """Empirical Bayes: pull each leg's log effect towards `target` by se^2 / (se^2 + tau^2); tau^2 = between-leg
    variance beyond noise (method of moments, at least 0)."""
    effects, ses = np.array(effects), np.array(ses)
    tau2 = max(0.0, float(np.var(effects, ddof=1) - np.mean(ses ** 2)))
    w = tau2 / (tau2 + ses ** 2) if tau2 > 0 else np.zeros_like(ses)
    return target + w * (effects - target), w, tau2


def ci(draws):
    return [float(x) for x in np.percentile(draws, [2.5, 97.5])]


def main(offline=False):
    rng = np.random.default_rng(SEED)
    om = fetch(offline)
    wx = slots(om)
    write_weather_csv(wx, om)
    tt, legs = tomtom()
    obs = build_obs(tt, wx)
    assert len(obs) == 31 * len(HOURS), f"expected every day 1-31 July x hours 06-23, got {len(obs)} slots"
    y = np.log(np.array([o["trip_s"] for o in obs]))
    mean_trip_min = float(np.mean([o["trip_s"] for o in obs]) / 60)
    counts = {c: sum(o["cls"] == c for o in obs) for c, _, _ in CLASSES}
    wet = [c for c in ("light", "moderate", "heavy") if counts[c]]
    typical_mm = {c: round(float(np.mean([o["rain_now"] for o in obs if o["cls"] == c])), 2) for c in wet}

    models, draws = {}, {}
    for spec in ("classes", "linear", "dayfe"):
        eff, resid_sd, shape, dr = fit(obs, y, spec, rng, perm=N_PERM if spec == "classes" else 500)
        models[spec] = {"effects": eff, "residual_sd_log": round(resid_sd, 4), "n_obs": shape[0], "n_params": shape[1]}
        draws[spec] = dr
        print(f"model {spec}: n={shape[0]} k={shape[1]} resid sd {resid_sd:.3f}")
        for n, v in eff.items():
            print(f"   {n:13s} {pct(v['log_effect']):+6.1f}%  cluster 95% {pct(v['ci95_cluster'][0]):+.1f}..{pct(v['ci95_cluster'][1]):+.1f}"
                  f"  boot {pct(v['ci95_bootstrap'][0]):+.1f}..{pct(v['ci95_bootstrap'][1]):+.1f}  p_perm {v['p_permutation']:.3f}")
    # any rain (>= 0.1 mm) vs dry, one number: the classes model with every wet class merged
    eff_any, _, _, _ = fit([o | {"cls": "light" if o["cls"] != "dry" else "dry"} for o in obs], y, "classes", rng)
    models["any_rain"] = {"effects": {"any_rain": eff_any["light"], "rain_prev_mm": eff_any["rain_prev_mm"]}}
    a = eff_any["light"]
    print(f"any rain: {pct(a['log_effect']):+.1f}%  boot {pct(a['ci95_bootstrap'][0]):+.1f}..{pct(a['ci95_bootstrap'][1]):+.1f}  "
          f"p_perm {a['p_permutation']:.3f}")

    # sustained rain: that class in this hour after an hour with the class's typical amount (it has been raining a while)
    cm, dr = models["classes"]["effects"], draws["classes"]
    sustained = {c: {"log_effect": cm[c]["log_effect"] + cm["rain_prev_mm"]["log_effect"] * typical_mm[c],
                     "ci95_bootstrap": ci(dr[c] + dr["rain_prev_mm"] * typical_mm[c]), "typical_mm": typical_mm[c]} for c in wet}
    for c, s in sustained.items():
        print(f"sustained {c} ({typical_mm[c]} mm/h): {pct(s['log_effect']):+.1f}%  boot {pct(s['ci95_bootstrap'][0]):+.1f}.."
              f"{pct(s['ci95_bootstrap'][1]):+.1f}")

    # per leg: classes model on log(leg time), bootstrap only (permutations for 12 legs add little); every component
    # (each wet class, previous hour) pulled towards the corridor-wide estimate in proportion to its noise
    per_leg = []
    for j, leg in enumerate(legs):
        yl = np.log(np.array([o["legs"][j] for o in obs]))
        eff, _, _, dl = fit(obs, yl, "classes", rng, boot=1000, perm=0)
        per_leg.append(leg | {"mean_min": round(float(np.mean([o["legs"][j] for o in obs]) / 60), 2), "effects": eff, "draws": dl})
    tau = {}
    for comp in wet + ["rain_prev_mm"]:
        sh, w, tau2 = shrink([l["effects"][comp]["log_effect"] for l in per_leg], [l["effects"][comp]["se_cluster"] for l in per_leg],
                             cm[comp]["log_effect"])
        tau[comp] = round(float(np.sqrt(tau2)), 4)
        for l, s, ww in zip(per_leg, sh, w):
            l["effects"][comp]["log_effect_shrunk"] = float(s)
            l["effects"][comp]["weight_own_estimate"] = round(float(ww), 3)
    for l in per_leg:
        l["sustained"] = {}
        for c in wet:
            m = typical_mm[c]
            l["sustained"][c] = {"log_effect": l["effects"][c]["log_effect"] + l["effects"]["rain_prev_mm"]["log_effect"] * m,
                                 "ci95_bootstrap": ci(l["draws"][c] + l["draws"]["rain_prev_mm"] * m),
                                 "log_effect_shrunk": l["effects"][c]["log_effect_shrunk"] + l["effects"]["rain_prev_mm"]["log_effect_shrunk"] * m}
        print(f"   {l['leg']:24s} " + "  ".join(f"{c}: {pct(l['sustained'][c]['log_effect']):+6.1f}% "
                                              f"({pct(l['sustained'][c]['ci95_bootstrap'][0]):+.0f}..{pct(l['sustained'][c]['ci95_bootstrap'][1]):+.0f})"
                                              f" -> {pct(l['sustained'][c]['log_effect_shrunk']):+.1f}%" for c in wet))
    print("between-leg spread beyond noise (tau, log):", tau)
    res = write_results(obs, wx, counts, wet, typical_mm, models, sustained, per_leg, tau, mean_trip_min, om)
    write_factors(res, obs, models, sustained, per_leg, wet, typical_mm)
    print(f"wrote {WEATHER_CSV.relative_to(ROOT)}, {RESULTS.relative_to(ROOT)}, {FACTORS.relative_to(ROOT)}")


def share_by_hour(wx):
    """Per hour 06-23: share of July days in each rain class."""
    out = {}
    for h in HOURS:
        cs = [wx[(dt.date(2026, 7, d).isoformat(), h)]["rain_class"] for d in range(1, 32)]
        out[str(h)] = {c: round(cs.count(c) / len(cs), 3) for c, _, _ in CLASSES}
    cs = [wx[(dt.date(2026, 7, d).isoformat(), h)]["rain_class"] for d in range(1, 32) for h in HOURS]
    out["all"] = {c: round(cs.count(c) / len(cs), 3) for c, _, _ in CLASSES}
    return out


def pct_ci(e):
    return {"pct": pct(e["log_effect"]), "ci95_pct": [pct(x) for x in e["ci95_bootstrap"]]}


def write_results(obs, wx, counts, wet, typical_mm, models, sustained, per_leg, tau, mean_trip_min, om):
    cm, a = models["classes"]["effects"], models["any_rain"]["effects"]["any_rain"]
    wettest = sorted(obs, key=lambda o: -o["rain_now"])[:8]
    res = {
        "question": "Does rain in an hour slow the Lingampally -> Lakdikapul trip in that hour, by how much, and where?",
        "data": {
            "traffic": "TomTom Traffic Stats jobs 10053357 + 10053399: every day 1-31 July 2026, one-hour slots, 12 legs (measured)",
            "weather": f"{SOURCE}, 3 points (grid cells {', '.join(f'{v[0]:.2f},{v[1]:.2f}' for v in (om[p]['grid'] for p in om))}); "
                       "corridor value = mean of the 3 points",
            "slots": len(obs), "days": 31, "hours": f"{HOURS[0]:02d}:00-{HOURS[-1] + 1:02d}:00",
            "slots_by_rain_class": counts, "typical_mm_per_hour": typical_mm,
            "class_limits_mm_per_hour": {c: [lo, None if hi > 1e8 else hi] for c, lo, hi in CLASSES},
            "max_hourly_rain_mm": round(max(o["rain_now"] for o in obs), 2),
            "wettest_slots": [{"date": o["date"], "slot": f"{o['hour']:02d}:00-{o['hour'] + 1:02d}:00", "rain_mm": o["rain_now"],
                               "trip_min": round(o["trip_s"] / 60, 1)} for o in wettest],
            "mean_trip_min_06_23": round(mean_trip_min, 1),
            "alignment": "TomTom slot hh:00-hh+1:00 <- Open-Meteo row stamped hh+1:00 (precipitation = total over the preceding hour)",
        },
        "model": "log(trip time) = hour-of-day + day-of-week + rain class in the hour + previous hour's rain (mm); SEs clustered "
                 "by day; 95% ranges from a day-block bootstrap (2000 resamples of whole days); p from a permutation test (2000 "
                 "times, each day gets another day's whole rain pattern). Effects are on the log scale: pct = exp(effect) - 1",
        "models": models,
        "headline": {
            "any_rain": pct_ci(a) | {"p": round(a["p_permutation"], 3), "minutes_on_mean_trip": round(mean_trip_min * (np.exp(a["log_effect"]) - 1), 1)},
            "by_class": {c: pct_ci(cm[c]) | {"p": round(cm[c]["p_permutation"], 3), "slots": counts[c],
                                             "minutes_on_mean_trip": round(mean_trip_min * (np.exp(cm[c]["log_effect"]) - 1), 1)} for c in wet},
            "previous_hour_per_mm": pct_ci(cm["rain_prev_mm"]) | {"p": round(cm["rain_prev_mm"]["p_permutation"], 3)},
            "sustained": {c: pct_ci(s) | {"typical_mm": s["typical_mm"],
                                          "minutes_on_mean_trip": round(mean_trip_min * (np.exp(s["log_effect"]) - 1), 1)}
                          for c, s in sustained.items()},
            "within_day_check": {c: pct_ci(models["dayfe"]["effects"][c]) | {"p": round(models["dayfe"]["effects"][c]["p_permutation"], 3)}
                                 for c in wet + ["rain_prev_mm"]},
            "linear_per_mm": pct_ci(models["linear"]["effects"]["rain_now_mm"]) | {"p": round(models["linear"]["effects"]["rain_now_mm"]["p_permutation"], 3)},
        },
        "per_leg": [{"leg": l["leg"], "from": l["from"], "to": l["to"], "distance_m": l["distance_m"], "mean_min": l["mean_min"],
                     **{c: pct_ci(l["effects"][c]) | {"pct_shrunk": pct(l["effects"][c]["log_effect_shrunk"]),
                                                      "weight_own_estimate": l["effects"][c]["weight_own_estimate"]} for c in wet},
                     "previous_hour_per_mm": pct_ci(l["effects"]["rain_prev_mm"]) | {"pct_shrunk": pct(l["effects"]["rain_prev_mm"]["log_effect_shrunk"])},
                     "sustained": {c: pct_ci(l["sustained"][c]) | {"pct_shrunk": pct(l["sustained"][c]["log_effect_shrunk"])} for c in wet}}
                    for l in per_leg],
        "per_leg_spread_beyond_noise_log": tau,
        "share_of_days_by_hour": share_by_hour(wx),
        "label": "estimated",
        "generated_by": "data/weather/analyse_weather_hourly.py",
    }
    RESULTS.write_text(dumps(res))
    return res


def write_factors(res, obs, models, sustained, per_leg, wet, typical_mm):
    """rain_factors.json: the keys the first look wrote (the planning agent reads overall_travel_time_factor, label,
    confidence) with hourly-based values; per-class factors; the simulation's what-if settings and reference factors."""
    old = json.loads(FACTORS.read_text()) if FACTORS.exists() else {}
    first_look = old.get("first_look") or {k: old[k] for k in ("overall_speed_factor", "overall_travel_time_factor", "per_leg",
                                                                 "stress_test", "basis", "confidence") if k in old}
    cm = models["classes"]["effects"]
    a = models["any_rain"]["effects"]["any_rain"]
    ids = [l["leg"] for l in per_leg]

    def tf(x):
        return round(float(np.exp(x)), 4)

    def leg_time(l, cls, prev_mm):
        """The simulation's time factor on a leg (vs a dry hour after a dry hour): shrunk estimates, never below 1
        (assumed: rain does not make a road faster; a lower estimate is noise)."""
        e = (l["effects"][cls]["log_effect_shrunk"] if cls != "dry" else 0.0) + l["effects"]["rain_prev_mm"]["log_effect_shrunk"] * prev_mm
        return max(1.0, tf(e))

    by_class = {"dry": {"travel_time_factor": 1.0, "slots": res["data"]["slots_by_rain_class"]["dry"],
                        "mm_per_hour": [0.0, 0.1], "note": "reference: under 0.1 mm in the hour"}}
    for c in wet:
        by_class[c] = {
            "mm_per_hour": res["data"]["class_limits_mm_per_hour"][c], "typical_mm": typical_mm[c], "slots": res["data"]["slots_by_rain_class"][c],
            "travel_time_factor": tf(cm[c]["log_effect"]), "travel_time_factor_ci95": [tf(x) for x in cm[c]["ci95_bootstrap"]],
            "p_permutation": round(cm[c]["p_permutation"], 4),
            "sustained_travel_time_factor": tf(sustained[c]["log_effect"]),
            "sustained_travel_time_factor_ci95": [tf(x) for x in sustained[c]["ci95_bootstrap"]],
            "per_leg_speed_factor_raw": {l["leg"]: tf(-l["effects"][c]["log_effect"]) for l in per_leg},
            "per_leg_speed_factor_raw_ci95": {l["leg"]: [tf(-l["effects"][c]["ci95_bootstrap"][1]), tf(-l["effects"][c]["ci95_bootstrap"][0])]
                                              for l in per_leg},
            "per_leg_speed_factor_shrunk": {l["leg"]: tf(-l["effects"][c]["log_effect_shrunk"]) for l in per_leg},
        }
    if "heavy" not in by_class:
        by_class["heavy"] = {"travel_time_factor": None, "slots": 0, "mm_per_hour": [5.0, None],
                             "note": "no hour in July 2026 reached 5 mm/h in the reanalysis (its ~9 km grid smooths downpours); no estimate"}
    top = wet[-1]
    settings = {"dry": ("dry", 0.0, "no rain in the hour or the hour before"),
                "light_rain": ("light", typical_mm.get("light", 0.0),
                               f"light rain (0.1-1 mm/h, typically {typical_mm.get('light')} mm) this hour and the hour before"),
                "heavy_rain": (top, typical_mm[top],
                               f"the wettest hours July 2026 had: {by_class[top]['mm_per_hour'][0]:g}+ mm/h (typically {typical_mm[top]} mm) "
                               "this hour and the hour before. The reanalysis smooths downpours: a rain gauge would usually record more")}
    what_if = {"legs": ids, "settings": {}}
    for name, (cls, mm, meaning) in settings.items():
        t = [leg_time(l, cls, mm) for l in per_leg]
        trip = (1.0, [1.0, 1.0]) if cls == "dry" else (tf(sustained[cls]["log_effect"]), [tf(x) for x in sustained[cls]["ci95_bootstrap"]])
        what_if["settings"][name] = {"class": cls, "mm_this_hour": mm, "mm_previous_hour": mm, "meaning": meaning,
                                     "trip_travel_time_factor": trip[0], "trip_travel_time_factor_ci95": trip[1],
                                     "per_leg_time_factor": t, "per_leg_speed_factor": {i: round(1 / x, 4) for i, x in zip(ids, t)}}
    # the simulation is calibrated to TomTom averages that already contain rainy hours: the factor applied is relative
    # to that mix (speed factor on a leg = reference time factor / setting's time factor)
    ref = {(o["date"], o["hour"]): [leg_time(l, o["cls"], o["rain_prev"]) for l in per_leg] for o in obs}
    mean = lambda keys: [round(float(np.mean([ref[k][j] for k in keys])), 4) for j in range(len(ids))]  # noqa: E731
    what_if["reference_time_factors"] = {
        "all_day": mean([k for k in ref if k[1] < 23]),            # the all-day calibration: July, 06:00-23:00
        "hour": {str(h): mean([k for k in ref if k[1] == h]) for h in HOURS},
        "day_hour": {f"{d} {h:02d}": v for (d, h), v in sorted(ref.items()) if any(x != 1.0 for x in v)},
        "note": "per leg (order of `legs`), the rain time factor baked into each calibration target: the all-day July "
                "calibration (06-23), a typical July hour (mean over the 31 days), a single day-hour (its own rain; dry "
                "day-hours are left out and mean 1.0)"}
    what_if["how"] = ("speed cap on leg i = calibrated cap x reference_time_factors[target][i] / settings[weather].per_leg_time_factor[i]; "
                      "nothing else changes (demand, signals)")
    out = {
        "overall_travel_time_factor": tf(a["log_effect"]),
        "overall_travel_time_factor_ci95": [tf(x) for x in a["ci95_bootstrap"]],
        "overall_speed_factor": round(1 / tf(a["log_effect"]), 4),
        "per_leg": what_if["settings"]["light_rain"]["per_leg_speed_factor"],
        "per_leg_note": "speed factors while light rain has been falling for an hour (the commonest wet hour); heavier rain in "
                        "what_if.settings.heavy_rain. Per-leg estimates are pulled towards the corridor-wide one in proportion "
                        "to their noise (empirical Bayes) and never above 1 (assumed: rain does not make a road faster)",
        "stress_test": {"overall_travel_time_factor": tf(sustained[top]["ci95_bootstrap"][1]),
                        "overall_speed_factor": round(1 / tf(sustained[top]["ci95_bootstrap"][1]), 4),
                        "note": f"upper end of the 95% range for sustained {top} rain; a pessimistic what-if, not the expected case"},
        "by_class": by_class,
        "what_if": what_if,
        "demand_factor": 1.0,
        "demand_basis": "no evidence either way; keep demand unchanged (assumed)",
        "applies_to": "one-hour slots 06:00-24:00, Lingampally -> Lakdikapul; rain class from the 3-point corridor mean in that hour",
        "basis": (f"TomTom Traffic Stats one-hour slots, every day 1-31 July 2026 ({res['data']['slots']} slots, 06-23 h) vs "
                  "Open-Meteo hourly rain (ERA5-based reanalysis, mean of 3 points). log(trip) ~ hour + weekday + rain class + "
                  f"previous hour's rain; day-block bootstrap 95% ranges, permutation p. Any rain in the hour: "
                  f"{pct(a['log_effect']):+.1f}% (95% range {pct(a['ci95_bootstrap'][0]):+.1f} to {pct(a['ci95_bootstrap'][1]):+.1f}%, "
                  f"p={a['p_permutation']:.3f}). Comparing rainy and dry hours of the same day: no difference."),
        "confidence": confidence(models),
        "label": "estimated",
        "source_files": ["data/raw/corridor_legs_tomtom.csv", "data/raw/weather_july_hourly.csv",
                         "data/weather/analyse_weather_hourly.py", "data/weather/results.json"],
        "first_look": first_look | {"note": "first look (data/rain/analyse_rain.py): daily 08-20 averages, 1-15 July only"},
    }
    FACTORS.write_text(dumps(out))


def confidence(models):
    a = models["any_rain"]["effects"]["any_rain"]
    if a["ci95_bootstrap"][0] > 0 and a["p_permutation"] < 0.05:
        return "moderate: slower traffic in rainy hours is distinguishable from zero with 558 hour slots; its size is uncertain"
    return ("low: rainy hours look a few percent slower, but with 558 hour slots this is not statistically certain, and "
            "rainy and dry hours of the same day do not differ")


if __name__ == "__main__":
    main(offline="--offline" in sys.argv)
