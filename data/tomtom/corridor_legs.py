"""Split TomTom's corridor travel time at the corridor's junctions (data/corridor/corridor.json).

Reads the Traffic Stats route-analysis results in data/tomtom/corridor/<jobId>.json (job 10051304: all of July 2026,
06:00-23:00; jobs 10051327-10051341: one per day 1-15 July, 08:00-20:00; job 10053357: July and each day 1-23 July,
hour by hour), one row set per (date range, time set) in each job, places each junction on the measured route, adds up the
segment travel times between consecutive junctions, and scales them so the legs sum to TomTom's whole-trip average
(per-segment averages miss some of the waiting a whole trip sees). Label: measured.
Writes data/raw/corridor_legs_tomtom.csv: one row per (period, leg).
Usage: python3 data/tomtom/corridor_legs.py
"""
import csv, glob, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORRIDOR = json.loads((ROOT / "data/corridor/corridor.json").read_text())


def dist(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))


def legs_for(path):
    """Leg rows for every (date range, time set) pair in one job's results."""
    d = json.load(open(path)); r = d["routes"][0]
    ranges = {x.get("@id", i + 1): x for i, x in enumerate(d["dateRanges"])}
    tsets = {x.get("@id", i + 1): x for i, x in enumerate(d["timeSets"])}
    segs, cum = [], 0.0
    for s in r["segmentResults"]:
        segs.append({"start": cum, "len": s["distance"], "shape": [(p["latitude"], p["longitude"]) for p in s["shape"]],
                     "t": {(x["dateRange"], x["timeSet"]): x.get("averageTravelTime") for x in s["segmentTimeResults"]}})
        cum += s["distance"]

    def locate(lat, lon):
        best = (1e9, 0.0)
        for r_ in segs:
            acc = 0.0
            for a, b in zip(r_["shape"], r_["shape"][1:]):
                seg = dist(a, b)
                for f in (0, 0.25, 0.5, 0.75, 1):
                    p = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
                    dd = dist(p, (lat, lon))
                    if dd < best[0]:
                        best = (dd, r_["start"] + acc + seg * f)
                acc += seg
        return best

    pos = [(p, *locate(p["lat"], p["lon"])) for p in CORRIDOR["points"]]
    out = []
    for summ in r["summaries"]:
        pair, trip = (summ["dateRange"], summ["timeSet"]), summ.get("averageTravelTime")
        if not trip:
            continue
        known = [(x["len"], x["t"].get(pair)) for x in segs if x["t"].get(pair)]
        if not known:
            continue
        speed = sum(L for L, _ in known) / sum(t for _, t in known)   # m/s, fills segments without probe data in this slot
        times = [x["t"].get(pair) or x["len"] / speed for x in segs]

        def time_between(x0, x1):
            return sum(t * max(0.0, min(x["start"] + x["len"], x1) - max(x["start"], x0)) / x["len"]
                       for x, t in zip(segs, times) if x["len"])

        raw = [(a, b, x1 - x0, time_between(x0, x1)) for (a, _, x0), (b, _, x1) in zip(pos, pos[1:])]
        k = trip / sum(t for *_, t in raw)
        dr, ts = ranges[pair[0]], tsets[pair[1]]
        period = f"{dr['from']}..{dr['to']} {ts['name']}"
        coverage = round(sum(L for L, _ in known) / cum, 3)
        out += [{"period": period, "job": Path(path).stem, "from_id": a["id"], "to_id": b["id"], "from": a["name"], "to": b["name"],
                 "distance_m": round(L), "time_s": round(t * k, 1), "speed_kmh": round(L / (t * k) * 3.6, 1) if t else None,
                 "trip_total_s": round(trip, 1), "coverage": coverage, "label": "measured"} for a, b, L, t in raw]
    return out, max(off for _, off, _ in pos)


if __name__ == "__main__":
    out, worst = [], 0
    for f in sorted(glob.glob(str(ROOT / "data/tomtom/corridor/[0-9]*.json"))):
        rows, off = legs_for(f); out += rows; worst = max(worst, off)
    with open(ROOT / "data/raw/corridor_legs_tomtom.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(f"{len(out)} rows from {len(out) // (len(CORRIDOR['points']) - 1)} reports; farthest junction from the route: {worst:.0f} m")
