"""Test the corridor intervention templates (sim/templates/corridor.py) end to end: build each variant, check the
corridor route still runs both ways, run a SUMO simulation and compare trip times with the baseline.

Traffic (test only, assumed): 300 veh/h each way along the whole corridor for 15 minutes, plus 150 veh/h from each
side road at the junction under test; the run lasts until 75 minutes. Two times are reported per direction:
  A->B / B->A   the whole trip (also shows congestion elsewhere on the corridor, so it is noisy: +-70 s)
  local         from ~600 m before the junction to ~600 m after it: the PASS/FAIL check uses this one
Through trips are kept on the corridor with `via` edges (SUMO's own fastest A-B route leaves it at j03, j06, j07
and j10), except at a new flyover/underpass, where SUMO chooses between the structure and the ground road.

Usage (repo root, inside .venv):  python sim/templates/test_corridor.py          (about 2 minutes)
                                  python sim/templates/test_corridor.py j07       (only cases whose name has j07)
"""
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import sumolib

sys.path.insert(0, str(Path(__file__).parent))
import corridor  # noqa: E402
from corridor import cn  # noqa: E402

BASE = cn.ROOT / "sim/corridor/corridor.net.xml"
SUMO = sumolib.checkBinary("sumo")
MAX_TELEPORTS = 5
THROUGH_VPH = 300   # each way along the whole corridor
CROSS_VPH = 150     # per side road at the junction under test
WINDOW_M = 600      # local window either side of the junction

# (name, interventions, expectation for the local through time: "faster" / "slower" / "runs")
CASES = [
    ("flyover j07", [{"junction_id": "j07", "kind": "flyover", "params": {}}], "faster"),
    ("flyover j08", [{"junction_id": "j08", "kind": "flyover", "params": {"lanes": 2, "length_m": 500}}], "faster"),
    ("flyover j03", [{"junction_id": "j03", "kind": "flyover", "params": {"lanes": 3}}], "faster"),
    ("underpass j07", [{"junction_id": "j07", "kind": "underpass", "params": {}}], "faster"),
    ("underpass j10", [{"junction_id": "j10", "kind": "underpass", "params": {}}], "faster"),
    ("retime j07 share 0.3", [{"junction_id": "j07", "kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.3}}], "slower"),
    ("retime j07 share 0.6", [{"junction_id": "j07", "kind": "signal_retime", "params": {"cycle_s": 120, "corridor_green_share": 0.6}}], "runs"),
    ("retime j08 share 0.3", [{"junction_id": "j08", "kind": "signal_retime", "params": {"cycle_s": 150, "corridor_green_share": 0.3}}], "slower"),
    ("retime j05 share 0.3", [{"junction_id": "j05", "kind": "signal_retime", "params": {"cycle_s": 120, "main_share": 0.3}}], "slower"),
    ("retime j05 share 0.7", [{"junction_id": "j05", "kind": "signal_retime", "params": {"cycle_s": 90, "corridor_green_share": 0.7}}], "faster"),
    # j03: the corridor crosses the signalled roundabout in two stages, so only the cycle can change (warns)
    ("retime j03 share 0.3", [{"junction_id": "j03", "kind": "signal_retime", "params": {"cycle_s": 90, "corridor_green_share": 0.3}}], "runs"),
    ("widening j05", [{"junction_id": "j05", "kind": "widening", "params": {"add_lanes": 1}}], "runs"),
    ("widening j07", [{"junction_id": "j07", "kind": "widening", "params": {}}], "runs"),
    ("flyover j07+retime j09", [{"junction_id": "j07", "kind": "flyover", "params": {}},
                                {"junction_id": "j09", "kind": "signal_retime", "params": {"corridor_green_share": 0.7}}], "faster"),
]


def corridor_via(path):
    """`via` edges that keep the through trips on the corridor while leaving SUMO free to choose between a new
    flyover/underpass and the ground road under it: every corridor edge except the structures and the ground
    pieces beside them."""
    return [e.getID() for e in path[1:-1] if not e.getID().startswith(corridor.GRADE) and ".flyover_" not in e.getID()
            and ".underpass_" not in e.getID()]


def window(base_net, jid):
    """{flow: (edge before, edge after)}: corridor edges ending/starting >= WINDOW_M m from the junction, on the
    baseline. Their ids survive every edit (ramps start and land closer than that)."""
    ctx = {"paths": {"fwd": cn.route(base_net), "rev": cn.route(base_net, reverse=True)}}
    ctx["groups"] = {tag: cn.junction_nodes(base_net, p) for tag, p in ctx["paths"].items()}
    out = {}
    for tag, (path, i0, i1) in corridor.sides(ctx, jid).items():
        k, d = i0, 0.0
        while k > 0 and d < WINDOW_M:
            d += path[k].getLength(); k -= 1
        m, d = i1, 0.0
        while m < len(path) - 1 and d < WINDOW_M:
            d += path[m].getLength(); m += 1
        out["ab" if tag == "fwd" else "ba"] = (path[k].getID(), path[m].getID())
    return out


def demand(base_net, jid, net, path):
    """Trips file: through traffic both ways along `net`'s corridor, and cross traffic at the junction (from every
    side road of the baseline junction to every other)."""
    fwd, rev = cn.route(base_net), cn.route(base_net, reverse=True)
    group = {n.getID() for side in (fwd, rev) for n in cn.junction_nodes(base_net, side).get(jid, [])}
    on_corridor = {e.getID() for e in fwd + rev}
    nodes = [base_net.getNode(n) for n in group]
    ins = {e.getID() for n in nodes for e in n.getIncoming() if e.getFromNode().getID() not in group and e.getID() not in on_corridor}
    outs = {e.getID() for n in nodes for e in n.getOutgoing() if e.getToNode().getID() not in group and e.getID() not in on_corridor}
    lines = ['<routes>', '<vType id="car" vClass="passenger"/>']
    for fid, p in (("ab", cn.route(net)), ("ba", cn.route(net, reverse=True))):
        lines.append(f'<flow id="{fid}" type="car" from="{p[0].getID()}" to="{p[-1].getID()}" via="{" ".join(corridor_via(p))}" '
                     f'begin="0" end="900" vehsPerHour="{THROUGH_VPH}" departLane="best"/>')
    for i, a in enumerate(sorted(ins)):
        targets = [b for b in sorted(outs) if base_net.getEdge(b).getToNode() != base_net.getEdge(a).getFromNode()]
        for j, b in enumerate(targets):
            lines.append(f'<flow id="x{i}_{j}" type="car" from="{a}" to="{b}" begin="0" end="900" '
                         f'vehsPerHour="{CROSS_VPH / len(targets):.0f}" departLane="best"/>')
    lines.append('</routes>')
    path.write_text("\n".join(lines))


def simulate(net_path, routes, win, tmp):
    """Run SUMO. Returns mean trip time per through flow ('ab', 'ba'), mean local time ('ab_local', 'ba_local'),
    trips arrived ('n_ab', 'n_ba'), teleports, and each through vehicle's route."""
    vroute, stats = f"{tmp}/vroute.xml", f"{tmp}/stats.xml"
    r = subprocess.run([SUMO, "-n", str(net_path), "-r", str(routes), "--end", "4500", "--no-step-log", "--no-warnings",
                        "--ignore-route-errors", "--vehroute-output", vroute, "--vehroute-output.exit-times",
                        "--statistic-output", stats, "--time-to-teleport", "300"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    trips, local, routes_ = {"ab": [], "ba": []}, {"ab": [], "ba": []}, {}
    for v in ET.parse(vroute).getroot().iter("vehicle"):
        flow = v.get("id").split(".")[0]
        if flow not in trips or v.find("route") is None:
            continue
        edges = v.find("route").get("edges").split()
        exits = [float(x) for x in v.find("route").get("exitTimes").split()]
        routes_[v.get("id")] = edges
        trips[flow].append(float(v.get("arrival")) - float(v.get("depart")))
        a, b = win.get(flow, (None, None))
        if a in edges and b in edges:
            local[flow].append(exits[edges.index(b)] - exits[edges.index(a)])
    tele = ET.parse(stats).getroot().find("teleports")
    for f in (vroute, stats):
        Path(f).unlink(missing_ok=True)
    mean = lambda xs: statistics.mean(xs) if xs else float("nan")  # noqa: E731
    return {"ab": mean(trips["ab"]), "ba": mean(trips["ba"]), "ab_local": mean(local["ab"]), "ba_local": mean(local["ba"]),
            "n_ab": len(trips["ab"]), "n_ba": len(trips["ba"]), "routes": routes_,
            "teleports": int(tele.get("total")) if tele is not None else 0}


def run_case(base_net, ends, name, ivs, expect, baselines, tmp):
    """Build, check and simulate one case; returns a result row (PASS / WARN / FAIL)."""
    jid, kinds = ivs[0]["junction_id"], {iv["kind"] for iv in ivs}
    win = window(base_net, jid)
    if jid not in baselines:
        demand(base_net, jid, base_net, Path(tmp) / "base.rou.xml")
        baselines[jid] = simulate(BASE, Path(tmp) / "base.rou.xml", win, tmp)
    base, problems, cautions = baselines[jid], [], []
    row = {"name": name, "base": base, "var": None, "result": "FAIL"}
    out = Path(tmp) / "variant.net.xml"
    try:
        warnings = corridor.apply(BASE, out, ivs)
    except Exception as e:  # noqa: BLE001  (a build failure is a FAIL row)
        return {**row, "note": f"build failed: {e}"[:110]}
    net = sumolib.net.readNet(str(out))
    for tag, rev in (("fwd", False), ("rev", True)):
        p = cn.route(net, rev)
        if not p or (p[0].getID(), p[-1].getID()) != ends[tag]:
            problems.append(f"{tag} corridor route broken")
    demand(base_net, jid, net, Path(tmp) / "variant.rou.xml")
    var = simulate(out, Path(tmp) / "variant.rou.xml", win, tmp)
    for flow, tag in (("ab", "fwd"), ("ba", "rev")):     # SUMO's own route choice past the junction
        structure = {e.getID() for e in net.getEdges() if e.getID().startswith(corridor.GRADE) and e.getID().endswith(tag)}
        through = [r for v, r in var["routes"].items() if v.startswith(flow + ".")]
        used = sum(1 for r in through if structure & set(r)) / max(1, len(through))
        if structure and used < 0.9:
            problems.append(f"only {used:.0%} of {flow} trips take the {tag} structure")
    if var["teleports"] > base["teleports"] + MAX_TELEPORTS:
        msg = f"{var['teleports']} teleports (baseline {base['teleports']})"
        # a flyover/underpass must not jam; a harsh signal plan may (that is a result, not a broken network)
        (problems if kinds & {"flyover", "underpass"} else cautions).append(msg)
    for flow in ("ab", "ba"):
        if var[f"n_{flow}"] < 0.98 * base[f"n_{flow}"]:
            cautions.append(f"{base[f'n_{flow}'] - var[f'n_{flow}']} fewer {flow} trips arrived in time")
    local = lambda r: statistics.mean(x for x in (r["ab_local"], r["ba_local"]) if x == x)  # noqa: E731
    delta = local(var) - local(base)
    if expect == "faster" and delta >= 0:
        problems.append(f"expected a shorter local time, got {delta:+.0f} s")
    if expect == "slower" and delta <= 0:
        problems.append(f"expected a longer local time, got {delta:+.0f} s")
    result = "FAIL" if problems else "WARN" if cautions else "PASS"
    return {**row, "var": var, "result": result, "note": "; ".join(problems + cautions + warnings)[:150]}


def check_errors():
    """Bad input: unknown junction/kind raise ValueError; j04 flyover only warns."""
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, iv in (("unknown junction", {"junction_id": "j99", "kind": "flyover"}),
                         ("unknown kind", {"junction_id": "j07", "kind": "teleporter"}),
                         ("bad param", {"junction_id": "j07", "kind": "signal_retime", "params": {"corridor_green_share": 1.5}})):
            try:
                corridor.apply(BASE, Path(tmp) / "x.net.xml", [iv])
                rows.append((name, "FAIL", "no ValueError"))
            except ValueError as e:
                rows.append((name, "PASS", f"ValueError: {e}"[:90]))
        w = corridor.apply(BASE, Path(tmp) / "x.net.xml", [{"junction_id": "j04", "kind": "flyover"}])
        rows.append(("flyover at j04", "PASS" if any("already has a flyover" in x for x in w) else "FAIL", (w or ["no warning"])[0][:90]))
    return rows


def main(only=None):
    base_net = sumolib.net.readNet(str(BASE))
    ends = {tag: (p[0].getID(), p[-1].getID()) for tag, p in (("fwd", cn.route(base_net)), ("rev", cn.route(base_net, True)))}
    baselines, rows = {}, []
    with tempfile.TemporaryDirectory() as tmp:
        for name, ivs, expect in CASES:
            if only and only not in name:
                continue
            rows.append(run_case(base_net, ends, name, ivs, expect, baselines, tmp))
            print(f"  {rows[-1]['result']}: {name}", flush=True)
    nan = {k: float("nan") for k in ("ab", "ba", "ab_local", "ba_local")} | {"teleports": 0}
    print(f"\nTimes in seconds, baseline -> variant. local = {WINDOW_M} m either side of the junction.")
    print(f"{'case':24} {'result':6} {'A->B trip':>13} {'B->A trip':>13} {'A->B local':>11} {'B->A local':>11} {'telep':>5}  notes")
    for r in rows:
        b, v = r["base"], r["var"] or nan
        cell = lambda k, w: f"{b[k]:.0f}->{v[k]:.0f}".rjust(w)  # noqa: E731
        print(f"{r['name']:24} {r['result']:6} {cell('ab', 13)} {cell('ba', 13)} {cell('ab_local', 11)} {cell('ba_local', 11)} "
              f"{v['teleports']:5d}  {r['note']}")
    for name, res, note in check_errors():
        rows.append({"result": res})
        print(f"{name:24} {res:6} {'':61} {note}")
    failed = sum(r["result"] == "FAIL" for r in rows)
    print(f"\n{sum(r['result'] == 'PASS' for r in rows)} PASS, {sum(r['result'] == 'WARN' for r in rows)} WARN, {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
