"""SUMO runner: a C3 variant spec in, a C2 run result out, plus C1 vehicle frames for the 3D view.

Owner: Simulation workstream. The backend calls `run()` when MOCK_SIM=0 (backend/app/main.py).

    result = run({"variant_id": "flyover_3lane_400m", "template": "flyover",
                  "params": {"lanes": 3, "length_m": 400}}, volume_scale=1.0, run_id="r_abc")
    # -> C2 dict (contracts/run_result.schema.json) + "frames_path": JSON lines, one C1 frame per second

Command line:  python sim/runner.py '{"variant_id":"baseline","template":"baseline","params":{}}' --scale 1.0 [--seed 42] [--upstream 600]

What a run does
  1. Picks the network for the template: baseline = sim/networks/ymca.net.xml; flyover = built once by
     sim/templates/flyover.py from the params (its design check becomes the C2 warnings).
  2. Builds the traffic for that network at the requested volume scale (sim/scripts/build_demand.py:
     2020 study counts, TomTom morning turn shares). Vehicles start and end UPSTREAM_M from the circle,
     so they pass the next junctions on each road.
  3. Runs SUMO for SIM_END seconds with the sublane model; statistics start after WARMUP.
  4. Measures delay and queues in zones: `ymca_circle` (ring, flyover, and the 240 m of each road touching
     it) and `next_<direction>` (240-700 m out on each road, where a ripple would show).
  5. Writes the C1 frames (FRAMES_FROM..FRAMES_TO) for playback.

Delay per junction = total time lost on the zone's roads / vehicles entering the zone. Queue = the longest
queue seen on any lane in the zone (SUMO queue output). `approach_speed_kmh` is the simulated speed on the
last 240 m of each road into the circle, next to TomTom's measured 09:00 speed (`tomtom_speed_kmh`).
About 1.5% of vehicles collide in the sublane model and are removed; that is SUMO's default handling.
"""
import contextlib, csv, io, json, math, os, subprocess, sys, time, uuid, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim/scripts"))
sys.path.insert(0, str(ROOT / "sim/templates"))
import build_demand as bd  # noqa: E402
import sumolib  # noqa: E402

BASE_NET = ROOT / "sim/networks/ymca.net.xml"
DEFINITION = ROOT / "data/tomtom/junction/ymca_definition.json"
TOMTOM_SPEEDS = ROOT / "data/raw/tomtom_ymca_speeds.csv"
TOMTOM_JUNCTION = ROOT / "data/raw/tomtom_ymca_junction_live.csv"
OUT = ROOT / "sim/out"
SIM_END = 1800        # simulated seconds per run (a few seconds of wall time)
WARMUP = 300          # statistics start here, once the roads have filled
FRAMES_FROM, FRAMES_TO = 300, 1200   # 15 minutes of C1 frames for the 3D view
NEAR_M, FAR_M = 240, 700             # zone limits along each road from the circle
UPSTREAM_M = 600      # where vehicles start and end, measured from the circle
CALIBRATED_SCALE = 2.0  # 2020 study counts x 2.0 (with close following) reproduce TomTom's 09:00 speeds within ~3 km/h (3-seed mean)
SEED = 2              # closest of 9 seeds to their mean (speeds within 0.3 km/h of it); demo runs are reproducible
SUMO_OPTS = ["--lateral-resolution", "0.3", "--time-to-teleport", "300", "--no-step-log", "--no-warnings"]
DIRECTION = {  # TomTom approach / exit names -> compass label used in junction ids
    "Narayanguda Road South Bound": "ne", "Narayanguda Road North Bound": "s",
    "Raja Bahadur Venkata Rama Reddy Marg West Bound": "e", "Raja Bahadur Venkata Rama Reddy Marg East Bound": "e",
    "YMCA to Ramkoti Road East Bound": "w", "YMCA to Ramkoti Road West Bound": "w",
}
TOMTOM_ROUTE = {"ne": "NE Narayanaguda Road - in", "s": "S road - in", "e": "SE Basant Talkies side - in",
                "w": "W Narayanguda Main Road - in"}


def network_for(variant: dict):
    """Network file for the variant and any design warnings from its template."""
    template, params = variant["template"], variant.get("params") or {}
    if template == "baseline":
        return BASE_NET, []
    if template == "flyover":
        import flyover
        lanes, length = int(params.get("lanes", 3)), float(params.get("length_m", 400))
        out = OUT / "variants" / f"{variant['variant_id']}.net.xml"
        if not out.exists():
            flyover.build(lanes, length, params.get("axis", "east_west"), out)
        return out, [w["message"] for w in flyover.design_check(out, lanes)]
    raise NotImplementedError(f"template '{template}' has no builder in sim/templates yet "
                              f"(available: baseline, flyover)")


def demand_for(net_path: Path, volume_scale: float, upstream_m: float, window: str | None = None,
               minutes: int = 15) -> Path:
    """Traffic file for C2 `volume_scale` (1.0 = today's calibrated traffic, 0.8 = the 20% sensitivity test).
    With `window` (ISO start, IST) the volumes and turns come from TomTom's junction data in that window instead:
    TomTom's vehicles/hour is used as is (estimated), scaled only by `volume_scale`."""
    scale = round(volume_scale * (1.0 if window else CALIBRATED_SCALE), 3)
    tag = f"_w{window.replace(':', '').replace('-', '')[:13]}m{minutes}" if window else ""
    out = OUT / "demand" / f"{net_path.stem}_scale{scale:.2f}_up{int(upstream_m)}{tag}.rou.xml"
    if not out.exists():
        tmp = out.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")  # written whole, then renamed: safe for parallel runs
        bd.NET, bd.OUT, bd.UPSTREAM_M = net_path, tmp, upstream_m
        sys.argv = ["build_demand.py", "--scale", str(scale), "--since", "08:00", "--until", "11:00",
                    "--begin", "0", "--end", str(SIM_END)] + (["--window", window, "--minutes", str(minutes)] if window else [])
        with contextlib.redirect_stdout(io.StringIO()):
            bd.main()
        os.replace(tmp, out)
    return out


def chain(edge, backwards: bool, max_m: float):
    """Edges along one road away from the circle: [(edge, metres from the circle to its start)]."""
    out, e, total, seen = [(edge, 0.0)], edge, edge.getLength(), {edge.getID()}
    while total < max_m:
        cands = [x for x in (e.getIncoming() if backwards else e.getOutgoing())
                 if x.getID() not in seen and not x.getID().startswith(":")
                 and (x.getFromNode() != e.getToNode() if backwards else x.getToNode() != e.getFromNode())]
        turn = lambda x: abs(math.remainder(bd.angle(x) - bd.angle(e), 2 * math.pi))  # noqa: E731
        cands = [x for x in cands if turn(x) < math.radians(80)]
        if not cands:
            break
        e = min(cands, key=turn)
        seen.add(e.getID()); out.append((e, total)); total += e.getLength()
    return out


def zones(net):
    """{junction id: {"edges": set of edge ids, "gates": edges whose entered+departed counts vehicles}}
    plus {"approaches": {direction: [near edges of the road into the circle]}}."""
    definition = json.loads(DEFINITION.read_text())
    ins, outs = bd.approach_edges(net, definition)
    centre = net.convertLonLat2XY(*definition["rawJunction"]["geometry"]["coordinates"])
    rb = min(net.getRoundabouts(), key=lambda r: math.dist(net.getNode(r.getNodes()[0]).getCoord()[:2], centre))
    circle = {"edges": set(rb.getEdges()) | {e.getID() for e in net.getEdges() if e.getID().startswith("flyover_")},
              "gates": {e.getID() for e in ins.values()}}
    z, approaches = {"ymca_circle": circle}, {}
    for name, edge in list(ins.items()) + list(outs.items()):
        d = DIRECTION.get(name, "x")
        far = z.setdefault(f"next_{d}", {"edges": set(), "gates": set()})
        backwards = name in ins
        near_edges, far_edges = [], []
        for e, dist in chain(edge, backwards, FAR_M):
            (near_edges if dist < NEAR_M else far_edges).append(e)
        circle["edges"].update(e.getID() for e in near_edges)
        far["edges"].update(e.getID() for e in far_edges)
        if far_edges:
            far["gates"].add((far_edges[-1] if backwards else far_edges[0]).getID())
        if backwards:
            approaches[d] = near_edges
    return z, approaches


def measure(run_dir: Path, z: dict, approaches: dict):
    ed = {e.get("id"): e for e in ET.parse(run_dir / "edgedata.xml").getroot().iter("edge")}
    queue = {}
    for lane in ET.parse(run_dir / "queue.xml").getroot().iter("lane"):
        eid = lane.get("id").rsplit("_", 1)[0]
        queue[eid] = max(queue.get(eid, 0.0), float(lane.get("queueing_length") or 0))
    junctions = []
    for jid, zone in z.items():
        loss = sum(float(ed[e].get("timeLoss") or 0) for e in zone["edges"] if e in ed)
        vehicles = sum(int(float(ed[e].get("entered") or 0)) + int(float(ed[e].get("departed") or 0))
                       for e in zone["gates"] if e in ed)
        junctions.append({"id": jid, "avg_delay_s": round(loss / vehicles, 1) if vehicles else 0.0,
                          "max_queue_m": round(max((queue.get(e, 0.0) for e in zone["edges"]), default=0.0)),
                          "vehicles": vehicles})
    tomtom = {(r["route"], int(r["hour"])): float(r["avg_speed_kmh"]) for r in csv.DictReader(open(TOMTOM_SPEEDS))}
    speeds, refs, delays, weights = {}, {}, {}, {}
    for d, edges in approaches.items():
        length = sum(e.getLength() for e in edges); t = 0.0; loss = 0.0
        for e in edges:
            x = ed.get(e.getID()); sp = float(x.get("speed")) if x is not None and x.get("speed") else e.getSpeed()
            t += e.getLength() / max(sp, 0.1)
            loss += float(x.get("timeLoss") or 0) if x is not None else 0.0
        speeds[d] = round(length / t * 3.6, 1) if t else None
        refs[d] = tomtom.get((TOMTOM_ROUTE.get(d), 9))
        entry = ed.get(edges[0].getID())  # the edge touching the ring: every vehicle from this road passes it
        n = int(float(entry.get("entered") or 0)) + int(float(entry.get("departed") or 0)) if entry is not None else 0
        delays[d], weights[d] = (round(loss / n, 1) if n else None), n
    # TomTom-comparable delay for the circle: time lost on the last 240 m of each road, averaged over vehicles
    circle = next(j for j in junctions if j["id"] == "ymca_circle")
    circle["time_loss_through_zone_s"] = circle["avg_delay_s"]
    total = sum(weights.values())
    circle["avg_delay_s"] = round(sum(delays[d] * weights[d] for d in delays if delays[d] is not None) / total, 1) if total else 0.0
    ref_delays, ref_speeds = tomtom_morning_reference()
    trips = [t for t in ET.parse(run_dir / "tripinfo.xml").getroot().iter("tripinfo") if float(t.get("depart")) >= WARMUP]
    travel = sum(float(t.get("duration")) for t in trips) / len(trips) if trips else 0.0
    return junctions, round(travel), len(trips), speeds, refs, delays, ref_delays, ref_speeds


def tomtom_morning_reference():
    """TomTom Junction Analytics, Fri 9 Oct 2026 08:00-11:00: median delay per approach, and the median speed over
    the approach (its length / median travel time). A second yardstick next to the July route speeds."""
    delays, travel = {}, {}
    if TOMTOM_JUNCTION.exists():
        for r in csv.DictReader(open(TOMTOM_JUNCTION)):
            if "08:00" <= r["time"][11:16] < "11:00" and r["approach"] in DIRECTION:
                d = DIRECTION[r["approach"]]
                delays.setdefault(d, []).append(float(r["delay_s"])); travel.setdefault(d, []).append(float(r["travel_time_s"]))
    lengths = {}
    if DEFINITION.exists():
        for a in json.loads(DEFINITION.read_text())["junctionModel"]["approaches"]:
            if a["name"] in DIRECTION:
                lengths[DIRECTION[a["name"]]] = float(a["length"])
    med = lambda v: sorted(v)[len(v) // 2]  # noqa: E731
    return ({d: round(med(v), 1) for d, v in delays.items()},
            {d: round(lengths[d] / med(v) * 3.6, 1) for d, v in travel.items() if d in lengths and med(v) > 0})


def write_frames(fcd: Path, out: Path) -> int:
    import gzip
    n = 0
    with open(out, "w") as f, (gzip.open(fcd, "rb") if fcd.suffix == ".gz" else open(fcd, "rb")) as src:
        for _, el in ET.iterparse(src, events=("end",)):
            if el.tag != "timestep":
                continue
            t = float(el.get("time"))
            if FRAMES_FROM <= t < FRAMES_TO:
                vehicles = [{"id": v.get("id"), "type": v.get("type"), "lon": round(float(v.get("x")), 6),
                             "lat": round(float(v.get("y")), 6), "z": round(float(v.get("z") or 0), 1),
                             "angle": round(float(v.get("angle")), 1), "speed": round(float(v.get("speed")), 2)}
                            for v in el.iter("vehicle")]
                f.write(json.dumps({"t": t, "vehicles": vehicles}) + "\n"); n += 1
            el.clear()
            if t >= FRAMES_TO:
                break
    fcd.unlink(missing_ok=True)
    return n


def write_roads(net, edgedata: Path, out: Path):
    """GeoJSON of every road with its simulated mean speed, speed limit and vehicles, for map colouring."""
    ed = {e.get("id"): e for e in ET.parse(edgedata).getroot().iter("edge")}
    feats = []
    for e in net.getEdges():
        if e.getID().startswith(":"):
            continue
        d = ed.get(e.getID())
        speed = float(d.get("speed")) * 3.6 if d is not None and d.get("speed") else None
        coords = [list(net.convertXY2LonLat(x, y)) for x, y in e.getShape()]
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[round(a, 6), round(b, 6)] for a, b in coords]},
                      "properties": {"id": e.getID(), "name": e.getName() or "", "lanes": e.getLaneNumber(),
                                     "limit_kmh": round(e.getSpeed() * 3.6), "speed_kmh": round(speed, 1) if speed is not None else None,
                                     "vehicles": int(float(d.get("entered") or 0)) if d is not None else 0,
                                     "flyover": e.getID().startswith("flyover_")}})
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))


def run(variant: dict, volume_scale: float = 1.0, run_id: str | None = None, seed: int = SEED,
        upstream_m: float = UPSTREAM_M, frames: bool = True, window: str | None = None, minutes: int = 15) -> dict:
    """`frames=False` skips the vehicle-position output. `window` rebuilds a specific time from TomTom's junction
    data (see demand_for); the result then also carries TomTom's measured numbers for that window."""
    t0 = time.time()
    run_id = run_id or "r_" + uuid.uuid4().hex[:8]
    net_path, warnings = network_for(variant)
    rou = demand_for(net_path, volume_scale, upstream_m, window, minutes)
    run_dir = OUT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "add.xml").write_text(f'<additional><edgeData id="z" file="edgedata.xml" begin="{WARMUP}" end="{SIM_END}"/></additional>')
    cmd = ["sumo", "-n", str(net_path), "-r", str(rou), "-a", str(run_dir / "add.xml"), "--end", str(SIM_END),
           "--seed", str(seed), "--tripinfo-output", str(run_dir / "tripinfo.xml"),
           "--queue-output", str(run_dir / "queue.xml")] + SUMO_OPTS
    if frames:  # .gz: SUMO compresses the vehicle positions (about 15 MB instead of 150 MB of temporary file)
        cmd += ["--fcd-output", str(run_dir / "fcd.xml.gz"), "--fcd-output.geo", "true",
                "--fcd-output.attributes", "id,type,x,y,z,angle,speed", "--device.fcd.begin", str(FRAMES_FROM)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"sumo failed: {proc.stderr[-800:]}")
    net = sumolib.net.readNet(str(net_path))
    z, approaches = zones(net)
    junctions, travel, trips, speeds, refs, delays, ref_delays, ref_speeds = measure(run_dir, z, approaches)
    n_frames = write_frames(run_dir / "fcd.xml.gz", run_dir / "frames.jsonl") if frames else 0
    write_roads(net, run_dir / "edgedata.xml", run_dir / "roads.geojson")
    (run_dir / "queue.xml").unlink(missing_ok=True)  # measured; 1-2 MB per run otherwise
    if window:  # TomTom's own measurements for the same minutes, per direction, for a like-for-like comparison
        w = bd.tomtom_window(bd.window_bounds(window, minutes))
        lengths = {DIRECTION[a["name"]]: float(a["length"]) for a in json.loads(DEFINITION.read_text())["junctionModel"]["approaches"] if a["name"] in DIRECTION}
        tomtom_window = {DIRECTION[a]: {"delay_s": v["delay_s"], "queue_m": round(v["queue_m"]), "volume_per_hour": round(v["volume_per_hour"]),
                                        "speed_kmh": round(lengths[DIRECTION[a]] / v["travel_time_s"] * 3.6, 1) if v["travel_time_s"] else None,
                                        "minutes": v["minutes"]} for a, v in w.items() if a in DIRECTION}
        inputs = {"counts_source": "tomtom_junction_volumes + tomtom_turns (window) + 2020 vehicle mix", "label": "estimated",
                  "volume_scale": volume_scale, "window": window, "minutes": minutes,
                  "calibration": "volumes per road = TomTom's estimate for the window; turns measured in the window; "
                                 "vehicle mix from the 2020 count", "seed": seed, "upstream_m": upstream_m}
    else:
        tomtom_window = None
        inputs = {"counts_source": "published_study_2020 + tomtom_turns_2026", "label": "estimated",
                  "volume_scale": volume_scale, "count_scale": round(volume_scale * CALIBRATED_SCALE, 3),
                  "calibration": f"2020 counts x {CALIBRATED_SCALE} with close following match TomTom 09:00 "
                                 "speeds within ~3 km/h (3-seed mean); ~5,700 vehicles/h through the circle",
                  "seed": seed, "upstream_m": upstream_m}
    result = {"run_id": run_id, "variant_id": variant["variant_id"], "junctions": junctions,
              "corridor_travel_time_s": travel, "warnings": warnings, "inputs": inputs,
              "tomtom_window": tomtom_window, "tomtom_junction_speed_kmh": ref_speeds,
              "approach_speed_kmh": speeds, "tomtom_speed_kmh": refs,
              "approach_delay_s": delays, "tomtom_delay_s": ref_delays,
              "frames_path": str(run_dir / "frames.jsonl") if frames else None, "frames": n_frames, "trips": trips,
              "roads_path": str(run_dir / "roads.geojson"),
              "network": str(net_path), "sim_seconds": SIM_END, "wall_seconds": round(time.time() - t0, 1)}
    (run_dir / "result.json").write_text(json.dumps(result, indent=1))
    return result


def _arg(name, default, cast):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


if __name__ == "__main__":
    spec = json.loads(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].startswith("{") else \
        {"variant_id": "baseline", "template": "baseline", "params": {}}
    res = run(spec, _arg("--scale", 1.0, float), seed=_arg("--seed", SEED, int), upstream_m=_arg("--upstream", UPSTREAM_M, float),
              window=_arg("--window", None, str), minutes=_arg("--minutes", 15, int))
    print(json.dumps({k: v for k, v in res.items() if k != "frames_path"}, indent=1))
