"""Does rain slow the Lingampally -> Lakdikapul trip? (Data and proof workstream)

Inputs
  data/raw/corridor_legs_tomtom.csv  TomTom Traffic Stats, one 08:00-20:00 average per day, 1-15 July 2026 (measured)
  data/tomtom/corridor/*.json        raw TomTom jobs (median trip time per day)
  Open-Meteo archive API             hourly precipitation, July 2026, 3 points along the corridor (downloaded with curl)

Outputs
  data/raw/rain_july_hyderabad.csv   hourly precipitation per point + 3-point mean (measured: ERA5-based reanalysis)
  data/raw/corridor_rain_vs_trip.csv per day 1-15 July: weekday, rain, wet hours, trip and per-leg minutes
  data/rain/rain_factors.json        recommended rain setting for the simulation (estimated)
  data/rain/rain_vs_trip.png         one small chart
  stdout                             the numbers quoted in data/rain/README.md

Usage: .venv/bin/python -I data/rain/analyse_rain.py            (downloads rain with curl)
       .venv/bin/python -I data/rain/analyse_rain.py --offline  (reuses data/rain/_openmeteo_cache/)
No TomTom jobs are created: this only reads results already downloaded.
"""
import csv, datetime as dt, json, subprocess, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
OUT = ROOT / "data/rain"
CACHE = OUT / "_openmeteo_cache"  # raw API answers, git-ignored

POINTS = {  # start, middle (Gachibowli / Khajaguda), end of the corridor
    "A_lingampally": (17.4878, 78.3142),
    "M_gachibowli": (17.4227, 78.3821),
    "B_lakdikapul": (17.4042, 78.4647),
}
URL = ("https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
       "&start_date=2026-07-01&end_date=2026-07-31&hourly=precipitation,rain&timezone=Asia%2FKolkata")
SOURCE = "Open-Meteo historical weather archive (ERA5-based reanalysis)"
WET_HOUR_MM = 0.5     # an hour is "wet" at >= 0.5 mm (3-point mean)
WET_DAY_MM = 2.0      # a day is "wet" at >= 2 mm in 08:00-20:00, "dry" below 0.5 mm, "light" in between
DRY_DAY_MM = 0.5
DAY_START, DAY_END = 8, 20  # TomTom's daily time set is 08:00-20:00 (hours 08..19)
HOURS = DAY_END - DAY_START

# Two-sided 95% t critical values, df 1..30 (no scipy in the venv)
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
       2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


# ---------------------------------------------------------------- rain
def fetch_rain(offline):
    CACHE.mkdir(exist_ok=True)
    data = {}
    for name, (lat, lon) in POINTS.items():
        f = CACHE / f"{name}.json"
        if not (offline and f.exists()):
            # Python's certificate check fails on some team Macs, so download with curl
            subprocess.run(["curl", "-sSf", "--max-time", "60", "-o", str(f), URL.format(lat=lat, lon=lon)], check=True)
        j = json.loads(f.read_text())
        h = j["hourly"]
        data[name] = {"grid": (j["latitude"], j["longitude"]),
                      "precip": dict(zip(h["time"], [v or 0.0 for v in h["precipitation"]])),
                      "rain": dict(zip(h["time"], [v or 0.0 for v in h["rain"]]))}
    return data


def write_rain_csv(rain):
    times = sorted(next(iter(rain.values()))["precip"])
    with open(RAW / "rain_july_hyderabad.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_ist"] + [f"{k}_{n}" for n in rain for k in ("precip_mm", "rain_mm")]
                   + ["precip_mm_mean3", "source", "label"])
        for t in times:
            vals = [v for n in rain for v in (rain[n]["precip"][t], rain[n]["rain"][t])]
            mean = sum(rain[n]["precip"][t] for n in rain) / len(rain)
            w.writerow([t] + vals + [round(mean, 2), SOURCE, "measured"])


def daily_rain(rain):
    """Per date: 08-20 total (3-point mean), wet hours (3-point mean >= 0.5 mm), 24 h total, 08-20 total per point."""
    times = sorted(next(iter(rain.values()))["precip"])
    out = defaultdict(lambda: {"mm": 0.0, "wet_h": 0, "mm_24h": 0.0, "per_point": defaultdict(float)})
    for t in times:
        day, hh = t[:10], int(t[11:13])
        m = sum(rain[n]["precip"][t] for n in rain) / len(rain)
        out[day]["mm_24h"] += m
        if DAY_START <= hh < DAY_END:
            out[day]["mm"] += m
            out[day]["wet_h"] += int(m >= WET_HOUR_MM)
            for n in rain:
                out[day]["per_point"][n] += rain[n]["precip"][t]
    return out


# ---------------------------------------------------------------- traffic
def load_trips():
    legs, trips, names, leg_order = defaultdict(dict), {}, {}, []
    with open(RAW / "corridor_legs_tomtom.csv") as fh:
        for r in csv.DictReader(fh):
            day, day_to = r["period"][:10], r["period"][12:22]
            if day != day_to:
                continue  # the whole-July average
            leg = f'{r["from_id"]}-{r["to_id"]}'
            if leg not in leg_order:
                leg_order.append(leg)
            names[leg] = f'{r["from"].split(" (")[0]} -> {r["to"].split(" (")[0]}'
            legs[day][leg] = float(r["time_s"]) / 60
            trips[day] = (float(r["trip_total_s"]) / 60, int(r["job"]))
    median = {}
    for day, (_, job) in trips.items():
        s = json.loads((ROOT / f"data/tomtom/corridor/{job}.json").read_text())["routes"][0]["summaries"][0]
        median[day] = (s["medianTravelTime"] / 60, s.get("planningTimeIndex"))
    return legs, trips, median, leg_order, names


# ---------------------------------------------------------------- stats
def ols(y, X):
    """OLS with classical standard errors and 95% CIs. X includes the intercept column."""
    y, X = np.asarray(y, float), np.asarray(X, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    df = len(y) - X.shape[1]
    s2 = resid @ resid / df
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    t = T95[df - 1]
    r2 = 1 - resid @ resid / ((y - y.mean()) @ (y - y.mean()))
    return beta, se, beta - t * se, beta + t * se, df, r2, float(np.sqrt(s2))


def perm_test(a, b, n=20000, seed=7):
    """Two-sided permutation p-value for a difference in means."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    obs, pool, hits = a.mean() - b.mean(), np.concatenate([a, b]), 0
    rng = np.random.default_rng(seed)
    for _ in range(n):
        rng.shuffle(pool)
        hits += abs(pool[:len(a)].mean() - pool[len(a):].mean()) >= abs(obs) - 1e-9
    return hits / n


def sign_flip_test(d):
    """Exact two-sided sign-flip p-value for a mean paired difference."""
    d = np.asarray(d, float)
    obs, n, hits = abs(d.mean()), len(d), 0
    for mask in range(2 ** n):
        s = np.array([1 if mask >> i & 1 else -1 for i in range(n)])
        hits += abs((s * d).mean()) >= obs - 1e-9
    return hits / 2 ** n


def main():
    offline = "--offline" in sys.argv
    rain = fetch_rain(offline)
    write_rain_csv(rain)
    dr = daily_rain(rain)
    legs, trips, median, leg_order, names = load_trips()
    days = sorted(trips)

    rows = []
    for day in days:
        wd = dt.date.fromisoformat(day).strftime("%a")
        mm = dr[day]["mm"]
        row = {"date": day, "weekday": wd,
               "day_type": "sunday" if wd == "Sun" else ("saturday" if wd == "Sat" else "weekday"),
               "rain_mm_08_20": round(mm, 2), "wet_hours_08_20": dr[day]["wet_h"],
               "rain_mm_24h": round(dr[day]["mm_24h"], 2),
               **{f"rain_mm_08_20_{k}": round(v, 2) for k, v in dr[day]["per_point"].items()},
               "rain_class": "wet" if mm >= WET_DAY_MM else ("dry" if mm < DRY_DAY_MM else "light"),
               "trip_min": round(trips[day][0], 2), "trip_median_min": round(median[day][0], 2),
               "planning_time_index": median[day][1], "tomtom_job": trips[day][1]}
        for leg in leg_order:
            row[f"min_{leg}"] = round(legs[day][leg], 2)
        row["rain_label"] = "measured (ERA5-based reanalysis, mean of 3 points)"
        row["trip_label"] = "measured (TomTom Traffic Stats, 08:00-20:00 average)"
        rows.append(row)
    with open(RAW / "corridor_rain_vs_trip.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    p = print
    p("Rain grid cells used:", {n: d["grid"] for n, d in rain.items()})
    p("\nPer day (rain = mean of 3 points, 08-20):")
    p(f"{'date':10} {'day':3} {'mm':>5} {'wet_h':>5} {'class':5} {'trip':>5} {'median':>6}  mm per point A/M/B")
    for r in rows:
        pp = " ".join(f"{r[f'rain_mm_08_20_{k}']:4.1f}" for k in POINTS)
        p(f"{r['date']} {r['weekday']} {r['rain_mm_08_20']:5.1f} {r['wet_hours_08_20']:5d} {r['rain_class']:5} "
          f"{r['trip_min']:5.1f} {r['trip_median_min']:6.1f}  {pp}")
    p("\nAll July (3-point mean, mm 08-20 / 24 h): "
      + " ".join(f"{d[8:]}:{dr[d]['mm']:.1f}/{dr[d]['mm_24h']:.1f}" for d in sorted(dr)))

    # 1. Weekdays: wet vs dry
    wk = [r for r in rows if r["day_type"] == "weekday"]
    wet = [r for r in wk if r["rain_class"] == "wet"]
    dry = [r for r in wk if r["rain_class"] == "dry"]
    light = [r for r in wk if r["rain_class"] == "light"]
    res = {}
    for key in ("trip_min", "trip_median_min"):
        a, b = [r[key] for r in wet], [r[key] for r in dry]
        diff = np.mean(a) - np.mean(b)
        res[key] = dict(wet=float(np.mean(a)), dry=float(np.mean(b)), n_wet=len(a), n_dry=len(b), diff=float(diff),
                        pct=float(diff / np.mean(b) * 100), p=perm_test(a, b),
                        wet_vals=a, dry_vals=b, light_vals=[r[key] for r in light])
        p(f"\n[1] WEEKDAYS {key}: wet n={len(a)} mean {np.mean(a):.1f} {a}; dry n={len(b)} mean {np.mean(b):.1f} "
          f"(sd {np.std(b, ddof=1):.1f}) {b}; light n={len(light)} {res[key]['light_vals']}")
        p(f"    wet - dry = {diff:+.1f} min ({res[key]['pct']:+.1f}%), permutation p = {res[key]['p']:.2f}")
    a = [r["trip_min"] for r in wet + light]
    b = [r["trip_min"] for r in dry]
    res["any_rain"] = dict(mean=float(np.mean(a)), n=len(a), diff=float(np.mean(a) - np.mean(b)),
                           pct=float((np.mean(a) / np.mean(b) - 1) * 100), p=perm_test(a, b))
    p(f"    any rain (>=0.5 mm) n={len(a)} mean {np.mean(a):.1f} vs dry {np.mean(b):.1f}: "
      f"{res['any_rain']['diff']:+.1f} min ({res['any_rain']['pct']:+.1f}%), p = {res['any_rain']['p']:.2f}")
    wk_all = [r["trip_min"] for r in wk]
    res["weekday_sd"] = float(np.std(wk_all, ddof=1))
    p(f"    all weekdays n={len(wk_all)}: mean {np.mean(wk_all):.1f}, sd {res['weekday_sd']:.1f}, "
      f"range {min(wk_all):.1f}-{max(wk_all):.1f}")

    # 2. Same weekday, week 1 (1-7 July, rainy spell) vs week 2 (8-14 July, dry spell)
    by = {r["date"]: r for r in rows}
    pairs = [(f"2026-07-0{i}", f"2026-07-{i + 7:02d}") for i in range(1, 8)]
    d_min = [by[a]["trip_min"] - by[b]["trip_min"] for a, b in pairs]
    d_pct = [(by[a]["trip_min"] / by[b]["trip_min"] - 1) * 100 for a, b in pairs]
    res["paired"] = dict(pairs=[(by[a]["weekday"], a[8:], b[8:], by[a]["rain_mm_08_20"], by[b]["rain_mm_08_20"],
                                 round(x, 1), round(y, 1)) for (a, b), x, y in zip(pairs, d_min, d_pct)],
                         mean_min=float(np.mean(d_min)), mean_pct=float(np.mean(d_pct)), p=sign_flip_test(d_pct))
    p("\n[2] SAME WEEKDAY, week of 1-7 July (rainy) minus week of 8-14 July (dry):")
    for pr in res["paired"]["pairs"]:
        p(f"    {pr[0]} {pr[1]} ({pr[3]:.1f} mm) vs {pr[2]} ({pr[4]:.1f} mm): {pr[5]:+.1f} min ({pr[6]:+.1f}%)")
    p(f"    mean {res['paired']['mean_min']:+.1f} min ({res['paired']['mean_pct']:+.1f}%), "
      f"exact sign-flip p = {res['paired']['p']:.2f}, n=7 pairs")

    # 3. Regressions on all 15 days, controlling for Saturday / Sunday
    y = np.array([r["trip_min"] for r in rows])
    sun = np.array([r["day_type"] == "sunday" for r in rows], float)
    sat = np.array([r["day_type"] == "saturday" for r in rows], float)
    preds = {"rain_mm_08_20": [r["rain_mm_08_20"] for r in rows],
             "wet_hours_08_20": [r["wet_hours_08_20"] for r in rows],
             "rain_mm_24h": [r["rain_mm_24h"] for r in rows],
             "wet_day": [r["rain_class"] == "wet" for r in rows]}
    res["reg"] = {}
    p("\n[3] REGRESSION trip_min ~ rain + is_saturday + is_sunday (n=15):")
    for nm, x in preds.items():
        X = np.column_stack([np.ones(len(y)), np.asarray(x, float), sat, sun])
        b, se, lo, hi, df, r2, s = ols(y, X)
        res["reg"][nm] = dict(coef=float(b[1]), lo=float(lo[1]), hi=float(hi[1]), r2=float(r2), resid_sd=s,
                              base=float(b[0]), sat=float(b[2]), sun=float(b[3]))
        p(f"    {nm:16} {b[1]:+.2f} min per unit, 95% CI [{lo[1]:+.2f}, {hi[1]:+.2f}]   "
          f"(weekday base {b[0]:.1f}, Sat {b[2]:+.1f}, Sun {b[3]:+.1f}, R2 {r2:.2f}, resid sd {s:.1f})")

    # Translate "minutes per wet hour" in a 12-hour daily average into "% slower while it rains".
    # If trips are spread evenly over 08-20, one wet hour moves the daily average by (1/12) x the in-rain slowdown.
    base = res["reg"]["wet_hours_08_20"]["base"]
    per_h = res["reg"]["wet_hours_08_20"]
    in_rain = {k: per_h[k] * HOURS / base for k in ("coef", "lo", "hi")}
    res["in_rain"] = in_rain
    p(f"\n    => while it is raining: travel time {in_rain['coef'] * 100:+.0f}% "
      f"(95% CI {in_rain['lo'] * 100:+.0f}% to {in_rain['hi'] * 100:+.0f}%)")

    # 4. Per leg: weekday wet vs dry, plus a per-leg wet-hours regression on all 15 days
    p("\n[4] PER LEG (weekday wet vs dry; regression on wet hours, all days, -> % slower while raining):")
    per_leg = {}
    wh = np.asarray(preds["wet_hours_08_20"], float)
    for leg in leg_order:
        yl = np.array([r[f"min_{leg}"] for r in rows])
        X = np.column_stack([np.ones(len(yl)), wh, sat, sun])
        b, se, lo, hi, df, r2, s = ols(yl, X)
        a_ = [r[f"min_{leg}"] for r in wet]
        b_ = [r[f"min_{leg}"] for r in dry]
        per_leg[leg] = dict(name=names[leg], dry=float(np.mean(b_)), wet=float(np.mean(a_)),
                            ratio=float(np.mean(a_) / np.mean(b_)), cv_dry=float(np.std(b_, ddof=1) / np.mean(b_)),
                            in_rain=float(b[1] * HOURS / b[0]), in_rain_lo=float(lo[1] * HOURS / b[0]),
                            in_rain_hi=float(hi[1] * HOURS / b[0]),
                            weekdays=[round(r[f"min_{leg}"], 1) for r in wk])
        # same weekday, rainy week (1-7 July) vs dry week (8-14 July)
        dp = [(by[a][f"min_{leg}"] / by[b][f"min_{leg}"] - 1) * 100 for a, b in pairs]
        v = per_leg[leg]
        v.update(paired_pct=[round(x, 1) for x in dp], paired_mean_pct=float(np.mean(dp)),
                 paired_median_pct=float(np.median(dp)), paired_up=sum(x > 0 for x in dp), paired_p=sign_flip_test(dp))
        flag = "  <-- 7/7 pairs slower" if v["paired_up"] == len(dp) else ""
        p(f"    {leg:17} {v['name']:46} dry {v['dry']:4.1f} wet {v['wet']:4.1f} x{v['ratio']:.2f} | "
          f"in rain {v['in_rain'] * 100:+4.0f}% [{v['in_rain_lo'] * 100:+.0f}, {v['in_rain_hi'] * 100:+.0f}] | "
          f"rainy week vs dry week: mean {v['paired_mean_pct']:+.0f}%, median {v['paired_median_pct']:+.0f}%, "
          f"{v['paired_up']}/7 slower, p={v['paired_p']:.3f}{flag}")
    # The split between the first two legs depends on where TomTom places the Nallagandla junction, and they move
    # in opposite directions; check them together.
    comb = [(by[a][f"min_{leg_order[0]}"] + by[a][f"min_{leg_order[1]}"]) /
            (by[b][f"min_{leg_order[0]}"] + by[b][f"min_{leg_order[1]}"]) * 100 - 100 for a, b in pairs]
    res["first_two_legs_paired"] = dict(mean=float(np.mean(comb)), up=sum(x > 0 for x in comb), p=sign_flip_test(comb))
    p(f"    first two legs together (Lingampally -> ISB Rd): rainy vs dry week mean {np.mean(comb):+.1f}%, "
      f"{res['first_two_legs_paired']['up']}/7 slower, p={res['first_two_legs_paired']['p']:.2f}")
    return rows, res, per_leg, leg_order, dr


# ---------------------------------------------------------------- outputs
def write_factors(res, per_leg):
    """Recommended rain setting. See README 'Recommended setting' for the reasoning."""
    central = max(0.0, res["in_rain"]["coef"])          # best estimate while raining (travel-time increase)
    stress = max(0.0, res["in_rain"]["hi"])              # upper end of the 95% CI: a pessimistic 'heavy rain' case
    leg_tt = {}
    for leg, v in per_leg.items():
        # A leg gets its own number only if it was slower on the rainy day in every same-weekday pair
        # (rainy week 1-7 July vs dry week 8-14 July, exact sign-flip p < 0.05); then it gets that mean slowdown.
        # Otherwise it gets the corridor-wide number, so per-leg factors don't just amplify noise.
        # (Regression-only per-leg signals are not used: A->j01 and j01->j02 trade time at their shared junction.)
        own = v["paired_up"] == len(v["paired_pct"]) and v["paired_p"] < 0.05
        leg_tt[leg] = max(central, v["paired_mean_pct"] / 100) if own else central
    f = {
        "overall_speed_factor": round(1 / (1 + central), 3),
        "overall_travel_time_factor": round(1 + central, 3),
        "per_leg": {k: round(1 / (1 + t), 3) for k, t in leg_tt.items()},
        "per_leg_note": ("speed factors: multiply free-flow / max speed on that leg's edges while it rains. Every leg "
                         "gets the corridor-wide value except legs slower on the rainy day in all 7 same-weekday pairs "
                         f"(only j03-j04 Gachibowli Circle -> Biodiversity jn: +{per_leg['j03-j04']['paired_mean_pct']:.0f}% "
                         f"mean, +{per_leg['j03-j04']['paired_median_pct']:.0f}% median). Low confidence."),
        "stress_test": {
            "overall_speed_factor": round(1 / (1 + stress), 3),
            "overall_travel_time_factor": round(1 + stress, 3),
            "note": "upper end of the 95% confidence range; use for a 'heavy rain' what-if, not as the expected case",
        },
        "demand_factor": 1.0,
        "applies_to": "hours when it is raining (>= 0.5 mm/h), 08:00-20:00, Lingampally -> Lakdikapul",
        "basis": (f"TomTom Traffic Stats daily 08:00-20:00 averages, 1-15 July 2026 (15 days) vs Open-Meteo "
                  f"ERA5-based hourly rain (mean of 3 points). Regression trip_min ~ wet_hours + Sat + Sun gives "
                  f"{res['reg']['wet_hours_08_20']['coef']:+.2f} min per wet hour "
                  f"(95% CI {res['reg']['wet_hours_08_20']['lo']:+.2f} to {res['reg']['wet_hours_08_20']['hi']:+.2f}), "
                  f"i.e. {res['in_rain']['coef'] * 100:+.0f}% travel time while raining "
                  f"(95% CI {res['in_rain']['lo'] * 100:+.0f}% to {res['in_rain']['hi'] * 100:+.0f}%). Whole-day effect "
                  f"on rainy weekdays not distinguishable from day-to-day noise "
                  f"({res['trip_min']['wet']:.1f} vs {res['trip_min']['dry']:.1f} min). Light-to-moderate monsoon "
                  f"showers only (max 7 mm in a 12-hour window); heavy-rain days (17, 29, 30 July) were not covered."),
        "confidence": "low: effect not statistically distinguishable from zero with 15 days",
        "demand_basis": "no evidence either way; keep demand unchanged (assumed)",
        "label": "estimated",
        "source_files": ["data/raw/corridor_rain_vs_trip.csv", "data/raw/rain_july_hyderabad.csv",
                         "data/rain/analyse_rain.py"],
    }
    (OUT / "rain_factors.json").write_text(json.dumps(f, indent=2) + "\n")
    print("\nrain_factors.json:", json.dumps({k: f[k] for k in ("overall_speed_factor", "per_leg", "stress_test")}))


def write_chart(rows, res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, ink2, muted, grid, axis, surface = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
    style = {"weekday": ("#2a78d6", "o", "Weekday (Mon-Fri)"), "saturday": ("#eb6834", "s", "Saturday"),
             "sunday": ("#1baf7a", "^", "Sunday")}
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=110)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)
    for dtype, (c, m, lab) in style.items():
        pts = [r for r in rows if r["day_type"] == dtype]
        ax.scatter([r["rain_mm_08_20"] for r in pts], [r["trip_min"] for r in pts], s=64, c=c, marker=m, label=lab,
                   edgecolors=surface, linewidths=2, zorder=3)
    base = res["reg"]["rain_mm_08_20"]
    xs = np.array([0, 7.6])
    ax.plot(xs, base["base"] + base["coef"] * xs, color=muted, lw=1.5, ls="--", zorder=2)
    ax.text(7.6, base["base"] + base["coef"] * 7.6 + 0.8, "weekday trend (Sat/Sun adjusted): flat", color=ink2, fontsize=8.5, ha="right")
    for r in rows:
        if r["date"][8:] in ("02", "03", "04", "05", "08", "10", "12"):
            ax.annotate(f"{int(r['date'][8:])} Jul", (r["rain_mm_08_20"], r["trip_min"]), xytext=(6, -3),
                        textcoords="offset points", fontsize=8, color=ink2)
    ax.set_xlabel("Rain 08:00-20:00 (mm, mean of 3 points on the corridor)", color=ink2, fontsize=9)
    ax.set_ylabel("Average trip, 08:00-20:00 (minutes)", color=ink2, fontsize=9)
    ax.set_title("Lingampally to Lakdikapul, 1-15 July 2026: rainy days not measurably slower",
                 color=ink, fontsize=10.5, loc="left")
    ax.set_ylim(44, 68)
    ax.set_xlim(-0.4, 8)
    ax.grid(True, color=grid, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(axis)
    ax.tick_params(colors=muted, labelsize=8.5)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right", labelcolor=ink2)
    fig.text(0.01, 0.01, "Sources: TomTom Traffic Stats (measured), Open-Meteo ERA5-based archive (modelled rain).",
             fontsize=7.5, color=muted)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / "rain_vs_trip.png", facecolor=surface)
    plt.close(fig)


if __name__ == "__main__":
    rows, res, per_leg, leg_order, dr = main()
    write_factors(res, per_leg)
    write_chart(rows, res)
