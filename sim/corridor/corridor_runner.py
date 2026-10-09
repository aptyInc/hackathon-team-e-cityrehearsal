"""Corridor simulation, Lingampally -> Lakdikapul: interventions in, C5 corridor result out.

Traffic
  - Through traffic both ways along the corridor on fixed routes (end-to-end volume per direction: calibrated). At
    Lakdikapul (B) it disperses before the last ~130 m, a 5-into-2-lane give-way merge; only probe cars drive on.
  - Cross traffic at every signalised junction. Where TomTom Junction Analytics measures the junction (corridor_junctions
    .json, picked up automatically), each cross-road approach gets TomTom's volume (mean of the minutes collected,
    `estimated`) times cross_scale, and TomTom's turn ratios decide how much joins the corridor each way or crosses it.
    Elsewhere: CROSS_VPH per approach, a third each way (`assumed`). Joining traffic drives JOIN_M on the corridor.
    Cross traffic enters INSERT_BACK_M up its road, so the junction's queue does not block it from entering.
  - Probe cars every 30 s both ways record when they pass each corridor point: the trip time split by leg.

Noise: journey.total_s_se is the uncertainty of the trip time as an absolute number: the probe cars' spread in this
run combined with the run-to-run spread (the calibrated baseline with 3 other seeds, run_to_run_sd_s in
calibration.json). Comparing a variant with the baseline is a paired comparison: driving is deterministic (Krauss
sigma 0), every run uses the same seed, the same traffic and the same netconvert rebuild (sim/templates/corridor.py
rebuilds every variant; the baseline gets a rebuild with no change), so a change only moves the legs of the sections
it touches. For that, use total_s_se_probes: a change is beyond noise when it exceeds about twice both runs'
total_s_se_probes combined (about +-0.8 min).

Running fast: the corridor runs as 6 sections (SECTIONS) at once, one SUMO each. A section is its legs plus 1 km of
road before them (traffic reaches the first junction in realistic platoons) and 300 m after; traffic entering it is the
corridor flow at that point. Trip time = sum of the legs. Each section starts full (fill flows), so 10 minutes of
warm-up and 15 minutes of probes are enough. A run takes about 20-40 s; frames (C1) cover 5 minutes.

Calibration (`calibrate()`, writes calibration.json), in plain words: TomTom measured how long each leg takes on
average (July 2026, 6 am-11 pm, `counted`) and, this evening, how long vehicles wait on the corridor's approaches at
the junctions it watches (Junction Analytics, `estimated`). We run the baseline, compare, adjust, a few times over:
  - leg too fast -> lower its speed (the leg's road speed stands in for what SUMO leaves out: buses stopping, parked
    vehicles, pedestrians, autos pulling in and out, "side friction").
  - leg too slow -> raise its speed; if it is already at 60 km/h the time is lost at the junction ending the leg, so
    the corridor gets more of that junction's green (up to 80%).
  - junction delay below TomTom's -> the corridor gets less green there (down to 35%; Gachibowli Circle no lower than
    70%, below which its roundabout locks up in some runs), so more of the trip is spent waiting at junctions, as
    TomTom measures, and less as slow road. The target is TomTom's delay but at most the leg's time above free flow
    (50 km/h), since the delays are evening means and the leg times all-day means. j04 (the corridor passes over it
    on the Biodiversity flyover) is left out of the delay targets; its volumes are still compared.
  - the network does not cope (vehicles stuck or unable to enter), or a leg is too slow even with 80% green -> all
    traffic is lowered 10% (to no less than 70% of the starting volumes).
The baseline then reproduces the measured trip, and interventions change it through what SUMO does model: junction
delays, queues, lanes and signals. Every knob is labelled in calibration.json and in the C5 result (inputs.sources).

    python sim/corridor/corridor_runner.py calibrate          # writes sim/corridor/calibration.json
    python sim/corridor/corridor_runner.py run [j07:flyover]  # prints the C5 result summary
"""
import csv, heapq, json, math, os, shutil, statistics, subprocess, sys, time, uuid, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "sim/scripts"))
sys.path.insert(0, str(ROOT / "sim/templates"))
import corridor_net as cn  # noqa: E402
import sumolib  # noqa: E402
from build_demand import VTYPES  # noqa: E402

NET = HERE / "corridor.net.xml"
CALIBRATION = HERE / "calibration.json"
LEGS_CSV = ROOT / "data/raw/corridor_legs_tomtom.csv"
JA_CONFIG = ROOT / "data/tomtom/junction/corridor_junctions.json"
JA_LIVE = ROOT / "data/raw/tomtom_corridor_junction_live.csv"
JA_TURNS = ROOT / "data/raw/tomtom_corridor_turn_ratios.csv"
OUT = Path(os.environ.get("CR_SIM_OUT", ROOT / "sim/out")) / "corridor"
CORRIDOR_ID = "lingampally_lakdikapul"
TOMTOM_JOB = "10051304"           # July 2026, every day 06:00-23:00
THROUGH_VPH = {"fwd": 1500, "rev": 1500}   # end-to-end corridor traffic per direction (assumed; calibrated in calibration.json)
CROSS_SCALE = 0.6                 # share of TomTom's estimated cross-road volumes simulated (assumed; calibrated in calibration.json)
CROSS_VPH = 450                   # per cross-road approach at junctions without TomTom counts (assumed)
ASSUMED_SPLIT = {"fwd": 1 / 3, "rev": 1 / 3, "cross": 1 / 3}   # cross traffic: joins A->B, joins B->A, crosses (assumed)
MIN_TURN_PROBES = 10              # TomTom turn ratios are used for an approach once this many probe trips back them
JOIN_M = 3000                     # cross traffic that joins the corridor drives this far on it, then leaves (assumed)
INSERT_BACK_M = 250               # cross traffic enters this far up its road, not at the stop line
FILL_STEP_M, FILL_SPEED = 2500, 6.0   # the corridor starts full: extra entry points every 2.5 km until traffic at 6 m/s arrives
MIX = {"two_wheeler": 0.45, "car": 0.30, "auto": 0.18, "bus": 0.07}   # assumed
MAX_KMH = 60                      # speed cap on the corridor before calibration
MAX_SHARE = 0.8                   # calibration gives the corridor at most this share of a junction's green
MIN_DEMAND = 0.7                  # calibration lowers traffic to no less than this share of the starting volumes
MIN_SHARE = 0.35                  # ... and gives the corridor at least this share of a junction's green
STABLE_SHARE = {"j03": 0.7}       # ... except Gachibowli Circle: below 70% its roundabout fills up and locks in some runs
FREE_KMH = 50                     # free-flow speed on the corridor's roads (assumed): a leg's time above it is delay
STEP = 0.5                        # s; the vehicle types' reaction times (tau 0.6-1.0 s) need steps no longer than this
SEED = 2                          # SUMO random seed: the same for the baseline and every variant (common random numbers)
SIGMA = 0                         # driver imperfection (Krauss sigma): 0, so baseline and variants differ only by the change
TELEPORT_S = 300                  # s a vehicle may stand still before SUMO lifts it out of a deadlock
PARALLEL = int(os.environ.get("CR_SIM_PARALLEL", "6"))   # SUMO processes at once per run (one per section at most)
WARMUP = 600                      # s before the first probe leaves
PROBE_EVERY, PROBE_SPAN = 30, 900   # one probe car each way every 30 s for 15 minutes (30 trips: noise is reported)
END = WARMUP + PROBE_SPAN + 3900  # long enough for the last probe to arrive (TomTom's trip: 58 min)
FRAMES = (WARMUP + 300, WARMUP + 600, 4)   # vehicle positions for the 3D view (C1): from, to, every N s (5 min, ~30 MB)
SECTIONS = [("A_lingampally", "j01"), ("j01", "j02"), ("j02", "j04"), ("j04", "j07"), ("j07", "j09"), ("j09", "B_lakdikapul")]
LEAD_IN_M, TAIL_M = 1000, 300     # road simulated before / after each section's legs
C1_TYPES = {"two_wheeler", "car", "auto", "bus", "truck"}
JUNCTION_BLOCKER_S = 5            # s a vehicle waits behind one stuck inside the junction before squeezing past (assumed; with SUMO's default, never, the junctions locked up)


# ---------- network ----------
def tomtom_legs():
    """TomTom July average per leg: [(from_id, to_id, distance_m, time_s, speed_kmh)] in corridor order."""
    rows = [r for r in csv.DictReader(LEGS_CSV.open()) if r["job"] == TOMTOM_JOB]
    return [(r["from_id"], r["to_id"], float(r["distance_m"]), float(r["time_s"]), float(r["speed_kmh"])) for r in rows]


def leg_edges(net, path):
    """Edges of `path` in each leg (between consecutive corridor points), in leg order."""
    pos = cn.junction_positions(net, path)
    idx = [pos[p["id"]][0] for p in cn.CORRIDOR["points"]]
    return [path[a + 1:b + 1] for a, b in zip(idx, idx[1:])]


def calibrated_net(out: Path, caps=None, shares=None):
    """Copy of the network where each leg's corridor lanes run at the leg's calibrated speed (both directions; it
    replaces OSM's speed limit, which is mostly a road-type default and is 20 km/h on one stretch before Tolichowki),
    and the corridor's green share at each junction ({junction id: share}; others keep CORRIDOR_GREEN_SHARE)."""
    caps = caps if caps is not None else calibration()["cap_kmh"]
    net = sumolib.net.readNet(str(NET))
    fwd, rev = cn.route(net), cn.route(net, reverse=True)
    speed = {}
    for k, edges in enumerate(leg_edges(net, fwd)):
        for e in edges:
            speed[e.getID()] = caps[k] / 3.6
    for k, edges in enumerate(reversed(leg_edges_rev(net, rev))):
        for e in edges:
            speed[e.getID()] = caps[k] / 3.6
    tree = ET.parse(NET)
    for edge in tree.getroot().iter("edge"):
        v = speed.get(edge.get("id"))
        if v:
            for lane in edge.iter("lane"):
                lane.set("speed", f"{v:.2f}")
    tree.write(out)
    if shares and any(abs(v - cn.CORRIDOR_GREEN_SHARE) > 1e-6 for v in shares.values()):
        cn.signal_plans(out, shares)
    return out


def leg_edges_rev(net, rev):
    """Legs of the reverse path, in the reverse path's order (B -> A)."""
    pts = list(reversed(cn.CORRIDOR["points"]))
    pos = {}
    for p in pts:
        x, y = net.convertLonLat2XY(p["lon"], p["lat"])
        pos[p["id"]] = min(range(len(rev)), key=lambda i: math.dist(rev[i].getToNode().getCoord()[:2], (x, y)))
    pos[pts[0]["id"]], pos[pts[-1]["id"]] = -1, len(rev) - 1
    idx = [pos[p["id"]] for p in pts]
    return [rev[a + 1:b + 1] for a, b in zip(idx, idx[1:])]


# ---------- traffic ----------
def tomtom_volumes(field="volume_per_hour"):
    """TomTom Junction Analytics: mean of `field` (veh/h, or delay_s) per (junction_id, approach_id) over all minutes
    collected so far, and the time span collected ('first .. last' minute)."""
    if not JA_LIVE.exists():
        return {}, None
    sums, times = {}, []
    for r in csv.DictReader(JA_LIVE.open()):
        k = (r["junction_id"], r["approach_id"])
        n, v = sums.get(k, (0, 0.0))
        sums[k] = (n + 1, v + float(r.get(field) or 0))
        times.append(r["time"])
    return {k: v / n for k, (n, v) in sums.items()}, f"{min(times)[:16]} .. {max(times)[:16]}" if times else None


def tomtom_turns():
    """TomTom turn ratios, weighted by probe count: {(junction_id, approach name): {exit name: probes}} ({} when the
    collector has not written any)."""
    out = {}
    if JA_TURNS.exists():
        for r in csv.DictReader(JA_TURNS.open()):
            w = float(r["probes"] or 0) * float(r["ratio_percent"] or 0) / 100
            d = out.setdefault((r["junction_id"], r["approach"]), {})
            d[r["exit"]] = d.get(r["exit"], 0.0) + w
    return out


def _match(net, p1, p2, at_start=False, radius=50):
    """Network edge (cars allowed) near p2 (or p1 when `at_start`) heading from p1 to p2 ((lon, lat) points)."""
    x1, y1 = net.convertLonLat2XY(*p1[:2]); x2, y2 = net.convertLonLat2XY(*p2[:2])
    want, (x, y) = math.atan2(y2 - y1, x2 - x1), ((x1, y1) if at_start else (x2, y2))
    cands = [(e, d) for e, d in net.getNeighboringEdges(x, y, radius) if e.allows("passenger")
             and abs(math.remainder(cn._angle(e) - want, 2 * math.pi)) < math.radians(45)]
    return min(cands, key=lambda t: t[1])[0] if cands else None


def _leads_to(e, node_jid, corridor=(), limit=800.0):
    """(junction id, edge entering it): the first corridor junction node within `limit` m downstream of edge `e`,
    not driving along the corridor itself."""
    heap, seen, n = [(0.0, 0, e)], set(), 0
    while heap:
        d, _, x = heapq.heappop(heap)
        if x.getID() in seen:
            continue
        seen.add(x.getID())
        if x.getToNode().getID() in node_jid:
            return node_jid[x.getToNode().getID()], x
        for y in x.getOutgoing():
            if d + x.getLength() < limit and y.getFunction() != "internal" and y.getID() not in corridor:
                n += 1
                heapq.heappush(heap, (d + x.getLength(), n, y))
    return None, None


def _upstream(e, avoid, metres=INSERT_BACK_M):
    """Walk back from edge `e` along the same road (closest heading) for about `metres`, not onto `avoid` edges or
    through corridor junction nodes: cross traffic is inserted there, so its queue has room and insertion is not
    blocked by the junction's own queue."""
    done = 0.0
    while done < metres:
        node = e.getFromNode()
        if node.getID() in avoid:
            break
        ins = [x for x in node.getIncoming() if x.getID() not in avoid and x.allows("passenger") and x.getFromNode() != e.getToNode()]
        if not ins:
            break
        prev = min(ins, key=lambda x: abs(math.remainder(cn._angle(x) - cn._angle(e), 2 * math.pi)))
        if abs(math.remainder(cn._angle(prev) - cn._angle(e), 2 * math.pi)) > math.radians(60):
            break
        e = prev
        done += e.getLength()
    return e


def junction_counts(net, groups, fwd, rev):
    """TomTom Junction Analytics on the network: (cross, corridor, span).
    cross     {edge id: {"jid", "vph", "split": {"fwd", "rev", "cross"}, "road", "split_source"}}: each measured cross-road
              approach, matched to the network edge at the end of TomTom's approach with the same heading, and assigned to
              the corridor junction that edge leads to. TomTom's junction areas overlap (j08's covers j09), so an edge seen
              by two areas keeps the larger volume, once. split: where its traffic goes (TomTom turn ratios, else thirds).
    corridor  {junction id: {"fwd"/"rev": {"edge", "vph", "road"}}}: the busiest corridor approach each way (volume check).
    Approaches on roads the network does not have (lanes, colony roads) are left out."""
    vol, span = tomtom_volumes()
    delay, _ = tomtom_volumes("delay_s")
    if not vol or not JA_CONFIG.exists():
        return {}, {}, None
    turns = tomtom_turns()
    fwd_ids, rev_ids = {e.getID() for e in fwd}, {e.getID() for e in rev}
    node_jid = {n.getID(): jid for jid, g in groups.items() for n in g}
    cross, corridor = {}, {}
    for j in json.loads(JA_CONFIG.read_text())["junctions"]:
        jid = j["corridor_id"]
        path = ROOT / f"data/tomtom/junction/corridor/{jid}_definition.json"
        if not path.exists():
            continue
        model = json.loads(path.read_text())["junctionModel"]
        exit_kind = {}
        for x in model["exits"]:
            c = x["segmentedGeometry"]["coordinates"][0]
            e = _match(net, c[0], c[1], at_start=True)
            kind = "fwd" if e and e.getID() in fwd_ids else "rev" if e and e.getID() in rev_ids else "cross"
            exit_kind.setdefault(x["name"], []).append(kind)
        exit_kind = {k: max(set(v), key=v.count) for k, v in exit_kind.items()}
        for a in model["approaches"]:
            vph = vol.get((jid, str(a["id"])), 0)
            c = a["segmentedGeometry"]["coordinates"][-1]
            e = _match(net, c[-2], c[-1]) if vph >= 30 else None
            if e is None:
                continue
            if e.getID() in fwd_ids or e.getID() in rev_ids:
                tag = "fwd" if e.getID() in fwd_ids else "rev"
                if vph > corridor.setdefault(jid, {}).get(tag, {}).get("vph", 0):
                    corridor[jid][tag] = {"edge": e.getID(), "vph": round(vph), "road": a["name"],
                                          "delay_s": round(delay.get((jid, str(a["id"])), 0), 1)}
                continue
            if not groups.get(jid):     # the corridor passes over this junction (j04): its cross roads never meet it
                continue
            if e.getFromNode().getID() in node_jid:      # TomTom's approach ends inside the junction: the road into it
                ins = [x for x in e.getFromNode().getIncoming() if x.getID() not in fwd_ids | rev_ids
                       and x.getFromNode().getID() not in node_jid and x.allows("passenger")]
                e = min(ins, key=lambda x: abs(math.remainder(cn._angle(x) - cn._angle(e), 2 * math.pi))) if ins else None
            at, entry = _leads_to(e, node_jid, fwd_ids | rev_ids) if e else (None, None)
            if at is None or entry.getID() in fwd_ids | rev_ids:
                continue
            probes = {}
            for name, w in turns.get((jid, a["name"]), {}).items():
                k = exit_kind.get(name, "cross")
                probes[k] = probes.get(k, 0.0) + w
            total = sum(probes.values())
            split = {k: probes.get(k, 0.0) / total for k in ("fwd", "rev", "cross")} if total >= MIN_TURN_PROBES else dict(ASSUMED_SPLIT)
            old = cross.get(e.getID())
            if old is None or vph > old["vph"]:
                cross[e.getID()] = {"jid": at, "vph": round(vph), "split": {k: round(v, 3) for k, v in split.items()}, "road": a["name"],
                                    "split_source": "estimated (TomTom turn ratios)" if total >= MIN_TURN_PROBES else "assumed"}
    return cross, corridor, span


def _after(path, i, metres):
    """Index of the first path edge at least `metres` past the end of path[i], skipping flyover/underpass edges and the
    edge landing from one (traffic joining at the junction cannot use them)."""
    k, done = i + 1, 0.0
    while k < len(path) - 1 and done < metres:
        done += path[k].getLength()
        k += 1
    grade = lambda e: e.getID().startswith(("flyover_", "underpass_"))  # noqa: E731
    while k < len(path) - 1 and (grade(path[k]) or grade(path[k - 1])):
        k += 1
    return k


def point_index(net, path, reverse=False):
    """{corridor point id: index of the path edge whose end is nearest it}; the trip's start point gets -1."""
    pts = cn.CORRIDOR["points"][::-1] if reverse else cn.CORRIDOR["points"]
    out = {}
    for p in pts:
        x, y = net.convertLonLat2XY(p["lon"], p["lat"])
        out[p["id"]] = min(range(len(path)), key=lambda i: math.dist(path[i].getToNode().getCoord()[:2], (x, y)))
    out[pts[0]["id"]], out[pts[-1]["id"]] = -1, len(path) - 1
    return out


def demand(net, base_groups, volume_scale=1.0, through=None, cross_scale=CROSS_SCALE, tomtom=None):
    """All traffic as flows [{"id", "route": [edge ids], "vph", "kind"}]: through traffic both ways along the corridor
    (fixed routes), and cross traffic at every junction (TomTom volumes where measured, else CROSS_VPH per approach)
    that crosses the corridor or joins it for JOIN_M metres. `base_groups` are the junction node ids of the unchanged
    network, so cross traffic still meets the ground junction under a flyover. Returns (flows, info)."""
    through = through or THROUGH_VPH
    fwd, rev = cn.route(net), cn.route(net, reverse=True)
    paths = {"fwd": fwd, "rev": rev}
    on_path = {e.getID() for e in fwd + rev}
    groups = {j: [net.getNode(n) for n in ids if net.hasNode(n)] for j, ids in base_groups.items()}
    node_jid = {n.getID(): jid for jid, g in groups.items() for n in g}
    # TomTom's numbers as frozen in calibration.json (so runs are reproducible and match the calibration), else live
    measured, corridor, span = (tomtom["cross"], tomtom["corridor"], tomtom["span"]) if tomtom else junction_counts(net, groups, fwd, rev)
    measured = {e: m for e, m in measured.items() if net.hasEdge(e)}
    # Lakdikapul (B): traffic disperses at the junction there; past the last wide piece of road only the probe cars drive
    # on (the route's last ~130 m squeeze 5 lanes into 2 at a give-way merge, which jammed the whole last leg)
    end = len(fwd) - 2
    while end > 0 and fwd[end].getLaneNumber() < 3 and sum(e.getLength() for e in fwd[end:]) < 800:
        end -= 1
    cut = {"fwd": fwd[end].getID() if fwd[end].getLaneNumber() >= 3 else fwd[-1].getID(), "rev": rev[-1].getID()}
    clip = lambda r, tag: r[:r.index(cut[tag]) + 1] if cut[tag] in r else r  # noqa: E731
    flows = [{"id": f"t{tag[0]}", "route": clip([e.getID() for e in p], tag), "vph": through[tag] * volume_scale, "kind": "through", "dir": tag}
             for tag, p in paths.items()]
    pos = {"fwd": point_index(net, fwd), "rev": point_index(net, rev, reverse=True)}
    approaches = {}
    for e_id, m in measured.items():
        approaches.setdefault(m["jid"], []).append((net.getEdge(e_id), m["vph"] * cross_scale, m["split"], "estimated", m["split_source"], m["road"]))
    summary = {}
    for jid, nodes in groups.items():
        ids = {n.getID() for n in nodes}
        if not ids:
            continue
        if jid not in approaches:
            ins = [e for n in nodes for e in n.getIncoming() if e.getID() not in on_path and e.getFromNode().getID() not in ids
                   and e.allows("passenger")]
            approaches[jid] = [(e, CROSS_VPH, dict(ASSUMED_SPLIT), "assumed", "assumed", e.getName()) for e in ins]
        outs = [e for n in nodes for e in n.getOutgoing() if e.getID() not in on_path and e.getToNode().getID() not in ids
                and e.allows("passenger")]
        joins = {}
        for tag, path in paths.items():
            i = pos[tag][jid]
            a, b = _after(path, i, 150), _after(path, i, JOIN_M)
            joins[tag] = (path[a], clip([x.getID() for x in path[a + 1:b + 1]], tag))
        rows = []
        for e, vph, split, label, split_source, road in approaches[jid]:
            start = _upstream(e, on_path | set(node_jid))
            dests = []
            for tag in ("fwd", "rev"):
                to, rest = joins[tag]
                p, _ = net.getShortestPath(start, to, vClass="passenger")
                if p and sum(x.getLength() for x in p) < 3000:
                    dests.append((tag, [x.getID() for x in p] + rest, split.get(tag, 0.0)))
            ok = []
            for o in outs:
                if o.getToNode() == e.getFromNode() or o.getID() == e.getID():
                    continue
                p, _ = net.getShortestPath(start, o, vClass="passenger")
                if p and sum(x.getLength() for x in p) < 2000:
                    ok.append(p)
            dests += [("cross", [x.getID() for x in p], split.get("cross", 0.0) / len(ok)) for p in ok]
            total = sum(s for _, _, s in dests)
            if not dests or total <= 0:
                continue
            for tag, edges, share in dests:
                v = vph * volume_scale * share / total
                if v >= 1:
                    flows.append({"id": f"x{jid[1:]}_{len(flows)}", "route": edges, "vph": v, "kind": "cross", "jid": jid, "dir": tag})
            used = {k: round(sum(s for t, _, s in dests if t == k) / total, 3) for k in ("fwd", "rev", "cross")}
            rows.append({"road": road, "edge": e.getID(), "enters_on": start.getID(), "vph": round(vph * volume_scale),
                         "label": label, "split": used, "split_source": split_source})
        summary[jid] = {"approaches": len(rows), "vph": sum(r["vph"] for r in rows),
                        "label": rows[0]["label"] if rows else "none", "roads": rows}
    return flows, {"cross": summary, "corridor": corridor, "tomtom_span": span, "paths": paths, "pos": pos, "cut": cut}


# ---------- sections ----------
def sections(net, info):
    """The corridor split into SECTIONS that run in parallel. Each covers its legs plus LEAD_IN_M of road before (so
    traffic reaches its first junction in realistic platoons and queues) and TAIL_M after; [{"k", "legs", "fwd": (a, b),
    "rev": (a, b) path index ranges, "junctions" (simulated), "owned" (reported here), "end" s, "lon": (lo, hi)}]."""
    pts = [p["id"] for p in cn.CORRIDOR["points"]]
    lon = {p["id"]: p["lon"] for p in cn.CORRIDOR["points"]}
    tt = {(a, b): t for a, b, _, t, _ in tomtom_legs()}
    out = []
    for k, (p1, p2) in enumerate(SECTIONS):
        i1, i2 = pts.index(p1), pts.index(p2)
        sec = {"k": k, "legs": list(range(i1, i2)), "points": pts[i1:i2 + 1], "junctions": [], "owned": [],
               "lon": (-999 if i1 == 0 else lon[p1] + 0.0015, 999 if i2 == len(pts) - 1 else lon[p2] + 0.0015)}
        for tag, a, b in (("fwd", p1, p2), ("rev", p2, p1)):
            path, pos = info["paths"][tag], info["pos"][tag]
            cum = [0.0]
            for e in path:
                cum.append(cum[-1] + e.getLength())          # cum[i + 1]: distance to the end of path[i]
            da, db = cum[pos[a] + 1], cum[pos[b] + 1]
            start = 0 if pos[a] < 0 else next(i for i in range(len(path)) if cum[i + 1] > da - LEAD_IN_M)
            while start > 0 and path[start].getLength() < 50:   # vehicles enter the section on a piece with room
                start -= 1
            end = len(path) - 1 if pos[b] == len(path) - 1 else next((i for i in range(len(path)) if cum[i + 1] >= db + TAIL_M), len(path) - 1)
            sec[tag] = (start, end)
        sec["junctions"] = [p for p in pts[i1:i2 + 1] if p.startswith("j")]
        sec["owned"] = [p for p in pts[i1 + 1:i2 + 1] if p.startswith("j")]       # A->B approach fully inside
        sec["owned_rev"] = [p for p in pts[i1:i2] if p.startswith("j")]          # B->A approach fully inside
        sec["end"] = int(WARMUP + PROBE_SPAN + max(900, 1.6 * sum(tt[(pts[i], pts[i + 1])] for i in sec["legs"])) + 300)
        out.append(sec)
    return out


def section_routes(net, sec, flows, info, out: Path):
    """Routes file of one section: every flow cut to the section (the part of its route inside it), fill flows so the
    section starts full, and its probe cars. Vehicle ids start with the section number (probes: probe_fwd_<k>...)."""
    paths, k, end = info["paths"], sec["k"], sec["end"]
    slices = {tag: paths[tag][sec[tag][0]:sec[tag][1] + 1] for tag in ("fwd", "rev")}
    corridor = {e.getID() for p in paths.values() for e in p}
    inside = {e.getID() for s in slices.values() for e in s}
    inside |= {e for f in flows if f.get("jid") in sec["junctions"] for e in f["route"] if e not in corridor}
    stop = {"fwd": WARMUP + PROBE_SPAN + 60, "rev": end - 300}    # A->B traffic behind the last probe cannot affect it
    lines = ['<routes>', VTYPES.replace('<vType ', f'<vType sigma="{SIGMA}" '),
             f'    <vType id="probe" sigma="{SIGMA}" vClass="passenger" length="4.3" minGap="1.0" tau="0.8" maxSpeed="16.7" accel="2.6" decel="4.5" '
             'speedFactor="1.0" color="1,1,1"><param key="has.vehroute.device" value="true"/></vType>',
             f'    <vTypeDistribution id="mix" vTypes="{" ".join(MIX)}" probabilities="{" ".join(str(v) for v in MIX.values())}"/>']
    entering = {"fwd": 0.0, "rev": 0.0}
    body = []
    for f in flows:
        route, run = f["route"], []
        for e in route:                     # the first stretch of the route inside the section
            if e in inside:
                run.append(e)
            elif run:
                break
        if not run or (f["kind"] == "cross" and f["jid"] not in sec["junctions"] and len(run) < 2):
            continue
        for tag in ("fwd", "rev"):
            if run[0] == slices[tag][0].getID():
                entering[tag] += f["vph"]
        tag = f.get("dir", "fwd")
        stop_at = stop.get(tag, end) if f["kind"] == "through" or (f["kind"] == "cross" and f["jid"] not in sec["junctions"]) else end
        body.append(f'    <flow id="{k}{f["id"]}" type="mix" begin="0" end="{stop_at}" vehsPerHour="{f["vph"]:.0f}" '
                    f'departLane="best" departSpeed="max"><route edges="{" ".join(run)}"/></flow>')
    for tag, s in slices.items():
        # the section starts full: the traffic entering it also enters every FILL_STEP_M along the way until the
        # vehicles from the previous entry point get there (at FILL_SPEED), so probes meet steady traffic early on
        cum, last = 0.0, 0.0
        for i, e in enumerate(s[:-1]):
            cum += e.getLength()
            if cum - last >= FILL_STEP_M and cum < sum(x.getLength() for x in s) - 800 and s[i + 1].getLength() >= 50:   # room to enter
                body.append(f'    <flow id="{k}f{tag[0]}{i + 1}" type="mix" begin="0" end="{(cum - last) / FILL_SPEED:.0f}" '
                            f'vehsPerHour="{entering[tag]:.0f}" departLane="best" departSpeed="max">'
                            f'<route edges="{" ".join(_clip([x.getID() for x in s[i + 1:]], info["cut"][tag]))}"/></flow>')
                last = cum
        body.append(f'    <flow id="probe_{tag}_{k}" type="probe" begin="{WARMUP}" end="{WARMUP + PROBE_SPAN}" period="{PROBE_EVERY}" '
                    f'departLane="best" departSpeed="max"><route edges="{" ".join(x.getID() for x in s)}"/></flow>')
    out.write_text("\n".join(lines + body + ['</routes>']))
    return out


def _clip(route, last):
    """The route up to and including edge `last` (all of it when `last` is not on it)."""
    return route[:route.index(last) + 1] if last in route else route


def detectors(net, base_groups, sec, out: Path, count_edges=()):
    """A queue detector on the last 150 m of every lane approaching the section's junctions (whole run), and vehicle
    counts on `count_edges` (the corridor approaches TomTom measures) while the probes leave."""
    lines = ["<additional>"]
    for jid in sec["junctions"]:
        node_ids = base_groups.get(jid, [])
        nodes = [net.getNode(n) for n in node_ids if net.hasNode(n)]
        for e in {e for n in nodes for e in n.getIncoming() if e.getFromNode().getID() not in node_ids}:
            for lane in e.getLanes():
                L = lane.getLength()
                if L > 5:
                    lines.append(f'    <laneAreaDetector id="{jid}|{lane.getID()}" lane="{lane.getID()}" pos="{max(0, L - 150):.1f}" '
                                 f'endPos="{L - 0.5:.1f}" period="{sec["end"]}" file="e2_{sec["k"]}.xml"/>')
    edges = sorted({e for e in count_edges if net.hasEdge(e)})
    if edges:
        lines.append(f'    <edgeData id="counts" file="counts_{sec["k"]}.xml" begin="{WARMUP}" end="{WARMUP + PROBE_SPAN}" '
                     f'edges="{" ".join(edges)}"/>')
    lines.append("</additional>")
    out.write_text("\n".join(lines))
    return out


# ---------- run and measure ----------
def simulate(net, net_path: Path, sec, outdir: Path, frames=True, seed=SEED):
    """Run one section in SUMO. With `frames`, vehicle positions in the FRAMES window (inside the section's own stretch)
    go to frames_<k>.jsonl through TraCI (SUMO's FCD output cannot stop at the window's end)."""
    k = sec["k"]
    cmd = [sumolib.checkBinary("sumo"), "-n", str(net_path), "-r", str(outdir / f"routes_{k}.xml"), "-a", str(outdir / f"det_{k}.xml"),
           "--begin", "0", "--end", str(sec["end"]), "--seed", str(seed), "--step-length", str(STEP), "--no-step-log",
           "--log", str(outdir / f"sumo_{k}.log"), "--time-to-teleport", str(TELEPORT_S), "--ignore-route-errors",
           "--ignore-junction-blocker", str(JUNCTION_BLOCKER_S),
           "--device.vehroute.probability", "0", "--vehroute-output", str(outdir / f"probes_{k}.xml"),
           "--vehroute-output.exit-times", "--statistic-output", str(outdir / f"stats_{k}.xml")]
    if not frames:
        subprocess.run(cmd, cwd=outdir, check=True, capture_output=True)
        return None
    import traci
    import traci.constants as tc
    label = f"cr_{outdir.name}_{k}_{uuid.uuid4().hex[:6]}"
    traci.start(cmd, label=label, stdout=subprocess.DEVNULL)
    conn, path = traci.getConnection(label), outdir / f"frames_{k}.jsonl"
    (bx0, by0), (bx1, by1) = net.getBBoxXY()
    centre = min(net.getNodes(), key=lambda n: math.dist(n.getCoord()[:2], ((bx0 + bx1) / 2, (by0 + by1) / 2))).getID()
    lo, hi = sec["lon"]
    try:
        conn.simulationStep(float(FRAMES[0] - FRAMES[2]))
        conn.junction.subscribeContext(centre, tc.CMD_GET_VEHICLE_VARIABLE, math.dist((bx0, by0), (bx1, by1)),
                                       [tc.VAR_POSITION3D, tc.VAR_ANGLE, tc.VAR_SPEED, tc.VAR_TYPE])
        with path.open("w") as f:
            t = FRAMES[0]
            while t <= FRAMES[1]:
                conn.simulationStep(float(t))
                vehicles = []
                for vid, v in (conn.junction.getContextSubscriptionResults(centre) or {}).items():
                    x, y, z = v[tc.VAR_POSITION3D]
                    lon, lat = net.convertXY2LonLat(x, y)
                    if lo <= lon < hi:
                        vt = v[tc.VAR_TYPE]
                        vehicles.append({"id": vid, "type": vt if vt in C1_TYPES else "car", "lon": round(lon, 5), "lat": round(lat, 5),
                                         "z": round(z, 1) if abs(z) >= 0.05 else 0, "angle": round(v[tc.VAR_ANGLE]), "speed": round(v[tc.VAR_SPEED], 1)})
                f.write(json.dumps({"t": t, "vehicles": vehicles}, separators=(",", ":")) + "\n")
                t += FRAMES[2]
        conn.junction.unsubscribeContext(centre, tc.CMD_GET_VEHICLE_VARIABLE, 0)
        conn.simulationStep(float(sec["end"]))
    finally:
        conn.close()
    return path


def merge_frames(paths, out: Path):
    """One C1 frame per time step with the vehicles of every section."""
    files = [p.open() for p in paths]
    with out.open("w") as f:
        for lines in zip(*files):
            frames = [json.loads(l) for l in lines]
            f.write(json.dumps({"t": frames[0]["t"], "vehicles": [v for fr in frames for v in fr["vehicles"]]}, separators=(",", ":")) + "\n")
    for fh, p in zip(files, paths):
        fh.close(); p.unlink()
    return out


def probe_legs(sec, info, outdir: Path):
    """The section's legs (A->B direction): {leg index: (distance m, mean time s)} over its probe cars that got through."""
    path, pos = info["paths"]["fwd"], info["pos"]["fwd"]
    a, _ = sec["fwd"]
    per_probe = []
    for v in ET.parse(outdir / f"probes_{sec['k']}.xml").getroot().iter("vehicle"):
        if not v.get("id").startswith("probe_fwd") or v.get("arrival") is None:
            continue
        exits = [float(t) for t in v.find("route").get("exitTimes").split()]
        t = [float(v.get("depart")) if pos[p] < 0 else exits[pos[p] - a] for p in sec["points"]]
        per_probe.append([y - x for x, y in zip(t, t[1:])])
        per_probe[-1].append(v.get("id").rsplit(".", 1)[1])     # probe number: same departure time in every section
    if not per_probe:
        raise RuntimeError(f"no probe car got through section {sec['points'][0]}-{sec['points'][-1]}; the network is gridlocked there")
    out = {}
    for n, leg in enumerate(sec["legs"]):
        p1, p2 = sec["points"][n], sec["points"][n + 1]
        dist = sum(e.getLength() for e in path[pos[p1] + 1:pos[p2] + 1])
        times = [p[n] for p in per_probe]
        out[leg] = (dist, sum(times) / len(times), statistics.pstdev(times))
    return out, len(per_probe), {p[-1]: sum(p[:-1]) for p in per_probe}


def junction_stats(outdir: Path, secs, info):
    """Mean time lost and longest queue on each junction's approaches, and vehicles that entered them. Each approach is
    read from the section where it is simulated in full (not where its traffic is just entering the section)."""
    rev = {e.getID() for e in info["paths"]["rev"]}
    acc = {}
    for sec in secs:
        f = outdir / f"e2_{sec['k']}.xml"
        if not f.exists():
            continue
        for d in ET.parse(f).getroot().iter("interval"):
            jid, lane = d.get("id").split("|", 1)
            if jid not in (sec["owned_rev"] if lane.rsplit("_", 1)[0] in rev else sec["owned"]):
                continue
            a = acc.setdefault(jid, [0, 0.0, 0.0])
            n = int(d.get("nVehEntered", 0))
            a[0] += n
            a[1] += n * max(0.0, float(d.get("meanTimeLoss", 0)))
            a[2] = max(a[2], float(d.get("maxJamLengthInMeters", 0)))
    out = []
    for p in cn.CORRIDOR["points"]:
        if p["kind"] != "junction":
            continue
        n, loss, q = acc.get(p["id"], (0, 0, 0))
        out.append({"id": p["id"], "name": p["name"], "lat": p["lat"], "lon": p["lon"],
                    "avg_delay_s": round(loss / n, 1) if n else 0.0, "max_queue_m": round(q), "vehicles": n})
    return out


def approach_edges(info, base_groups):
    """{(junction id, "fwd"/"rev"): corridor edges from TomTom's measured approach up to the junction}."""
    out = {}
    for jid, dirs in info["corridor"].items():
        ids = set(base_groups.get(jid, []))
        if not ids:       # the corridor passes over this junction (j04): no approach delay of its own to compare
            continue
        for tag, m in dirs.items():
            path = [e.getID() for e in info["paths"][tag]]
            if m["edge"] not in path:
                continue
            i, run, done = path.index(m["edge"]), [], 0.0
            for e in info["paths"][tag][i:i + 15]:
                run.append(e.getID())
                done += e.getLength()
                if e.getToNode().getID() in ids:
                    if done < 1500:   # else TomTom's approach does not lead into this junction on the corridor (overlapping areas)
                        out[(jid, tag)] = run
                    break
    return out


def corridor_volumes(outdir: Path, secs, measured, approaches=None):
    """Simulated vs TomTom on the corridor approaches TomTom measures, while the probes leave: veh/h, and the delay
    (time lost per vehicle from TomTom's approach start up to the junction; TomTom: evening mean, estimated)."""
    rows = []
    for sec in secs:
        f = outdir / f"counts_{sec['k']}.xml"
        data = {e.get("id"): e for e in ET.parse(f).getroot().iter("edge")} if f.exists() else {}
        for jid in sec["junctions"]:
            for tag, m in sorted(measured.get(jid, {}).items()):
                if jid not in sec["owned" if tag == "fwd" else "owned_rev"]:
                    continue      # this direction's approach is read in the section that simulates it in full
                e = data.get(m["edge"])
                sim = (float(e.get("entered", 0)) + float(e.get("departed", 0))) * 3600 / PROBE_SPAN if e is not None else None
                lost = [float(data[x].get("timeLoss", 0)) / max(1.0, float(data[x].get("entered", 0)) + float(data[x].get("departed", 0)))
                        for x in (approaches or {}).get((jid, tag), []) if x in data]
                rows.append({"junction_id": jid, "direction": "A->B" if tag == "fwd" else "B->A", "road": m["road"], "edge": m["edge"],
                             "tomtom_vph": m["vph"], "sim_vph": round(sim) if sim is not None else None,
                             "tomtom_delay_s": m.get("delay_s"), "sim_delay_s": round(sum(lost), 1) if lost else None,
                             "label": "estimated"})
    return rows


def write_roads(net, outdir: Path):
    """GeoJSON of the corridor's main roads (for the map)."""
    feats = []
    for e in net.getEdges():
        if e.getFunction() == "internal" or not e.allows("passenger"):
            continue
        shape = e.getShape3D()   # z: flyovers and underpasses built by sim/templates/corridor.py are at +-6 m
        lifted = any(abs(z) > 0.5 for *_, z in shape)
        coords = [[round(v, 6) for v in net.convertXY2LonLat(x, y)] + ([round(z, 1)] if lifted else []) for x, y, z in shape]
        props = {"id": e.getID(), "lanes": e.getLaneNumber(), "name": e.getName()}
        kind = next((k for k in ("flyover", "underpass") if e.getID().startswith(k + "_")), None)
        if kind:   # the template's structure edges are named <kind>_<junction>_<fwd|rev>
            props.update(structure=kind, junction_id=e.getID().split("_")[1], flyover=kind == "flyover")
        feats.append({"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": coords}})
    path = outdir / "roads.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    return path


def calibration():
    """Calibrated knobs (calibration.json), or the assumed defaults before calibration."""
    c = json.loads(CALIBRATION.read_text()) if CALIBRATION.exists() else {}
    return {"cap_kmh": c.get("cap_kmh", [MAX_KMH] * (len(cn.CORRIDOR["points"]) - 1)),
            "through_vph": c.get("through_vph") if isinstance(c.get("through_vph"), dict) else dict(THROUGH_VPH),
            "cross_scale": c.get("cross_scale", CROSS_SCALE), "green_share": c.get("green_share", {}), "tomtom": c.get("tomtom"),
            "run_to_run_sd_s": c.get("run_to_run_sd_s", 0.0),
            "calibrated": bool(c)}


def run(interventions=(), volume_scale=1.0, run_id=None, frames=True, caps=None, label="July 2026 average, 6 am-11 pm", through=None,
        cross_scale=None, shares=None, seed=SEED, tomtom=None):
    """Simulate the corridor with `interventions` (C5 shape); return the C5 corridor result. `caps` (km/h per leg),
    `through` ({"fwd", "rev"} veh/h), `cross_scale` and `shares` ({junction id: corridor green share}) override the
    calibrated values (calibrate() uses them)."""
    run_id = run_id or "rc_" + uuid.uuid4().hex[:8]
    outdir = OUT / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cal = calibration()
    through = through or cal["through_vph"]
    base = sumolib.net.readNet(str(NET))
    base_groups = {j: [n.getID() for n in g] for j, g in cn.junction_groups(base).items() if g}
    net_path = calibrated_net(outdir / "corridor.net.xml", caps if caps is not None else cal["cap_kmh"],
                              shares if shares is not None else cal["green_share"])
    warnings = []
    variant = outdir / "variant.net.xml"
    if interventions:
        import corridor as templates   # sim/templates/corridor.py (interventions)
        warnings += templates.apply(net_path, variant, list(interventions))
    else:   # the baseline goes through the same netconvert rebuild as every variant, so they differ only by the change
        cn.rebuild(net_path, variant, lambda prefix: None)
    net_path = variant
    net = sumolib.net.readNet(str(net_path))
    flows, info = demand(net, base_groups, volume_scale, through, cross_scale if cross_scale is not None else cal["cross_scale"],
                         tomtom or cal["tomtom"])
    secs = sections(net, info)
    approaches = approach_edges(info, base_groups)
    count_edges = [m["edge"] for d in info["corridor"].values() for m in d.values()] + [e for v in approaches.values() for e in v]
    for sec in secs:
        section_routes(net, sec, flows, info, outdir / f"routes_{sec['k']}.xml")
        detectors(net, base_groups, sec, outdir / f"det_{sec['k']}.xml", count_edges)
    with ThreadPoolExecutor(min(len(secs), PARALLEL)) as pool:
        frame_files = list(pool.map(lambda s: simulate(net, net_path, s, outdir, frames, seed), secs))
    frames_path = merge_frames(frame_files, outdir / "frames.jsonl") if frames else None
    legs, n_probes, trips = {}, [], {}
    for sec in secs:
        got, n, per = probe_legs(sec, info, outdir)
        legs.update(got); n_probes.append(n)
        for i, t in per.items():
            trips.setdefault(i, []).append(t)
    trips = [sum(t) for t in trips.values() if len(t) == len(secs)]    # whole trips: probe i's legs in every section
    sd = statistics.pstdev(trips) if len(trips) > 1 else None
    tt = tomtom_legs()
    pts = cn.CORRIDOR["points"]
    out_legs = []
    for k, (_, _, _, _, tt_kmh) in enumerate(tt):
        dist, secs_, leg_sd = legs[k]
        out_legs.append({"from_id": pts[k]["id"], "to_id": pts[k + 1]["id"], "from_name": pts[k]["name"], "to_name": pts[k + 1]["name"],
                         "distance_m": round(dist), "time_s": round(secs_), "speed_kmh": round(dist / secs_ * 3.6, 1) if secs_ else None,
                         # TomTom's measured speed on this leg, over the simulated leg's length
                         "tomtom_time_s": round(dist / (tt_kmh / 3.6)),
                         "time_s_sd": round(leg_sd, 1)})       # spread between the probe cars
    teleports = loaded = waiting = 0
    for sec in secs:
        stats = ET.parse(outdir / f"stats_{sec['k']}.xml").getroot()
        teleports += int(stats.find("teleports").get("total"))
        loaded += int(stats.find("vehicles").get("loaded")); waiting += int(stats.find("vehicles").get("waiting"))
    if teleports > 0.01 * loaded:
        warnings.append(f"{teleports} vehicles were stuck for 5 minutes and skipped ahead (gridlock somewhere on the network)")
    if waiting > 0.02 * loaded:
        warnings.append(f"{waiting} vehicles could not enter the network by the end (queues back up beyond the modelled roads)")
    if min(n_probes) < PROBE_SPAN // PROBE_EVERY:
        warnings.append(f"in some sections only {min(n_probes)} of {PROBE_SPAN // PROBE_EVERY} probe cars got through in time")
    kinds = {i["kind"] for i in interventions}
    cross = info["cross"]
    measured = any(v["label"] == "estimated" for v in cross.values())
    result = {
        "run_id": run_id, "variant_id": "baseline" if not interventions else "+".join(f"{i['kind']}_{i['junction_id']}" for i in interventions),
        "corridor_id": CORRIDOR_ID,
        "time": {"window": "2026-07", "minutes": PROBE_SPAN // 60, "label": label},
        "interventions": list(interventions),
        "journey": {"total_s": sum(l["time_s"] for l in out_legs), "distance_m": sum(l["distance_m"] for l in out_legs),
                    "tomtom_total_s": sum(l["tomtom_time_s"] for l in out_legs), "legs": out_legs,
                    # noise: spread of whole-trip times between probe cars, and the uncertainty of the mean (total_s)
                    "total_s_sd": round(sd, 1) if sd is not None else None,
                    # uncertainty of total_s: the probes' spread in this run and the run-to-run spread (other seeds,
                    # measured at calibration) combined. Variant vs baseline (same seed and traffic): use
                    # total_s_se_probes of both runs (see the module docstring)
                    "total_s_se": round(math.hypot(sd / math.sqrt(len(trips)), cal["run_to_run_sd_s"]), 1) if sd is not None else None,
                    "total_s_se_probes": round(sd / math.sqrt(len(trips)), 1) if sd is not None else None,
                    "run_to_run_sd_s": cal["run_to_run_sd_s"],
                    "probe_trips": len(trips)},
        "junctions": junction_stats(outdir, secs, info),
        "warnings": warnings,
        "inputs": {"counts_source": "estimated" if measured else "assumed", "label": "estimated" if measured else "assumed",
                   "volume_scale": volume_scale, "cross_traffic": cross,
                   "through_vph": round(through["fwd"] * volume_scale),
                   "through_vph_by_direction": {"A->B": round(through["fwd"] * volume_scale), "B->A": round(through["rev"] * volume_scale)},
                   "cross_vph_per_approach": round(CROSS_VPH * volume_scale),
                   "corridor_volumes": corridor_volumes(outdir, secs, info["corridor"], approaches),
                   "sources": sources_note(cal, info),
                   "calibrated_to": f"TomTom Traffic Stats job {TOMTOM_JOB}, July 2026 06:00-23:00, leg speeds",
                   "speeds_source": "counted (TomTom probe data)", "probes_arrived": min(n_probes), "teleports": teleports,
                   "vehicles_loaded": loaded, "vehicles_not_inserted": waiting,
                   "sections": [{"from": s["points"][0], "to": s["points"][-1], "sim_seconds": s["end"], "probes": n}
                                for s, n in zip(secs, n_probes)],
                   "sim_seconds": max(s["end"] for s in secs), "wall_seconds": round(time.time() - t0, 1), "templates": sorted(kinds)},
        "frames_path": str(frames_path) if frames_path else None,
        "roads_path": str(write_roads(net, outdir)),
    }
    (outdir / "result.json").write_text(json.dumps(result, indent=1))
    return result


def sources_note(cal, sources):
    """What the run's inputs are and how sure we are of each: measured (counted), estimated, assumed or calibrated."""
    span = sources.get("tomtom_span")
    return [
        {"input": "leg travel times (calibration target)", "label": "counted",
         "source": f"TomTom Traffic Stats job {TOMTOM_JOB}: probe vehicles, July 2026 every day 06:00-23:00"},
        {"input": "cross-road volumes at " + (", ".join(sorted(j for j, v in sources["cross"].items() if v["label"] == "estimated")) or "no junction"),
         "label": "estimated", "source": f"TomTom Junction Analytics (model estimates from probe data), mean over {span or 'no data yet'}"},
        {"input": "where cross traffic goes (turn shares)", "label": "estimated",
         "source": "TomTom Junction Analytics turn ratios where collected; elsewhere a third each way (assumed)"},
        {"input": "cross-road volumes at the other junctions", "label": "assumed", "source": f"{CROSS_VPH} veh/h per approach"},
        {"input": "end-to-end corridor volume", "label": "calibrated" if cal["calibrated"] else "assumed",
         "source": "set so the corridor approaches at the TomTom junctions carry TomTom's volume (inputs.corridor_volumes)"},
        {"input": "speed cap per leg (side friction: bus stops, parking, pedestrians, autos)", "label": "calibrated" if cal["calibrated"] else "assumed",
         "source": "set so the probe cars' leg times match TomTom's"},
        {"input": "signal plans", "label": "assumed", "source": f"{cn.SIGNAL_CYCLE_S} s cycle, a corridor stage and a cross-road stage, "
                                                                 f"corridor gets {cn.CORRIDOR_GREEN_SHARE:.0%} of the green (corridor_net.signal_plans)"},
        {"input": "corridor green share where calibrated", "label": "calibrated" if cal["green_share"] else "assumed",
         "source": ", ".join(f"{j} {v:.0%}" for j, v in sorted(cal["green_share"].items())) or "none"},
        {"input": "vehicle mix", "label": "assumed", "source": ", ".join(f"{k} {v:.0%}" for k, v in MIX.items())},
        {"input": "joining traffic", "label": "assumed", "source": f"drives {JOIN_M / 1000:.0f} km along the corridor, then turns off"},
        {"input": "junction delay on the corridor's approaches (calibration target)", "label": "estimated",
         "source": f"TomTom Junction Analytics, mean over {span or 'no data yet'} (evening); capped at each leg's all-day time "
                   f"above {FREE_KMH} km/h free flow (inputs.corridor_volumes: tomtom_delay_s vs sim_delay_s)"},
        {"input": "traffic at Lakdikapul (B)", "label": "assumed",
         "source": "disperses before the last ~130 m (a 5-into-2-lane give-way merge); only probe cars drive on"},
    ]


# ---------- calibration ----------
def junction_delays(res, tt):
    """{junction id: (simulated, target delay s)} at the junctions where TomTom measures the corridor's approaches:
    means over both directions. Target: TomTom's delay (evening mean, estimated), but at most the time TomTom's leg
    into the junction takes above free flow (FREE_KMH), so the all-day leg times stay reachable."""
    pts = [p["id"] for p in cn.CORRIDOR["points"]]
    rows = {}
    for r in res["inputs"]["corridor_volumes"]:
        if r.get("sim_delay_s") is not None and r.get("tomtom_delay_s") is not None:
            rows.setdefault(r["junction_id"], []).append((r["sim_delay_s"], r["tomtom_delay_s"]))
    out = {}
    for jid, pairs in rows.items():
        k = pts.index(jid) - 1                                     # the leg ending at the junction
        excess = max(10.0, tt[k][3] - tt[k][2] / (FREE_KMH / 3.6))
        out[jid] = (statistics.mean(a for a, _ in pairs), min(statistics.mean(b for _, b in pairs), excess))
    return out


def calibrate(rounds=8, fresh=False, through=None, cross_scale=None):
    """Fit the calibrated knobs to TomTom and write calibration.json (see the module docstring). Each round runs the
    baseline, then per leg: too fast -> lower its speed cap; too slow -> raise the cap, and once the cap is at MAX_KMH
    (the time is lost at the junction, not on the road) give the corridor more green at the junction ending the leg.
    Traffic is lowered 10% when the network does not cope (vehicles stuck or unable to enter) or a leg is still too slow
    with the corridor's green at its limit, but never below MIN_DEMAND of the starting volumes. `through` and
    `cross_scale` set the starting volumes (default: calibration.json, else the assumed defaults). Keeps the round
    closest to TomTom."""
    tt = tomtom_legs()
    pts = [p["id"] for p in cn.CORRIDOR["points"]]
    cal = calibration()
    caps = list(cal["cap_kmh"]) if cal["calibrated"] and not fresh else [min(MAX_KMH, 2.0 * kmh) for *_, kmh in tt]
    shares = {} if fresh else dict(cal["green_share"])
    through, cross_scale = dict(through or cal["through_vph"]), cross_scale or cal["cross_scale"]
    floor = {"through": {d: v * MIN_DEMAND for d, v in through.items()}, "cross": cross_scale * MIN_DEMAND}
    base = sumolib.net.readNet(str(NET))
    groups = cn.junction_groups(base)
    signals = {j for j, g in groups.items() if g}
    cross, corridor, span = junction_counts(base, groups, cn.route(base), cn.route(base, reverse=True))   # live TomTom data
    tomtom = {"span": span, "cross": cross, "corridor": corridor,
              "note": "TomTom Junction Analytics means used by every run (frozen at calibration; refreshed by calibrate())"}
    best = None
    for r in range(rounds):
        res = run(caps=caps, shares=shares, through=through, cross_scale=cross_scale, frames=False, run_id=f"calib_{r}", tomtom=tomtom)
        shutil.rmtree(OUT / f"calib_{r}", ignore_errors=True)
        legs, j = res["journey"]["legs"], res["journey"]
        ratios = [l["time_s"] / l["tomtom_time_s"] for l in legs]
        score = max(abs(x - 1) for x in ratios) + 2 * abs(j["total_s"] / j["tomtom_total_s"] - 1)
        print(f"round {r}: sim {j['total_s'] / 60:.1f} min vs TomTom {j['tomtom_total_s'] / 60:.1f} min | leg ratios "
              f"{[round(x, 2) for x in ratios]} | shares {shares} | through {through} cross {cross_scale} | delays { {jid: (round(a), round(b)) for jid, (a, b) in junction_delays(res, tt).items()} } | {res['inputs']['wall_seconds']} s", flush=True)
        score += 0.25 * sum(abs(d - t) / max(t, 10) for d, t in junction_delays(res, tt).values()) / max(1, len(junction_delays(res, tt)))
        if best is None or score < best[0]:
            best = (score, list(caps), dict(shares), res, dict(through), cross_scale)
        if all(abs(x - 1) < 0.07 for x in ratios) and abs(j["total_s"] / j["tomtom_total_s"] - 1) < 0.03:
            break
        overloaded, touched = False, set()
        for k, x in enumerate(ratios):
            new = max(8.0, min(MAX_KMH, caps[k] * x ** 0.8))
            end = pts[k + 1]
            if x > 1.07 and caps[k] >= MAX_KMH - 0.1 and end in signals:
                if shares.get(end, cn.CORRIDOR_GREEN_SHARE) >= MAX_SHARE - 1e-6:
                    overloaded = True       # still too slow with the corridor's green at its limit: too much traffic
                shares[end] = round(min(MAX_SHARE, shares.get(end, cn.CORRIDOR_GREEN_SHARE) + 0.1), 2)
                touched.add(end)
            caps[k] = round(new, 1)
        # junction delay: where TomTom measures the corridor's approaches, the corridor's green moves the simulated
        # delay towards target_delay() (TomTom's, at most the leg's time over free flow); the caps then refit the legs
        for jid, (simd, target) in junction_delays(res, tt).items():
            if jid in touched or jid not in signals:
                continue
            share = shares.get(jid, cn.CORRIDOR_GREEN_SHARE)
            if simd < 0.75 * target and ratios[pts.index(jid) - 1] < 1.07:
                shares[jid] = round(max(STABLE_SHARE.get(jid, MIN_SHARE), share - 0.05), 2)
            elif simd > 1.33 * target + 5:
                shares[jid] = round(min(MAX_SHARE, share + 0.05), 2)
        inp = res["inputs"]
        if inp["teleports"] > 0.01 * inp["vehicles_loaded"] or inp["vehicles_not_inserted"] > 0.02 * inp["vehicles_loaded"]:
            overloaded = True
        if overloaded and cross_scale * 0.9 >= floor["cross"] - 1e-6:
            through = {d: round(v * 0.9) for d, v in through.items()}
            cross_scale = round(cross_scale * 0.9, 3)
    _, caps, shares, res, through, cross_scale = best
    # run-to-run noise: the calibrated baseline with other seeds (everything else equal)
    others = [run(caps=caps, shares=shares, through=through, cross_scale=cross_scale, frames=False, run_id=f"calib_seed{sd_}",
                  tomtom=tomtom, seed=sd_) for sd_ in (SEED + 1, SEED + 2, SEED + 3)]
    for sd_ in (SEED + 1, SEED + 2, SEED + 3):
        shutil.rmtree(OUT / f"calib_seed{sd_}", ignore_errors=True)
    totals = [res["journey"]["total_s"]] + [o["journey"]["total_s"] for o in others]
    print(f"seeds {SEED}..{SEED + 3}: trip {[round(t / 60, 1) for t in totals]} min", flush=True)
    j = res["journey"]
    CALIBRATION.write_text(json.dumps({
        "target": f"TomTom Traffic Stats job {TOMTOM_JOB}: Lingampally -> Lakdikapul, July 2026 every day 06:00-23:00",
        "cap_kmh": caps, "green_share": shares, "through_vph": through, "cross_scale": cross_scale, "tomtom": tomtom,
        "knobs": {
            "cap_kmh": "calibrated: speed cap per leg (A->j01 ... j11->B) standing in for side friction (bus stops, parking, "
                       "pedestrians, autos), both directions",
            "green_share": f"calibrated: corridor share of the green time at junctions where the leg was still too slow at "
                           f"{MAX_KMH} km/h; elsewhere {cn.CORRIDOR_GREEN_SHARE} (assumed)",
            "through_vph": "calibrated: end-to-end corridor traffic per direction; starts at THROUGH_VPH (assumed) and is "
                           "lowered 10% at a time while a leg stays too slow with the corridor's green at its limit",
            "cross_scale": "calibrated as through_vph: share of TomTom Junction Analytics' evening cross-road volumes used for the all-day "
                           "average"},
        "result": {"sim_total_s": j["total_s"], "tomtom_total_s": j["tomtom_total_s"],
                   "legs": [{"leg": f"{l['from_id']}->{l['to_id']}", "sim_s": l["time_s"], "tomtom_s": l["tomtom_time_s"],
                             "ratio": round(l["time_s"] / l["tomtom_time_s"], 3)} for l in j["legs"]],
                   "junction_delays": {jid: {"sim_s": round(a, 1), "target_s": round(b, 1)} for jid, (a, b) in junction_delays(res, tt).items()},
                   "total_s_se": j.get("total_s_se"),
                   "corridor_volumes": res["inputs"]["corridor_volumes"], "teleports": res["inputs"]["teleports"],
                   "vehicles_loaded": res["inputs"]["vehicles_loaded"], "vehicles_not_inserted": res["inputs"]["vehicles_not_inserted"],
                   "probes_arrived": res["inputs"]["probes_arrived"], "wall_seconds": res["inputs"]["wall_seconds"],
                   "inputs": res["inputs"]["sources"]},
        "run_to_run_sd_s": round(statistics.stdev(totals), 1), "seed_totals_s": totals,
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1))
    return caps, shares


if __name__ == "__main__":
    if sys.argv[1:2] == ["calibrate"]:
        calibrate()
    elif sys.argv[1:2] == ["run"]:
        ivs = [{"junction_id": a.split(":")[0], "kind": a.split(":")[1], "params": {}} for a in sys.argv[2:]]
        res = run(ivs, frames=False)
        j = res["journey"]
        print(f"{res['variant_id']}: {j['total_s'] / 60:.1f} min (TomTom {j['tomtom_total_s'] / 60:.1f}), {j['distance_m'] / 1000:.1f} km, "
              f"{res['inputs']['wall_seconds']} s wall, teleports {res['inputs']['teleports']}")
        for l in j["legs"]:
            print(f"  {l['from_id']:>14} -> {l['to_id']:<13} {l['distance_m']:>5} m  {l['time_s'] / 60:5.1f} min  (TomTom {l['tomtom_time_s'] / 60:5.1f})")
        for x in res["junctions"]:
            print(f"  {x['id']} {x['name'][:24]:24} delay {x['avg_delay_s']:6.1f} s  queue {x['max_queue_m']:4} m  veh {x['vehicles']}")
