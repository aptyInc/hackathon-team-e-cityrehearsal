"""Corridor network helpers: the route through the network, the network node of each corridor junction, and signals.

Used by build_network.sh (signals) and by the corridor runner and intervention templates (route, junction nodes).
"""
import heapq
import json
import math
import os
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
SIGNAL_CYCLE_S = 120   # assumed default cycle at the corridor's signalised junctions (main x minor: 100-150 s, s5)
CORRIDOR_GREEN_SHARE = 0.65  # assumed share of the green time for the corridor (signal_plans; main x minor: at least 65%, s5)
YELLOW_S = 4           # amber after each stage (docs/driver-behaviour.md s5, assumed)
# s5: junctions with 3+ busy approaches (TomTom: >= 1,000 veh/h each, estimated) run one approach at a time: here
# j02, j08, j09. Built (signal_plans) but OFF by default: in this single-file model each corridor direction then gets
# ~1/4 of a 150 s cycle, and the 2-3-lane corridor approaches at j02 and j08 gridlocked (delays of 5-15 min, leg j07-j08
# 4.6x TomTom) even at the old volumes. Turn on with CR_BIG_JUNCTIONS=j02,j08,j09 (needs recalibrating).
BIG_JUNCTIONS = {j for j in os.environ.get("CR_BIG_JUNCTIONS", "").split(",") if j}
BIG_CYCLE_S = 150      # cycle at the big junctions (s5, assumed)
RIGHT_TURN_S = 12      # protected right-turn phase for the corridor at main x minor junctions (s5, estimated)
MIN_GREEN_S = 10       # shortest green (s5: police let a green run from 10 s; assumed)
FREE_LEFT = os.environ.get("CR_FREE_LEFT", "1") != "0"   # s5: left-turners go in every phase, giving way (assumed)
FLYOVER_COST = 0.7     # route(): a metre on an existing flyover counts as 0.7 m: through traffic takes them (assumed;
                       # TomTom's fastest legs are exactly the flyover stretches)
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
    """Edges of the corridor trip (Lingampally -> Lakdikapul, or back): the shortest path through the network counting
    the distance across every junction it passes, then straightened (see _straighten). Counting the junctions puts
    the trip on the flyovers through traffic really uses (Gachibowli, Biodiversity, Shaikpet, Tolichowki, Masab
    Tank): by road length alone the ground roads under them look a few metres shorter."""
    if not reverse:
        a, b = edge_along(net, 1), edge_along(net, len(ROUTE_POINTS) - 3)
    else:   # the opposite carriageway: an edge near each end heading the other way
        a, b = _reverse_edge(net, len(ROUTE_POINTS) - 3), _reverse_edge(net, 1)
    if a is None or b is None:
        return []
    best, prev, heap, n = {a.getID(): a.getLength()}, {}, [(a.getLength(), 0, a)], 0
    while heap:
        d, _, e = heapq.heappop(heap)
        if e == b:
            path = [e]
            while path[-1].getID() in prev:
                path.append(prev[path[-1].getID()])
            return _straighten(path[::-1])
        if d > best.get(e.getID(), math.inf):
            continue
        end = e.getShape()[-1]
        for f in e.getAllowedOutgoing("passenger"):
            nd = d + f.getLength() * (FLYOVER_COST if flyover(f) else 1.0) + math.dist(end[:2], f.getShape()[0][:2])   # + across the junction
            if nd < best.get(f.getID(), math.inf):
                best[f.getID()], prev[f.getID()] = nd, e
                n += 1
                heapq.heappush(heap, (nd, n, f))
    return []


def flyover(e):
    """An existing flyover piece: OSM names it a flyover, or it runs at least 5 m up."""
    return "flyover" in (e.getName() or "").lower() or any(abs(pt[2]) >= 5 for pt in e.getShape3D())


def elevated(e):
    """True for a flyover (or underpass) piece: part of its shape is more than 1 m off the ground."""
    return any(abs(pt[2]) > 1 for pt in e.getShape3D())


def _straighten(path, slack=25.0, reach=6):
    """The shortest path leaves out the distance across each junction, so at Tolichowki a chain of tiny side pieces
    (with give-way turns) looked 1-2 m shorter than the main road, and the route took it. Wherever the path goes from
    one edge to another a few edges later, and fewer pieces join the two within `slack` m of the same length, take
    those (the main road)."""
    out, i = list(path), 0
    while i < len(out) - 2:
        for j in range(min(len(out) - 1, i + reach), i + 1, -1):
            if any(elevated(e) for e in out[i + 1:j]):
                continue                     # never swap a flyover for the road under it
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
            if n.getCoord3D()[2] <= 1 and math.dist(n.getCoord()[:2], (x, y)) <= radius and (len(n.getIncoming()) >= 2 or len(n.getOutgoing()) >= 2):
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
    made a single-lane bottleneck at j01, j03, j05-j07, j08, j10, j11 and near both ends. Also, where it meets other
    roads without a signal, OSM's road ranks made the corridor give way (at ~15 merges and splits). Now the corridor
    is the main road there, pieces narrower than 2 lanes get 2, and every lane of each route piece is linked on to the
    next piece, lane by lane (two lanes were squeezed into one at Tolichowki). Signal programs are regenerated (run
    signal_plans afterwards). Returns the number of (widened pieces, relinked route steps)."""
    net = sumolib.net.readNet(str(net_path))
    paths = [route(net), route(net, reverse=True)]
    # (not the pieces at the route's two ends: their shapes pick the route's first and last edge)
    widen = {e.getID(): 2 for p in paths for e in p[3:-2] if e.getLaneNumber() < 2}
    lanes = lambda e: widen.get(e.getID(), e.getLaneNumber())  # noqa: E731
    relink = {}         # (from, to) -> lane links replacing the existing ones
    for p in paths:
        for a, b in zip(p[1:-3], p[2:-2]):
            na, nb = lanes(a), lanes(b)
            linked = {(c.getFromLane().getIndex(), c.getToLane().getIndex()) for c in a.getConnections(b)}
            want = {(i, round(i * (nb - 1) / (na - 1)) if na > 1 else 0) for i in range(na)}   # lane by lane
            fans = len({f for f, _ in linked}) < len(linked)     # one lane feeds several: the others must give way
            if want - linked or (fans and linked != want):
                relink[(a.getID(), b.getID())] = sorted(want)

    on_path = {e.getID() for p in paths for e in p}
    top = max(e.getPriority() for e in net.getEdges()) + 1

    def edit(prefix):
        tree = ET.parse(f"{prefix}.edg.xml")
        for e in tree.getroot().iter("edge"):
            if e.get("id") in widen:
                e.set("numLanes", str(widen[e.get("id")]))
                for lane in e.findall("lane"):
                    e.remove(lane)
            if e.get("id") in on_path:      # the corridor is the main road where it meets others without a signal
                e.set("priority", str(top))
        tree.write(f"{prefix}.edg.xml")
        tree = ET.parse(f"{prefix}.con.xml")
        root = tree.getroot()
        for c in list(root):
            if c.tag == "connection" and (c.get("from"), c.get("to")) in relink:
                root.remove(c)
        for (a, b), links in relink.items():
            for i, j in links:
                ET.SubElement(root, "connection", **{"from": a, "to": b, "fromLane": str(i), "toLane": str(j)})
        for c in list(root):     # lane links on signals change: netconvert makes fresh programs
            if c.get("tl"):
                c.attrib.pop("tl"); c.attrib.pop("linkIndex", None); c.attrib.pop("linkIndex2", None)
        tree.write(f"{prefix}.con.xml")
        Path(f"{prefix}.tll.xml").write_text("<tlLogics/>\n")
    rebuild(net_path, net_path, edit)
    return len(widen), len(relink)


def signal_plans(net_path: Path, share=CORRIDOR_GREEN_SHARE, yellow=YELLOW_S):
    """Replace netconvert's guessed programs at the corridor junctions with the signal plans of docs/driver-behaviour.md
    section 5 (assumed). Every plan: `yellow` (4 s) amber after each green; the free left (left = the short turn in
    lefthand traffic) goes in every phase, giving way to traffic with a green (SUMO 'g').
      main x minor (j01, j05): the corridor both ways together (its right-turners wait for a gap in oncoming traffic,
          'g'), then a protected right-turn phase for the corridor (RIGHT_TURN_S, 12 s), then the side road;
          cycle SIGNAL_CYCLE_S (120 s); the corridor (with its right-turn phase) gets `share` of the green (>= 65%).
      big junctions with 3+ busy approaches (BIG_JUNCTIONS: j02, j08, j09): one approach at a time, so right-turners
          never face oncoming traffic; cycle BIG_CYCLE_S (150 s); the corridor's two approaches share `share` of the
          green, the cross roads the rest, equally (the doc shares green by traffic per lane: simplified).
    `share`: a number, or {junction id: share} with CORRIDOR_GREEN_SHARE elsewhere.
    Links that start inside a junction (the median gap of a divided road, the circulating lanes of Gachibowli Circle)
    never get a red: with their approach's green they have priority, otherwise they give way ('g'), so vehicles already
    in the junction can always clear it. Links merging into a lane another green link feeds give way (the corridor's
    own, else the straight-on one, keeps priority). Returns {tls id: jid}."""
    net = sumolib.net.readNet(str(net_path), withPrograms=True)
    fwd, rev = route(net), route(net, reverse=True)
    F, R = {e.getID() for e in fwd}, {e.getID() for e in rev}
    on_path = F | R
    owner = {c.getTLSID(): jid for jid, nodes in junction_groups(net).items() for n in nodes
             for e in n.getIncoming() for lane in e.getLanes() for c in lane.getOutgoing() if c.getTLSID()}
    links = {}                  # tls id -> {link index: {...}}
    for tls_id in owner:
        conns = net.getTLS(tls_id).getConnections()
        ids = {i.getEdge().getToNode().getID() for i, _, _ in conns}     # the nodes this signal controls
        for in_lane, out_lane, idx in conns:
            e = in_lane.getEdge()
            c = next((c for c in in_lane.getOutgoing() if c.getToLane() == out_lane), None)
            d = c.getDirection() if c is not None else "s"
            on = e.getID() in on_path and out_lane.getEdge().getID() in on_path
            links.setdefault(tls_id, {})[idx] = {
                "stage": "corridor" if e.getID() in on_path else "cross", "inner": e.getFromNode().getID() in ids,
                "approach": e.getID(), "tag": "fwd" if e.getID() in F else "rev" if e.getID() in R else None,
                # left-hand traffic: the free left is the short turn; right turns and U-turns cross oncoming traffic
                # (the corridor's own route never does: where the road bends at a junction, SUMO calls it a turn too)
                "free_left": FREE_LEFT and d in ("l", "L") and not on and out_lane.getEdge().getToNode().getID() not in ids, "right": d in ("r", "R", "t") and not on, "out": out_lane.getID(),
                "rank": 0 if on else 1 if d == "s" else 2}
    text = Path(net_path).read_text()

    def plan(m):     # only the tlLogic blocks change; the rest of the file stays byte for byte
        tl = ET.fromstring(m.group(0))
        k = links.get(tl.get("id"))
        if not k or not any(v["stage"] == "cross" and not v["inner"] for v in k.values()):
            return m.group(0)   # no cross road meets this signal (one carriageway's side): netconvert's plan stays
        n = len(tl.find("phase").get("state"))
        jid = owner[tl.get("id")]
        sh = share.get(jid, CORRIDOR_GREEN_SHARE) if isinstance(share, dict) else share
        L = lambda i: k.get(i, {"stage": "", "inner": True, "approach": None, "tag": None, "free_left": False, "right": False,  # noqa: E731
                                "out": None, "rank": 2})

        def merged(state):     # two 'G' links into one lane: the corridor (else straight-on) link keeps it, the rest give way
            state, best = list(state), {}
            for i in sorted((i for i in range(n) if state[i] == "G" and i in k), key=lambda i: k[i]["rank"]):
                if k[i]["out"] in best:
                    state[i] = "g"
                best.setdefault(k[i]["out"], i)
            return "".join(state)

        def phase(go, protected=lambda v: False):
            """State: 'G' for links `go` lets through (or 'g' when they cross oncoming traffic and are not
            `protected`), free lefts 'g' always, inner links 'g' when not going, the rest 'r'."""
            out = []
            for i in range(n):
                v = L(i)
                if go(v):
                    out.append("g" if v["right"] and not protected(v) else "G")
                elif v["free_left"] or v["inner"]:
                    out.append("g")
                else:
                    out.append("r")
            return merged("".join(out))

        def amber(state, nxt):
            """Links green now and red next get 'y'."""
            return "".join("y" if a in "Gg" and b == "r" else a for a, b in zip(state, nxt))

        if jid in BIG_JUNCTIONS:
            groups = []        # one phase per approach: corridor A->B, corridor B->A, then each cross road
            for tag in ("fwd", "rev"):
                if any(v["tag"] == tag and not v["inner"] for v in k.values()):
                    groups.append(("corridor", tag))
            for a in sorted({v["approach"] for v in k.values() if v["stage"] == "cross" and not v["inner"]}):
                groups.append(("cross", a))
            green = BIG_CYCLE_S - yellow * len(groups)
            n_corr = sum(g[0] == "corridor" for g in groups)
            n_cross = len(groups) - n_corr
            if n_corr and n_cross:
                durs = [max(MIN_GREEN_S, round(green * (sh / n_corr if g[0] == "corridor" else (1 - sh) / n_cross))) for g in groups]
            else:
                durs = [round(green / len(groups))] * len(groups)
            states = []
            for kind, key in groups:
                if kind == "corridor":   # the corridor's inner links of this direction go with it
                    states.append(phase(lambda v, key=key: v["tag"] == key, protected=lambda v: True))
                else:
                    states.append(phase(lambda v, key=key: v["approach"] == key and not v["inner"], protected=lambda v: True))
        else:
            right = any(v["stage"] == "corridor" and v["right"] for v in k.values())
            green = SIGNAL_CYCLE_S - yellow * (3 if right else 2)
            main = round(green * sh)
            prot = RIGHT_TURN_S if right else 0
            durs = [max(MIN_GREEN_S, main - prot)] + ([prot] if right else []) + [max(MIN_GREEN_S, green - main)]
            states = [phase(lambda v: v["stage"] == "corridor")]
            if right:
                states.append(phase(lambda v: v["stage"] == "corridor" and v["right"], protected=lambda v: True))
            states.append(phase(lambda v: v["stage"] == "cross"))
        phases = ""
        for i, (s, d) in enumerate(zip(states, durs)):
            nxt = states[(i + 1) % len(states)]
            phases += f'        <phase duration="{d}" state="{s}"/>\n        <phase duration="{yellow}" state="{amber(s, nxt)}"/>\n'
        return (f'<tlLogic id="{tl.get("id")}" type="static" programID="{tl.get("programID")}" offset="0">\n'
                f'{phases}    </tlLogic>')
    Path(net_path).write_text(re.sub(r"<tlLogic .*?</tlLogic>", plan, text, flags=re.S))
    return owner


if __name__ == "__main__":
    NET = ROOT / "sim/corridor/corridor.net.xml"
    if sys.argv[1:] == ["signals"]:      # build_network.sh, after netconvert
        print("signals at:", add_signals(NET))
        print("corridor lanes (widened pieces, relinked route steps):", corridor_lanes(NET))
        print("two-stage plans:", sorted(set(signal_plans(NET).values())))
    elif sys.argv[1:] == ["plans"]:
        print("two-stage plans:", sorted(set(signal_plans(NET).values())))
