"""Build the YMCA Circle baseline traffic (SUMO flows) from real inputs.

Inputs (all in /data, labels as in data/README.md):
  - data/raw/ymca_counts.csv            vehicles/hour per approach and class, 2020 study      (counted)
  - data/raw/tomtom_ymca_turn_ratios.csv where each approach's vehicles exit, TomTom live     (measured)
  - data/tomtom/junction/ymca_definition.json  TomTom approach/exit geometry, to find network edges
Assumptions (labelled `assumed` in the output file header):
  - study "light motor vehicles" split 70% car / 30% auto-rickshaw; heavy vehicles modelled as buses
  - study legs matched to approaches by place name (see LEG_TO_APPROACH)
Output: sim/demand/ymca_baseline.rou.xml (vehicle types + one flow per approach, exit and class)

Usage: python sim/scripts/build_demand.py [--scale 1.0] [--since HH:MM] [--until HH:MM]
"""
import argparse, csv, json, math
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path
import sumolib

ROOT = Path(__file__).resolve().parents[2]
NET = ROOT / "sim/networks/ymca.net.xml"
OUT = ROOT / "sim/demand/ymca_baseline.rou.xml"
UPSTREAM_M = 250  # vehicles enter this far before the circle, so queues have room to form

# Study leg -> TomTom approach. King Koti and Ramkoti lie west/south-west, Kachiguda east,
# Barkatpura north-east; the remaining leg is Narayanguda Road from the south. (estimated)
LEG_TO_APPROACH = {
    "King Koti road": "YMCA to Ramkoti Road East Bound",
    "Kacheguda signal": "Raja Bahadur Venkata Rama Reddy Marg West Bound",
    "Barkathpura road": "Narayanguda Road South Bound",
    "Narayanaguda road": "Narayanguda Road North Bound",
}
CAR_SHARE_OF_LMV = 0.70  # assumed
ROAD_SCALE = {}          # optional per-approach multipliers (TomTom approach name -> factor); see --mix tomtom


def tomtom_road_scale():
    """Rescale the 2020 study's split between roads to TomTom's morning shares (08:00-11:00 median veh/h)."""
    import statistics as st
    vol = {}
    for r in csv.DictReader(open(ROOT / "data/raw/tomtom_ymca_junction_live.csv")):
        if "08:00" <= r["time"][11:16] < "11:00":
            vol.setdefault(r["approach"], []).append(float(r["volume_per_hour"]))
    tomtom = {a: st.median(v) for a, v in vol.items()}
    study = {LEG_TO_APPROACH[r["approach"]]: float(r["total_vehicles"]) for r in csv.DictReader(open(ROOT / "data/raw/ymca_counts.csv"))}
    ts, ss = sum(tomtom.values()), sum(study.values())
    return {a: (tomtom[a] / ts) / (study[a] / ss) for a in study if a in tomtom}

VTYPES = """    <!-- Sublane model: run SUMO with lateral-resolution 0.3 so two-wheelers and autos filter between cars.
         minGap / tau (following distance and reaction time) are set close, as Indian city traffic drives (assumed):
         with SUMO's defaults the circle carried only ~3,300 vehicles/h at TomTom's speeds; with these, ~5,700/h. -->
    <vType id="two_wheeler" vClass="motorcycle" length="1.9" width="0.75" minGap="0.5" tau="0.6" maxSpeed="16.7" accel="3.0" decel="5.0"
           speedFactor="normc(0.85,0.1,0.5,1.2)" latAlignment="arbitrary" minGapLat="0.3" lcSublane="2.0" lcPushy="0.6" color="1,0.6,0"/>
    <vType id="auto" vClass="passenger" length="2.7" width="1.4" minGap="0.7" tau="0.7" maxSpeed="12.5" accel="1.8" decel="4.0"
           speedFactor="normc(0.85,0.1,0.5,1.1)" latAlignment="arbitrary" minGapLat="0.4" lcSublane="1.5" lcPushy="0.4" color="0.2,0.7,0.2"/>
    <vType id="car" vClass="passenger" length="4.3" width="1.75" minGap="1.0" tau="0.8" maxSpeed="16.7" accel="2.6" decel="4.5"
           speedFactor="normc(0.85,0.1,0.5,1.2)" latAlignment="center" minGapLat="0.5" color="0.3,0.5,0.9"/>
    <vType id="bus" vClass="bus" length="11" width="2.5" minGap="1.5" tau="1.0" maxSpeed="13.9" accel="1.2" decel="4.0"
           speedFactor="normc(0.8,0.1,0.5,1.0)" latAlignment="center" minGapLat="0.6" color="0.8,0.1,0.1"/>
"""


def approach_edges(net, definition):
    """Match each TomTom approach/exit to the network edge that touches the roundabout along the same road."""
    jm = definition["junctionModel"]
    centre = net.convertLonLat2XY(*definition["rawJunction"]["geometry"]["coordinates"])
    rb = min(net.getRoundabouts(), key=lambda r: math.hypot(*(a - b for a, b in zip(net.getNode(r.getNodes()[0]).getCoord(), centre))))
    nodes = set(rb.getNodes())
    ins = [e for n in nodes for e in net.getNode(n).getIncoming() if e.getFromNode().getID() not in nodes]
    outs = [e for n in nodes for e in net.getNode(n).getOutgoing() if e.getToNode().getID() not in nodes]

    def far_point(feature_coords):
        pts = [net.convertLonLat2XY(lon, lat) for lon, lat in feature_coords]
        return max(pts, key=lambda p: math.hypot(p[0] - centre[0], p[1] - centre[1]))

    def bearing(p):
        return math.atan2(p[1] - centre[1], p[0] - centre[0])

    def match(items, edges, end):
        out = {}
        for it in items:
            coords = it["segmentedGeometry"]["coordinates"]
            flat = [c for seg in coords for c in seg] if isinstance(coords[0][0], list) else coords
            b = bearing(far_point(flat))
            def edge_bearing(e):
                shape = e.getShape()
                p = shape[0] if end == "in" else shape[-1]
                return bearing(p)
            out[it["name"]] = min(edges, key=lambda e: abs(math.remainder(edge_bearing(e) - b, 2 * math.pi)))
        return out
    return match(jm["approaches"], ins, "in"), match(jm["exits"], outs, "out")


def walk(edge, metres, backwards):
    """Follow the road away from the circle until `metres` are covered; return the edge reached."""
    total, e, seen = edge.getLength(), edge, {edge.getID()}
    while total < metres:
        nxt = [x for x in (e.getIncoming() if backwards else e.getOutgoing())
               if x.getID() not in seen and not x.getID().startswith(":")
               and (x.getFromNode() != e.getToNode() if backwards else x.getToNode() != e.getFromNode())]  # no U-turn back
        # follow the road through bends: take the continuation with the smallest change of direction (under 80 degrees)
        turn = lambda x: abs(math.remainder(angle(x) - angle(e), 2 * math.pi))
        nxt = [x for x in nxt if turn(x) < math.radians(80)]
        if not nxt:
            break
        e = min(nxt, key=turn); seen.add(e.getID()); total += e.getLength()
    return e


def angle(e):
    s = e.getShape()
    return math.atan2(s[-1][1] - s[0][1], s[-1][0] - s[0][0])


def turn_shares(since, until, window=None):
    """Probe-weighted turn shares per approach: by time of day (since/until HH:MM) or an absolute window
    ((start datetime, end datetime), from `window_bounds`). An approach with under 20 probes in the window falls
    back to the morning shares, so a quiet night window still gets sensible turns."""
    agg, tot = defaultdict(lambda: defaultdict(float)), defaultdict(float)
    for r in csv.DictReader(open(ROOT / "data/raw/tomtom_ymca_turn_ratios.csv")):
        if window:
            t = datetime.fromisoformat(r["time"])
            if not (window[0] <= t < window[1]):
                continue
        else:
            hhmm = r["time"][11:16]
            if since and hhmm < since or until and hhmm >= until:
                continue
        p = float(r["probes"]); agg[r["approach"]][r["exit"]] += p; tot[r["approach"]] += p
    shares = {a: {x: p / tot[a] for x, p in ex.items()} for a, ex in agg.items() if tot[a] >= 20}
    if window:
        morning = turn_shares("08:00", "11:00")
        for a in morning:
            shares.setdefault(a, morning[a])
    return shares


def window_bounds(start: str, minutes: int):
    """Absolute window in IST from an ISO start such as 2026-10-09T09:00 (offset optional)."""
    t0 = datetime.fromisoformat(start)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
    return t0, t0 + timedelta(minutes=minutes)


def tomtom_window(window):
    """TomTom Junction Analytics medians per approach inside the window: vehicles/hour (estimated), delay (measured),
    queue (estimated), travel time (measured)."""
    import statistics as st
    rows = defaultdict(lambda: defaultdict(list))
    for r in csv.DictReader(open(ROOT / "data/raw/tomtom_ymca_junction_live.csv")):
        t = datetime.fromisoformat(r["time"])
        if window[0] <= t < window[1]:
            for k in ("volume_per_hour", "delay_s", "queue_m", "travel_time_s"):
                rows[r["approach"]][k].append(float(r[k]))
    return {a: {k: st.median(v) for k, v in ks.items()} | {"minutes": len(ks["delay_s"])} for a, ks in rows.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="traffic volume multiplier (C2 volume_scale)")
    ap.add_argument("--since", help="use TomTom turn ratios from this time of day (HH:MM)")
    ap.add_argument("--until", help="... up to this time of day (HH:MM)")
    ap.add_argument("--begin", type=int, default=0); ap.add_argument("--end", type=int, default=4200)
    ap.add_argument("--mix", choices=["study", "tomtom"], default="study", help="split between roads: 2020 study or TomTom's morning shares")
    ap.add_argument("--window", help="rebuild a specific time: ISO start in IST, e.g. 2026-10-09T09:00; volumes and turns from "
                                     "TomTom junction data in that window, vehicle mix from the 2020 count")
    ap.add_argument("--minutes", type=int, default=15, help="window length for --window")
    args = ap.parse_args()
    road_scale = tomtom_road_scale() if args.mix == "tomtom" else dict(ROAD_SCALE)
    window = window_bounds(args.window, args.minutes) if args.window else None
    tomtom = tomtom_window(window) if window else {}

    net = sumolib.net.readNet(str(NET))
    definition = json.loads((ROOT / "data/tomtom/junction/ymca_definition.json").read_text())
    ins, outs = approach_edges(net, definition)
    shares = turn_shares(args.since, args.until, window)
    counts = {r["approach"]: r for r in csv.DictReader(open(ROOT / "data/raw/ymca_counts.csv"))}

    source = (f'     Window {window[0].isoformat(timespec="minutes")} to {window[1].isoformat(timespec="minutes")}: volumes per road = TomTom '
              'Junction Analytics median vehicles/hour (estimated); turns from the same window (measured); vehicle mix '
              'per road from the 2020 study (assumed).' if window else
              '     Volumes: 2020 study counts per approach and class (counted). Turns: TomTom Junction Analytics,'
              f' probe-weighted{" " + (args.since or "") + "-" + (args.until or "") if args.since or args.until else ""} (measured).')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<!-- YMCA Circle baseline traffic, built by sim/scripts/build_demand.py (scale {args.scale}).',
             source,
             f'     Assumed: car/auto split {int(CAR_SHARE_OF_LMV*100)}/{int(100-CAR_SHARE_OF_LMV*100)} of light vehicles; heavy = bus;'
             ' study legs matched to approaches by place name.' + (f' Road split rescaled to TomTom morning shares: ' + ', '.join(f'{a.split()[0]} x{k:.2f}' for a, k in road_scale.items()) if road_scale else '') + ' -->',
             '<routes>', VTYPES]
    for leg, approach in LEG_TO_APPROACH.items():
        c = counts[leg]; k = road_scale.get(approach, 1.0)
        if window and approach in tomtom:  # TomTom's volume for the window, split into classes with the 2020 proportions
            k = tomtom[approach]["volume_per_hour"] / float(c["total_vehicles"])
        per_class = {"two_wheeler": float(c["motorcycle"]) * k, "car": float(c["light_motor_vehicle"]) * CAR_SHARE_OF_LMV * k,
                     "auto": float(c["light_motor_vehicle"]) * (1 - CAR_SHARE_OF_LMV) * k, "bus": float(c["heavy_vehicle"]) * k}
        origin = walk(ins[approach], UPSTREAM_M, backwards=True)
        lines.append(f'    <!-- {leg} -> {approach}: enters on {origin.getID()} -->')
        for exit_name, share in sorted(shares[approach].items(), key=lambda kv: -kv[1]):
            if share < 0.01:
                continue
            dest = walk(outs[exit_name], UPSTREAM_M, backwards=False)
            for vtype, vph in per_class.items():
                rate = vph * share * args.scale
                if rate < 0.5:
                    continue
                fid = f"{leg.split()[0].lower()}_{exit_name.split()[0].lower()}_{exit_name.split()[-2].lower()}_{vtype}"
                lines.append(f'    <flow id="{fid}" type="{vtype}" from="{origin.getID()}" to="{dest.getID()}" begin="{args.begin}" end="{args.end}"'
                             f' vehsPerHour="{rate:.1f}" departLane="best" departSpeed="max" departPosLat="random"/>')
    lines.append('</routes>')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {sum(1 for l in lines if '<flow' in l)} flows")
    for a, e in ins.items():
        print(f"  approach {a:50} -> entry edge {e.getID()} ({e.getName() or 'unnamed'})")
    for a, e in outs.items():
        print(f"  exit     {a:50} -> exit edge  {e.getID()} ({e.getName() or 'unnamed'})")


if __name__ == "__main__":
    main()
