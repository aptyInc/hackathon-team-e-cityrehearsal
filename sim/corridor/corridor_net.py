"""Corridor network helpers: the route through the network, the network node of each corridor junction, and signals.

Used by build_network.sh (signals) and by the corridor runner and intervention templates (route, junction nodes).
"""
import json
import math
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import sumolib

ROOT = Path(__file__).resolve().parents[2]
CORRIDOR = json.loads((ROOT / "data/corridor/corridor.json").read_text())
ROUTE_POINTS = json.loads((Path(__file__).parent / "route_points.json").read_text())
SIGNAL_CYCLE_S = 120   # assumed default cycle at the corridor's signalised junctions


def _angle(e):
    s = e.getShape()
    return math.atan2(s[-1][1] - s[0][1], s[-1][0] - s[0][0])


def edge_along(net, i):
    """Edge near route point i heading the same way as the measured route there."""
    (la, lo), (la2, lo2) = ROUTE_POINTS[i], ROUTE_POINTS[min(i + 1, len(ROUTE_POINTS) - 1)]
    x, y = net.convertLonLat2XY(lo, la); x2, y2 = net.convertLonLat2XY(lo2, la2)
    want = math.atan2(y2 - y, x2 - x)
    best = None
    for e, d in net.getNeighboringEdges(x, y, 60):
        if not e.allows("passenger"):
            continue
        diff = abs(math.remainder(_angle(e) - want, 2 * math.pi))
        score = d + diff * 20
        if diff < math.radians(60) and (best is None or score < best[1]):
            best = (e, score)
    return best[0] if best else None


def route(net, reverse=False):
    """Edges of the corridor trip (Lingampally -> Lakdikapul, or back), the fastest path through the network."""
    if not reverse:
        a, b = edge_along(net, 1), edge_along(net, len(ROUTE_POINTS) - 3)
    else:   # the opposite carriageway: an edge near each end heading the other way
        a, b = _reverse_edge(net, len(ROUTE_POINTS) - 3), _reverse_edge(net, 1)
    path, _ = net.getShortestPath(a, b, vClass="passenger")
    return path or []


def _reverse_edge(net, i):
    (la, lo), (la2, lo2) = ROUTE_POINTS[min(i + 1, len(ROUTE_POINTS) - 1)], ROUTE_POINTS[i]
    x, y = net.convertLonLat2XY(lo, la); x2, y2 = net.convertLonLat2XY(lo2, la2)
    want = math.atan2(y2 - y, x2 - x)
    cands = [(e, d) for e, d in net.getNeighboringEdges(x, y, 60) if e.allows("passenger")
             and abs(math.remainder(_angle(e) - want, 2 * math.pi)) < math.radians(60)]
    return min(cands, key=lambda t: t[1])[0] if cands else None


def junction_positions(net, path):
    """For each corridor point: index of the path edge whose end is closest to it, and the distance (m)."""
    out = {}
    for p in CORRIDOR["points"]:
        x, y = net.convertLonLat2XY(p["lon"], p["lat"])
        best = min(range(len(path)), key=lambda i: math.dist(path[i].getToNode().getCoord()[:2], (x, y)))
        out[p["id"]] = (best, math.dist(path[best].getToNode().getCoord()[:2], (x, y)))
    out[CORRIDOR["points"][0]["id"]] = (-1, 0.0)            # the trip starts before the first edge ends
    out[CORRIDOR["points"][-1]["id"]] = (len(path) - 1, 0.0)
    return out


def junction_nodes(net, path, radius=60.0):
    """Network nodes where the corridor meets each junction's cross roads: the path's nodes within `radius` m of the
    junction that join or split roads (divided roads split one junction into several nodes). [] where the corridor
    passes over the junction on a flyover."""
    pos = junction_positions(net, path)
    nodes = {}
    for p in CORRIDOR["points"]:
        if p["kind"] != "junction":
            continue
        i, _ = pos[p["id"]]
        x, y = net.convertLonLat2XY(p["lon"], p["lat"])
        group = []
        for k in range(max(0, i - 4), min(len(path), i + 5)):
            n = path[k].getToNode()
            elevated = any(len(pt) > 2 and pt[2] > 1 for e in path[k:k + 1] for pt in e.getShape(True))
            if not elevated and math.dist(n.getCoord()[:2], (x, y)) <= radius and (len(n.getIncoming()) >= 2 or len(n.getOutgoing()) >= 2):
                group.append(n)
        nodes[p["id"]] = list({n.getID(): n for n in group}.values())
    return nodes


def junction_groups(net):
    """Each junction's nodes on both carriageways: {junction_id: [nodes]} ([] where the corridor passes over)."""
    fwd, rev = junction_nodes(net, route(net)), junction_nodes(net, route(net, reverse=True))
    # where the forward trip passes over the junction (Biodiversity flyovers), so does the return trip
    return {j: list({n.getID(): n for n in fwd[j] + rev.get(j, [])}.values()) if fwd[j] else [] for j in fwd}


def rebuild(net_path: Path, out: Path, edit):
    """Export the network as plain XML, let `edit(prefix)` change the files, rebuild into `out`."""
    with tempfile.TemporaryDirectory() as tmp:
        p = f"{tmp}/plain"
        subprocess.run(["netconvert", "-s", str(net_path), "--plain-output-prefix", p], check=True, capture_output=True)
        edit(p)
        args = ["netconvert", "--node-files", f"{p}.nod.xml", "--edge-files", f"{p}.edg.xml", "--connection-files",
                f"{p}.con.xml", "--lefthand", "-o", str(out), "--tls.cycle.time", str(SIGNAL_CYCLE_S), "--tls.default-type", "static", "--tls.join", "--tls.join-dist", "45"]
        for kind, opt in (("tll", "--tllogic-files"), ("typ", "--type-files")):
            if Path(f"{p}.{kind}.xml").exists():
                args += [opt, f"{p}.{kind}.xml"]
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-800:])


def add_signals(net_path: Path):
    """Signals at every corridor junction the corridor crosses at ground level (OSM tags only 5). Label: assumed."""
    net = sumolib.net.readNet(str(net_path))
    nodes = {jid: g for jid, g in junction_groups(net).items() if g}
    ids = {n.getID() for g in nodes.values() for n in g}

    def edit(p):
        tree = ET.parse(f"{p}.nod.xml")
        for n in tree.getroot().iter("node"):
            if n.get("id") in ids and n.get("type") != "traffic_light":
                n.set("type", "traffic_light"); n.set("tlType", "static")
        tree.write(f"{p}.nod.xml")
    rebuild(net_path, net_path, edit)
    return {jid: len(g) for jid, g in nodes.items()}


if __name__ == "__main__":
    if sys.argv[1:] == ["signals"]:
        print("signals at:", add_signals(ROOT / "sim/corridor/corridor.net.xml"))
