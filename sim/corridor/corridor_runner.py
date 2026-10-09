"""Corridor simulation, Lingampally -> Lakdikapul: interventions in, C5 corridor result out.

Traffic (assumed volumes, then calibrated): through traffic both ways, cross traffic at every signalised junction, and
probe cars A -> B that record when they pass each junction, which gives the trip time split by leg.

`calibrate()` tunes each leg's road speed until the probes' leg times match TomTom's July 2026 average. That speed
stands in for side friction SUMO does not model (buses stopping, parked vehicles, pedestrians, merging autos). The
baseline therefore reproduces the measured trip, and interventions change it through the junction delays.

    python sim/corridor/corridor_runner.py calibrate          # writes sim/corridor/calibration.json
    python sim/corridor/corridor_runner.py run [j07:flyover]  # prints the C5 result summary
"""
import csv, gzip, json, math, os, shutil, subprocess, sys, time, uuid, xml.etree.ElementTree as ET
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
OUT = Path(os.environ.get("CR_SIM_OUT", ROOT / "sim/out")) / "corridor"
CORRIDOR_ID = "lingampally_lakdikapul"
TOMTOM_JOB = "10051304"           # July 2026, every day 06:00-23:00
THROUGH_VPH = 2500                # per direction (assumed)
CROSS_VPH = 450                   # per cross-road approach at each signalised junction (assumed)
MIX = {"two_wheeler": 0.45, "car": 0.30, "auto": 0.18, "bus": 0.07}   # assumed
MAX_KMH = 60                      # speed cap on the corridor before calibration
WARMUP = 900                      # s before the first probe leaves
PROBE_EVERY, PROBE_SPAN = 60, 1800  # one probe car each way per minute for 30 minutes
END = WARMUP + PROBE_SPAN + 4500  # long enough for the last probe to arrive
FRAMES = (WARMUP + 600, WARMUP + 900, 2)   # vehicle positions for the 3D view: from, to, every N s


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


def calibrated_net(out: Path, caps=None):
    """Copy of the network with each leg's lanes capped at the calibrated speed (both directions)."""
    caps = caps if caps is not None else json.loads(CALIBRATION.read_text())["cap_kmh"]
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
                lane.set("speed", f"{min(float(lane.get('speed')), v):.2f}")
    tree.write(out)
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
def measured_cross(net, groups, on_path):
    """Cross-road volumes measured by TomTom Junction Analytics: {junction_id: {edge_id: veh/h}}, each approach matched
    to the network edge at its junction end with the same heading. Corridor approaches are left out (they are the
    through traffic). Mean over all minutes collected so far."""
    if not JA_LIVE.exists():
        return {}
    sums = {}
    for r in csv.DictReader(JA_LIVE.open()):
        k = (r["junction_id"], r["approach_id"])
        n, v = sums.get(k, (0, 0.0))
        sums[k] = (n + 1, v + float(r["volume_per_hour"]))
    out = {}
    for j in json.loads(JA_CONFIG.read_text())["junctions"]:
        jid, ids = j["corridor_id"], {n.getID() for n in groups.get(j["corridor_id"], [])}
        path = ROOT / f"data/tomtom/junction/corridor/{jid}_definition.json"
        if not ids or not path.exists():
            continue
        for a in json.loads(path.read_text())["junctionModel"]["approaches"]:
            n, v = sums.get((jid, str(a["id"])), (0, 0.0))
            vph = v / n if n else 0
            if vph < 30:
                continue
            (lo1, la1), (lo2, la2) = a["segmentedGeometry"]["coordinates"][-1][-2:]
            x1, y1 = net.convertLonLat2XY(lo1, la1); x2, y2 = net.convertLonLat2XY(lo2, la2)
            want = math.atan2(y2 - y1, x2 - x1)
            cands = [(e, d) for e, d in net.getNeighboringEdges(x2, y2, 50) if e.allows("passenger")
                     and abs(math.remainder(cn._angle(e) - want, 2 * math.pi)) < math.radians(45)]
            if not cands:
                continue
            e = min(cands, key=lambda t: t[1])[0]
            if e.getID() in on_path or e.getFromNode().getID() in ids:
                continue
            out.setdefault(jid, {})
            out[jid][e.getID()] = out[jid].get(e.getID(), 0) + vph
    return out


def demand(net, out: Path, base_groups, volume_scale=1.0):
    """Through, cross and probe flows. Through traffic and probes follow the corridor (fixed route); cross traffic
    leaves by a cross road or joins the corridor (assumed split). `base_groups` are the junction node ids of the
    unchanged network, so cross traffic still meets the ground junction under a flyover."""
    fwd, rev = cn.route(net), cn.route(net, reverse=True)
    on_path = {e.getID() for e in fwd + rev}
    groups = {j: [net.getNode(n) for n in ids if net.hasNode(n)] for j, ids in base_groups.items()}
    measured = measured_cross(net, groups, on_path)
    probabilities = " ".join(str(v) for v in MIX.values())
    lines = ['<routes>', VTYPES,
             '    <vType id="probe" vClass="passenger" length="4.3" minGap="1.0" tau="0.8" maxSpeed="16.7" accel="2.6" decel="4.5" '
             'speedFactor="1.0" color="1,1,1"><param key="has.vehroute.device" value="true"/></vType>',
             f'    <vTypeDistribution id="mix" vTypes="{" ".join(MIX)}" probabilities="{probabilities}"/>',
             f'    <route id="fwd" edges="{" ".join(e.getID() for e in fwd)}"/>',
             f'    <route id="rev" edges="{" ".join(e.getID() for e in rev)}"/>']
    end, probes = END - 900, []   # SUMO reads flows in start-time order, so the probes (start after warm-up) go last
    for name in ("fwd", "rev"):
        lines.append(f'    <flow id="through_{name}" type="mix" route="{name}" begin="0" end="{end}" '
                     f'vehsPerHour="{THROUGH_VPH * volume_scale:.0f}" departLane="best" departSpeed="max"/>')
        probes.append(f'    <flow id="probe_{name}" type="probe" route="{name}" begin="{WARMUP}" end="{WARMUP + PROBE_SPAN}" '
                      f'period="{PROBE_EVERY}" departLane="best" departSpeed="max"/>')
    pos = cn.junction_positions(net, fwd)
    sources = {}
    for jid, nodes in groups.items():
        ids = {n.getID() for n in nodes}
        outs = [e for n in nodes for e in n.getOutgoing() if e.getID() not in on_path and e.getToNode().getID() not in ids]
        i = pos[jid][0]
        joins = [fwd[min(i + 8, len(fwd) - 1)], rev[max(0, len(rev) - i - 8)]]
        if jid in measured:
            ins = [(net.getEdge(e), vph, "estimated") for e, vph in measured[jid].items()]
        else:
            ins = [(e, CROSS_VPH, "assumed") for n in nodes for e in n.getIncoming()
                   if e.getID() not in on_path and e.getFromNode().getID() not in ids]
        sources[jid] = {"approaches": len(ins), "vph": round(sum(v for _, v, _ in ins)), "label": ins[0][2] if ins else "none"}
        for e, vph, _ in ins:
            dests = [o for o in outs if o.getToNode().getID() != e.getFromNode().getID()] + joins
            dests = [d for d in dests if d.getID() != e.getID() and net.getShortestPath(e, d, vClass="passenger")[0]]
            for d in dests:
                lines.append(f'    <flow id="x_{jid}_{e.getID()}_{d.getID()}" type="mix" from="{e.getID()}" to="{d.getID()}" begin="0" '
                             f'end="{end}" vehsPerHour="{vph * volume_scale / len(dests):.0f}" departLane="best" departSpeed="max"/>')
    lines += probes + ['</routes>']
    out.write_text("\n".join(lines))
    return sources


def detectors(net, base_groups, out: Path):
    """A queue detector on the last 150 m of every lane approaching each corridor junction."""
    lines = ["<additional>"]
    for jid, node_ids in base_groups.items():
        nodes = [net.getNode(n) for n in node_ids if net.hasNode(n)]
        for e in {e for n in nodes for e in n.getIncoming() if e.getFromNode().getID() not in node_ids}:
            for lane in e.getLanes():
                L = lane.getLength()
                if L > 5:
                    lines.append(f'    <laneAreaDetector id="{jid}|{lane.getID()}" lane="{lane.getID()}" pos="{max(0, L - 150):.1f}" '
                                 f'endPos="{L - 0.5:.1f}" period="{END}" file="e2.xml"/>')
    lines.append("</additional>")
    out.write_text("\n".join(lines))
    return out


# ---------- run and measure ----------
def simulate(net_path: Path, rou: Path, add: Path, outdir: Path, frames=True):
    cmd = ["sumo", "-n", str(net_path), "-r", str(rou), "-a", str(add), "--begin", "0", "--end", str(END),
           "--seed", "2", "--step-length", "0.5", "--no-step-log", "--no-warnings", "--time-to-teleport", "300", "--ignore-route-errors",
           "--device.vehroute.probability", "0", "--vehroute-output", str(outdir / "probes.xml"),
           "--vehroute-output.exit-times", "--tripinfo-output", str(outdir / "trips.xml"),
           "--statistic-output", str(outdir / "stats.xml")]
    if frames:
        cmd += ["--fcd-output", str(outdir / "fcd.xml.gz"), "--fcd-output.geo", "--device.fcd.begin", str(FRAMES[0]),
                "--device.fcd.period", str(FRAMES[2])]
    subprocess.run(cmd, cwd=outdir, check=True, capture_output=True)


def probe_legs(net, outdir: Path):
    """Per leg (forward direction): mean distance, mean time, from the probes that arrived."""
    points = cn.CORRIDOR["points"]
    xy = [net.convertLonLat2XY(p["lon"], p["lat"]) for p in points]
    cache, per_probe = {}, []
    for v in ET.parse(outdir / "probes.xml").getroot().iter("vehicle"):
        if not v.get("id").startswith("probe_fwd") or v.get("arrival") is None:
            continue
        r = v.find("route")
        edges, exits = r.get("edges").split(), [float(t) for t in r.get("exitTimes").split()]
        key = r.get("edges")
        if key not in cache:   # the route edge whose end is closest to each corridor point, in order
            es = [net.getEdge(e) for e in edges]
            idx, start = [-1], 0
            for p in xy[1:-1]:
                k = min(range(start, len(es)), key=lambda i: math.dist(es[i].getToNode().getCoord()[:2], p))
                idx.append(k); start = k
            idx.append(len(es) - 1)
            lengths = [e.getLength() for e in es]
            cache[key] = (idx, [sum(lengths[a + 1:b + 1]) for a, b in zip(idx, idx[1:])])
        idx, dists = cache[key]
        t = [float(v.get("depart"))] + [exits[k] for k in idx[1:]]
        per_probe.append((dists, [b - a for a, b in zip(t, t[1:])]))
    if not per_probe:
        raise RuntimeError("no probe car reached Lakdikapul; the network is gridlocked")
    n = len(per_probe)
    return [(sum(p[0][k] for p in per_probe) / n, sum(p[1][k] for p in per_probe) / n) for k in range(len(points) - 1)], n


def junction_stats(outdir: Path, base_groups, net):
    """Mean time lost and longest queue on each junction's approaches, and vehicles that entered them."""
    acc = {jid: [0, 0.0, 0.0] for jid in base_groups}
    for d in ET.parse(outdir / "e2.xml").getroot().iter("interval"):
        jid = d.get("id").split("|")[0]
        n = int(d.get("nVehEntered", 0))
        acc[jid][0] += n
        acc[jid][1] += n * float(d.get("meanTimeLoss", 0) if float(d.get("meanTimeLoss", 0)) >= 0 else 0)
        acc[jid][2] = max(acc[jid][2], float(d.get("maxJamLengthInMeters", 0)))
    out = []
    for p in cn.CORRIDOR["points"]:
        if p["kind"] != "junction":
            continue
        n, loss, q = acc.get(p["id"], (0, 0, 0))
        out.append({"id": p["id"], "name": p["name"], "lat": p["lat"], "lon": p["lon"],
                    "avg_delay_s": round(loss / n, 1) if n else 0.0, "max_queue_m": round(q), "vehicles": n})
    return out


def write_frames(outdir: Path):
    """FCD -> frames.jsonl (C1): one line per time step with every vehicle's position."""
    frames, cur = [], []
    with gzip.open(outdir / "fcd.xml.gz") as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if el.tag == "vehicle":
                vt = el.get("type").split("@")[0]
                cur.append({"id": el.get("id"), "type": "car" if vt == "probe" else vt, "lon": round(float(el.get("x")), 6),
                            "lat": round(float(el.get("y")), 6), "z": round(float(el.get("z", 0)), 1),
                            "angle": round(float(el.get("angle"))), "speed": round(float(el.get("speed")), 1)})
            elif el.tag == "timestep":
                frames.append({"t": float(el.get("time")), "vehicles": cur}); el.clear()
                cur = []
    path = outdir / "frames.jsonl"
    with path.open("w") as f:
        for fr in frames:
            f.write(json.dumps(fr, separators=(",", ":")) + "\n")
    (outdir / "fcd.xml.gz").unlink()
    return path


def write_roads(net, outdir: Path):
    """GeoJSON of the corridor's main roads (for the map)."""
    feats = []
    for e in net.getEdges():
        if e.getFunction() == "internal" or not e.allows("passenger"):
            continue
        coords = [list(map(lambda v: round(v, 6), net.convertXY2LonLat(x, y))) for x, y, *_ in e.getShape(True)]
        feats.append({"type": "Feature", "properties": {"id": e.getID(), "lanes": e.getLaneNumber(), "name": e.getName()},
                      "geometry": {"type": "LineString", "coordinates": coords}})
    path = outdir / "roads.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    return path


def run(interventions=(), volume_scale=1.0, run_id=None, frames=True, caps=None, label="July 2026 average, 6 am-11 pm"):
    """Simulate the corridor with `interventions` (C5 shape); return the C5 corridor result."""
    run_id = run_id or "rc_" + uuid.uuid4().hex[:8]
    outdir = OUT / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    base = sumolib.net.readNet(str(NET))
    base_groups = {j: [n.getID() for n in g] for j, g in cn.junction_groups(base).items() if g}
    net_path = calibrated_net(outdir / "corridor.net.xml", caps)
    warnings = []
    if interventions:
        import corridor as templates   # sim/templates/corridor.py (interventions)
        variant = outdir / "variant.net.xml"
        warnings += templates.apply(net_path, variant, list(interventions))
        net_path = variant
    net = sumolib.net.readNet(str(net_path))
    sources = demand(net, outdir / "demand.rou.xml", base_groups, volume_scale)
    simulate(net_path, outdir / "demand.rou.xml", detectors(net, base_groups, outdir / "e2.add.xml"), outdir, frames)
    legs, n_probes = probe_legs(net, outdir)
    tt = tomtom_legs()
    pts = cn.CORRIDOR["points"]
    out_legs = []
    for k, ((dist, secs), (_, _, _, _, tt_kmh)) in enumerate(zip(legs, tt)):
        out_legs.append({"from_id": pts[k]["id"], "to_id": pts[k + 1]["id"], "from_name": pts[k]["name"], "to_name": pts[k + 1]["name"],
                         "distance_m": round(dist), "time_s": round(secs), "speed_kmh": round(dist / secs * 3.6, 1) if secs else None,
                         # TomTom's measured speed on this leg, over the simulated leg's length
                         "tomtom_time_s": round(dist / (tt_kmh / 3.6))})
    stats = ET.parse(outdir / "stats.xml").getroot()
    teleports = int(stats.find("teleports").get("total"))
    if teleports > 50:
        warnings.append(f"{teleports} vehicles were stuck for 5 minutes and skipped ahead (gridlock somewhere on the network)")
    kinds = {i["kind"] for i in interventions}
    result = {
        "run_id": run_id, "variant_id": "baseline" if not interventions else "+".join(f"{i['kind']}_{i['junction_id']}" for i in interventions),
        "corridor_id": CORRIDOR_ID,
        "time": {"window": "2026-07", "minutes": PROBE_SPAN // 60, "label": label},
        "interventions": list(interventions),
        "journey": {"total_s": sum(l["time_s"] for l in out_legs), "distance_m": sum(l["distance_m"] for l in out_legs),
                    "tomtom_total_s": sum(l["tomtom_time_s"] for l in out_legs), "legs": out_legs},
        "junctions": junction_stats(outdir, base_groups, net),
        "warnings": warnings,
        "inputs": {"counts_source": "estimated" if any(v["label"] == "estimated" for v in sources.values()) else "assumed",
                   "volume_scale": volume_scale, "cross_traffic": sources,
                   "through_vph": round(THROUGH_VPH * volume_scale), "cross_vph_per_approach": round(CROSS_VPH * volume_scale),
                   "calibrated_to": f"TomTom Traffic Stats job {TOMTOM_JOB}, July 2026 06:00-23:00, leg speeds",
                   "speeds_source": "counted (TomTom probe data)", "probes_arrived": n_probes, "teleports": teleports,
                   "sim_seconds": END, "wall_seconds": round(time.time() - t0, 1), "templates": sorted(kinds)},
        "frames_path": str(write_frames(outdir)) if frames else None,
        "roads_path": str(write_roads(net, outdir)),
    }
    (outdir / "result.json").write_text(json.dumps(result, indent=1))
    for f in ("probes.xml", "trips.xml"):
        (outdir / f).unlink(missing_ok=True)
    return result


# ---------- calibration ----------
def calibrate(rounds=5):
    """Tune each leg's speed cap until the probes' leg times match TomTom's July average (within ~5%)."""
    tt = tomtom_legs()
    caps = [min(MAX_KMH, 2.0 * kmh) for *_, kmh in tt]
    for r in range(rounds):
        res = run(caps=caps, frames=False, run_id=f"calib_{r}")
        errs = []
        for k, leg in enumerate(res["journey"]["legs"]):
            ratio = leg["time_s"] / leg["tomtom_time_s"]   # >1: simulated leg too slow
            errs.append(ratio)
            caps[k] = round(max(8.0, min(MAX_KMH, caps[k] * ratio ** 0.8)), 1)
        j = res["journey"]
        print(f"round {r}: sim {j['total_s'] / 60:.1f} min vs TomTom {j['tomtom_total_s'] / 60:.1f} min | "
              f"leg ratios {[round(e, 2) for e in errs]} | {res['inputs']['wall_seconds']} s", flush=True)
        shutil.rmtree(OUT / f"calib_{r}", ignore_errors=True)
        if all(abs(e - 1) < 0.05 for e in errs):
            break
    CALIBRATION.write_text(json.dumps({"cap_kmh": caps, "target": f"TomTom job {TOMTOM_JOB} (July 2026, 06:00-23:00)",
                                       "through_vph": THROUGH_VPH, "cross_vph": CROSS_VPH, "mix": MIX,
                                       "last_round": {"sim_total_s": j["total_s"], "tomtom_total_s": j["tomtom_total_s"],
                                                      "leg_ratios": [round(e, 3) for e in errs]}}, indent=1))
    return caps


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
