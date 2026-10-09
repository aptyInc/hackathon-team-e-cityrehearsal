"""Corridor network helpers: the route through the network, the network node of each corridor junction, and signals.

Used by build_network.sh (signals) and by the corridor runner and intervention templates (route, junction nodes).
"""
import json
import math
import re
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
CORRIDOR_GREEN_SHARE = 0.6   # assumed share of the green time for the corridor's stage (signal_plans)
YELLOW_S = 4           # amber after each stage (assumed)
INNER_WAIT = "g"       # links inside a junction outside their own stage: "g" give way, "r" wait for their stage


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
    """Edges of the corridor trip (Lingampally -> Lakdikapul, or back): the shortest path through the network, then
    straightened (see _straighten)."""
    if not reverse:
        a, b = edge_along(net, 1), edge_along(net, len(ROUTE_POINTS) - 3)
    else:   # the opposite carriageway: an edge near each end heading the other way
        a, b = _reverse_edge(net, len(ROUTE_POINTS) - 3), _reverse_edge(net, 1)
    path, _ = net.getShortestPath(a, b, vClass="passenger")
    return _straighten(path or [])


def _straighten(path, slack=25.0, reach=6):
    """The shortest path leaves out the distance across each junction, so at Tolichowki a chain of tiny side pieces
    (with give-way turns) looked 1-2 m shorter than the main road, and the route took it. Wherever the path goes from
    one edge to another a few edges later, and fewer pieces join the two within `slack` m of the same length, take
    those (the main road)."""
    out, i = list(path), 0
    while i < len(out) - 2:
        for j in range(min(len(out) - 1, i + reach), i + 1, -1):
            have = sum(e.getLength() for e in out[i + 1:j])
            alt = _fewer_pieces(out[i], out[j], j - i - 2, have + slack)
            if alt is not None:
                out[i + 1:j] = alt
                break
        i += 1
    return out


def _fewer_pieces(a, b, most, max_len):
    """Edges strictly between a and b: at most `most` of them, total length <= max_len (fewest first), or None."""
    frontier = [(a, [])]
    for _ in range(most + 1):
        nxt = []
        for e, mid in frontier:
            for f in e.getAllowedOutgoing("passenger"):
                if f == b:
                    return mid
                if len(mid) < most and sum(x.getLength() for x in mid) + f.getLength() <= max_len and f not in mid:
                    nxt.append((f, mid + [f]))
        frontier = nxt
    return None


def _reverse_edge(net, i):
    (la, lo), (la2, lo2) = ROUTE_POINTS[min(i + 1, len(ROUTE_POINTS) - 1)], ROUTE_POINTS[i]
    x, y = net.convertLonLat2XY(lo, la); x2, y2 = net.convertLonLat2XY(lo2, la2)
    want = math.atan2(y2 - y, x2 - x)
    cands = [(e, d) for e, d in net.getNeighboringEdges(x, y, 60) if e.allows("passenger")
             and abs(math.remainder(_angle(e) - want, 2 * math.pi)) < math.radians(75)]
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


def corridor_lanes(net_path: Path):
    """Give the corridor its full width all the way: OSM leaves some short connector pieces on the route with one lane,
    and at some nodes only one lane of the corridor is linked to the next piece of the route (the rest turn off), which
    made a single-lane bottleneck at j01, j03, j05-j07, j08, j10, j11 and near both ends. Pieces narrower than 2 lanes
    get 2; every lane of each route piece is linked on to the next piece, lane by lane (two lanes squeezed into one at Tolichowki). Signal programs are regenerated (run
    signal_plans afterwards). Returns the number of (widened pieces, added lane links)."""
    net = sumolib.net.readNet(str(net_path))
    paths = [route(net), route(net, reverse=True)]
    # (not the pieces at the route's two ends: their shapes pick the route's first and last edge)
    widen = {e.getID(): 2 for p in paths for e in p[3:-2] if e.getLaneNumber() < 2}
    lanes = lambda e: widen.get(e.getID(), e.getLaneNumber())  # noqa: E731
    add = []
    for p in paths:
        for a, b in zip(p[2:-3], p[3:-2]):
            na, nb = lanes(a), lanes(b)
            linked = {(c.getFromLane().getIndex(), c.getToLane().getIndex()) for c in a.getConnections(b)}
            want = {(i, round(i * (nb - 1) / (na - 1)) if na > 1 else 0) for i in range(na)}   # lane by lane
            add += [(a.getID(), b.getID(), i, j) for i, j in sorted(want - linked)]

    def edit(prefix):
        tree = ET.parse(f"{prefix}.edg.xml")
        for e in tree.getroot().iter("edge"):
            if e.get("id") in widen:
                e.set("numLanes", str(widen[e.get("id")]))
                for lane in e.findall("lane"):
                    e.remove(lane)
        tree.write(f"{prefix}.edg.xml")
        tree = ET.parse(f"{prefix}.con.xml")
        root = tree.getroot()
        for a, b, i, j in add:
            ET.SubElement(root, "connection", **{"from": a, "to": b, "fromLane": str(i), "toLane": str(j)})
        for c in list(root):     # lane links on signals change: netconvert makes fresh programs
            if c.get("tl"):
                c.attrib.pop("tl"); c.attrib.pop("linkIndex", None); c.attrib.pop("linkIndex2", None)
        tree.write(f"{prefix}.con.xml")
        Path(f"{prefix}.tll.xml").write_text("<tlLogics/>\n")
    rebuild(net_path, net_path, edit)
    return len(widen), len(add)


def signal_plans(net_path: Path, share=CORRIDOR_GREEN_SHARE, yellow=YELLOW_S):
    """Replace netconvert's guessed programs at the corridor junctions with a plain two-stage plan (assumed):
    stage 1 the corridor's approaches go (both directions), stage 2 the cross roads' approaches go, `yellow` s amber
    after each; the corridor gets `share` of the green time (a number, or {junction id: share} with the default
    elsewhere). Links that start inside a junction (the median gap of a
    divided road, the circulating lanes of Gachibowli Circle) never get a red: in their own stage they have priority,
    in the other stage they give way (SUMO's 'g') to traffic with a green, so vehicles already in the junction can always
    clear it. Turns across oncoming traffic also give way.
    netconvert's own plans for these clusters (up to 10 stages at j03, 6 at j07, 8 s ambers) left the corridor about a
    third of the cycle and stopped vehicles inside the junction, which gridlocked the corridor. Returns {tls id: jid}."""
    net = sumolib.net.readNet(str(net_path), withPrograms=True)
    fwd, rev = route(net), route(net, reverse=True)
    on_path = {e.getID() for e in fwd + rev}
    owner = {c.getTLSID(): jid for jid, nodes in junction_groups(net).items() for n in nodes
             for e in n.getIncoming() for lane in e.getLanes() for c in lane.getOutgoing() if c.getTLSID()}
    links = {}                  # tls id -> {link index: (kind, gives way)}
    for tls_id in owner:
        conns = net.getTLS(tls_id).getConnections()
        ids = {i.getEdge().getToNode().getID() for i, _, _ in conns}     # the nodes this signal controls
        for in_lane, out_lane, idx in conns:
            e = in_lane.getEdge()
            c = next((c for c in in_lane.getOutgoing() if c.getToLane() == out_lane), None)
            stage = "corridor" if e.getID() in on_path else "cross"
            inner = e.getFromNode().getID() in ids
            # left-hand traffic: right turns and U-turns cross oncoming traffic and give way; the corridor's own
            # route never does (where the road bends right at a junction, SUMO calls it a turn too)
            across = c is not None and c.getDirection() in ("r", "t") and not (e.getID() in on_path and out_lane.getEdge().getID() in on_path)
            links.setdefault(tls_id, {})[idx] = (stage, inner, across)
    green = (SIGNAL_CYCLE_S - 2 * yellow)
    text = Path(net_path).read_text()

    def plan(m):     # only the tlLogic blocks change; the rest of the file stays byte for byte
        tl = ET.fromstring(m.group(0))
        k = links.get(tl.get("id"))
        if not k or not any(stage == "cross" and not inner for stage, inner, _ in k.values()):
            return m.group(0)   # no cross road meets this signal (one carriageway's side): netconvert's plan stays
        n = len(tl.find("phase").get("state"))
        sh = share.get(owner[tl.get("id")], CORRIDOR_GREEN_SHARE) if isinstance(share, dict) else share
        durations = (round(green * sh), yellow, green - round(green * sh), yellow)

        def go(s, i):
            stage, inner, across = k.get(i, ("", True, True))
            return ("g" if across else "G") if stage == s else INNER_WAIT if inner else "r"

        def amber(s, i):
            stage, inner, _ = k.get(i, ("", True, True))
            return "y" if stage == s and (not inner or INNER_WAIT == "r") else go(s, i)
        states = [f(stage) for stage in ("corridor", "cross") for f in
                  (lambda s: "".join(go(s, i) for i in range(n)), lambda s: "".join(amber(s, i) for i in range(n)))]
        phases = "".join(f'        <phase duration="{d}" state="{s}"/>\n' for s, d in zip(states, durations))
        return (f'<tlLogic id="{tl.get("id")}" type="static" programID="{tl.get("programID")}" offset="0">\n'
                f'{phases}    </tlLogic>')
    Path(net_path).write_text(re.sub(r"<tlLogic .*?</tlLogic>", plan, text, flags=re.S))
    return owner


if __name__ == "__main__":
    NET = ROOT / "sim/corridor/corridor.net.xml"
    if sys.argv[1:] == ["signals"]:      # build_network.sh, after netconvert
        print("signals at:", add_signals(NET))
        print("corridor lanes (widened pieces, added lane links):", corridor_lanes(NET))
        print("two-stage plans:", sorted(set(signal_plans(NET).values())))
    elif sys.argv[1:] == ["plans"]:
        print("two-stage plans:", sorted(set(signal_plans(NET).values())))
