"""Corridor intervention templates: network edits at the Lingampally -> Lakdikapul junctions (data/corridor/corridor.json).

apply(net_path, out, interventions) writes a copy of the corridor network with every intervention built in. Each
intervention is {"junction_id": "j07", "kind": "flyover", "params": {...}}; kinds follow C5
(contracts/corridor_result.schema.json). Params per kind (all optional):
    flyover / underpass  (not where the corridor already crosses on a flyover: Gachibowli, Biodiversity, Shaikpet,
                         Tolichowki, Masab Tank; a warning says so) lanes (each direction, default 2), speed_kmh (default 60, or the road's speed if faster),
                         length_m (whole structure; default: the junction's own span + 400 m, so the ramps start
                         and land ~200 m either side of the junction)
    signal_retime        cycle_s (40-240, default 120), corridor_green_share (alias main_share, 0.1-0.9, default 0.5):
                         share of the cycle's green time (cycle minus yellow/all-red) given to the phases that let the
                         corridor's through traffic into the junction
    widening             add_lanes (1-2, default 1), length_m (default 300, on the corridor either side of the junction)
    one_way              road (side road name or edge id; default the smallest two-way side road), direction ("in":
                         only traffic towards the junction, default; "out": only away), length_m (default 200)
    u_turn               not built yet (left out with a warning)
Method (as flyover.py): export the network as plain XML, edit it, rebuild once with netconvert (corridor_net.rebuild).
Everything is planned on the source network. Split road pieces keep their original edge ids on the side away from
the junction, so trips from the corridor's first edge to its last edge, and probes on those edges, still work.
The source network is never edited.

Usage (repo root, inside .venv):
    python sim/templates/corridor.py j07 flyover '{"lanes": 2}' --out /tmp/j07.net.xml
"""
import argparse
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import sumolib
from sumolib import geomhelper

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sim/corridor"))
import corridor_net as cn  # noqa: E402

KINDS = ("flyover", "underpass", "signal_retime", "widening", "one_way", "u_turn")
JUNCTIONS = {p["id"]: p for p in cn.CORRIDOR["points"] if p["kind"] == "junction"}
GRADE = ("flyover_", "underpass_")
ORDER = {"widening": 0, "one_way": 1, "signal_retime": 1, "flyover": 2, "underpass": 2}


def apply(net_path: Path, out: Path, interventions: list[dict]) -> list[str]:
    """Write a modified copy of the corridor network to `out` with all interventions applied. Returns warnings.
    Raises ValueError for an unknown junction or kind, or a param out of range."""
    for iv in interventions:
        if iv.get("junction_id") not in JUNCTIONS:
            raise ValueError(f"unknown junction {iv.get('junction_id')!r}; use one of {', '.join(JUNCTIONS)}")
        if iv.get("kind") not in KINDS:
            raise ValueError(f"unknown intervention kind {iv.get('kind')!r}; use one of {', '.join(KINDS)}")
    net = sumolib.net.readNet(str(net_path), withPrograms=True)
    ctx = {"net": net, "paths": {"fwd": cn.route(net), "rev": cn.route(net, reverse=True)}, "spans": [],
           "plans": [], "split": set(), "widened": set(), "grade": set()}
    ctx["groups"] = {tag: cn.junction_nodes(net, p) for tag, p in ctx["paths"].items()}
    edits, pending = [], []
    for iv in sorted(interventions, key=lambda iv: ORDER.get(iv["kind"], 9)):
        jid, kind = iv["junction_id"], iv["kind"]
        if kind not in TEMPLATES:
            pending.append((jid, kind, ["this template is not built yet; the intervention was left out"]))
            continue
        edit, notes = TEMPLATES[kind](ctx, jid, kind, iv.get("params") or {})
        if edit:
            edits.append(edit)
        pending.append((jid, kind, notes))     # an edit may still add notes while it runs
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    if not edits:        # nothing to build: the variant is the source network, byte for byte
        shutil.copyfile(net_path, out)
        return [f"{jid} {kind}: {n}" for jid, kind, notes in pending for n in notes]
    cn.rebuild(Path(net_path), Path(out), lambda prefix: [edit(prefix) for edit in edits])
    if ctx["plans"] and fit_lengths(Path(out), ctx["plans"]):
        cn.rebuild(Path(net_path), Path(out), lambda prefix: [edit(prefix) for edit in edits])
    warnings = [f"{jid} {kind}: {n}" for jid, kind, notes in pending for n in notes]
    if ctx["plans"]:
        warnings += check_route(Path(out), ctx["plans"])
    return warnings


def fit_lengths(net_path, plans):
    """The ground road's lane lengths leave out junction areas (and the new split points add two), so a structure
    measured end to end can look longer to the router than the road it replaces. Cap each structure at 97% of the
    built ground route between its ramps; True when a rebuild is needed."""
    net, changed = sumolib.net.readNet(str(net_path)), False
    for p in plans:
        ground = sum(net.getEdge(e).getLength() for e in [f"{p['up']}.{p['id']}", *p["bypassed"], f"{p['down']}.{p['id']}"])
        if p["length"] > 0.97 * ground:
            p["length"], changed = 0.97 * ground, True
    return changed


# ---------------------------------------------------------------- where the corridor meets a junction

def sides(ctx, jid):
    """For each direction ('fwd' A->B, 'rev' B->A): (path, i0, i1), path[i0] being the edge that enters the
    junction's node group and path[i1] the edge that leaves it. A direction is left out where the corridor does not
    cross the junction at ground level."""
    out = {}
    for tag, path in ctx["paths"].items():
        group = {n.getID() for n in ctx["groups"][tag].get(jid, [])}
        ins = [k for k, e in enumerate(path) if e.getToNode().getID() in group]
        outs = [k for k, e in enumerate(path) if e.getFromNode().getID() in group]
        if ins and outs and min(ins) < max(outs):
            out[tag] = (path, min(ins), max(outs))
    return out


def split_point(path, k, dist, upstream):
    """(edge index, offset from that edge's start) `dist` m upstream of path[k]'s end, or downstream of its start,
    at least 10 m from either end of the edge (stops at the corridor's first/last edge)."""
    step = -1 if upstream else 1
    while True:
        length = path[k].getLength()
        last = (k == 0) if upstream else (k == len(path) - 1)
        if (dist <= length - 10 and length >= 20) or last:
            off = min(max(dist, 10.0), max(length - 10.0, length / 2))
            return k, (length - off if upstream else off)
        dist -= length
        k += step


# ---------------------------------------------------------------- flyover / underpass

def existing_structure(ctx, jid, radius=80.0):
    """Name of the flyover the corridor already crosses junction `jid` on (from the network: a route piece named a
    flyover, or 5 m or more up, passing within `radius` m of the junction), or None."""
    p = JUNCTIONS[jid]
    xy = ctx["net"].convertLonLat2XY(p["lon"], p["lat"])
    near = [e for path in ctx["paths"].values() for e in path if cn.flyover(e)
            and geomhelper.distancePointToPolygon(xy, [q[:2] for q in e.getShape()], perpendicular=False) <= radius]
    named = [e.getName() for e in near if "flyover" in (e.getName() or "").lower()]   # the structure's own name first
    return named[0] if named else (near[0].getName() or "existing flyover") if near else None


def grade_separation(ctx, jid, kind, params):
    """Flyover (+6 m) or underpass (-6 m) carrying the corridor's through traffic past the junction, both ways.
    Cross and turning traffic keep using the ground junction. Returns (edit, warnings)."""
    lanes = int(params.get("lanes", 2))
    if not 1 <= lanes <= 4:
        raise ValueError(f"{kind} lanes must be 1-4, got {lanes}")
    if "speed_kmh" in params and not 20 <= float(params["speed_kmh"]) <= 100:
        raise ValueError(f"{kind} speed_kmh must be 20-100, got {params['speed_kmh']}")
    if "length_m" in params and not 100 <= float(params["length_m"]) <= 3000:
        raise ValueError(f"{kind} length_m must be 100-3000, got {params['length_m']}")
    found = sides(ctx, jid)
    if "fwd" not in found:
        on = existing_structure(ctx, jid)
        if on:
            return None, [f"{jid} already has a flyover: the corridor crosses {JUNCTIONS[jid]['name']} on the {on}; nothing built"]
        return None, [f"the corridor does not cross {jid} at ground level; nothing built"]
    if jid in ctx["grade"]:
        return None, [f"{jid} already gets a flyover or underpass in this variant; left out"]
    z = 6.0 if kind == "flyover" else -6.0
    plans, notes = [], []
    for tag, (path, i0, i1) in found.items():
        span = sum(path[k].getLength() for k in range(i0 + 1, i1))
        half = max(80.0, (float(params["length_m"]) - span) / 2) if "length_m" in params else 200.0
        for h in (half, half * 0.6, 80.0):     # shorten when it would run into another structure
            a, a_off = split_point(path, i0, h, upstream=True)
            b, b_off = split_point(path, i1, h, upstream=False)
            cum = [0.0]
            for e in path:
                cum.append(cum[-1] + e.getLength())
            lo, hi = cum[a] + a_off, cum[b] + b_off
            clash = any(t == tag and lo < h2 + 20 and l2 < hi + 20 for t, l2, h2 in ctx["spans"]) \
                or {path[a].getID(), path[b].getID()} & ctx["split"]
            if not clash:
                break
        if clash:
            notes.append(f"{tag}: overlaps another flyover/underpass in this variant; left out (use one longer structure)")
            continue
        if h < half:
            notes.append(f"{tag}: shortened to {hi - lo:.0f} m so it does not run into another flyover/underpass")
        if (a == 0 or b == len(path) - 1) and h == half:
            notes.append(f"{tag}: runs to the end of the corridor")
        ctx["spans"].append((tag, lo, hi))
        ctx["split"] |= {path[a].getID(), path[b].getID()}
        e_up, e_down = path[a], path[b]
        if {e_up.getID(), e_down.getID()} & ctx["widened"]:
            notes.append(f"{tag}: ramps sit on a widened road piece; lane links there may be uneven")
        ground_speed = max(path[k].getSpeed() for k in range(a, b + 1))
        speed = float(params["speed_kmh"]) / 3.6 if "speed_kmh" in params else max(60 / 3.6, ground_speed)
        # lane length of the ground route between the ramps (leaves out junction areas): the structure's length is
        # capped to it so routing by distance prefers the structure too
        ground = (e_up.getLength() - a_off) + sum(path[k].getLength() for k in range(a + 1, b)) + b_off
        shape = _deck_shape(path, a, a_off, b, b_off, z)
        length = min(geomhelper.polyLength([p[:2] for p in shape]), ground * 0.99)
        if e_up.getLaneNumber() < lanes:
            notes.append(f"{tag}: {lanes} lanes on the {kind} but the road before the ramp has {e_up.getLaneNumber()}")
        if e_down.getLaneNumber() < lanes:
            notes.append(f"{tag}: {lanes} {kind} lanes merge into {e_down.getLaneNumber()} at the landing "
                         f"({e_down.getName() or e_down.getID()}); build it with {e_down.getLaneNumber()} lanes or widen past the landing")
        if speed < ground_speed:
            notes.append(f"{tag}: {speed * 3.6:.0f} km/h is slower than the ground road ({ground_speed * 3.6:.0f} km/h); "
                         f"route choice may skip the {kind}")
        plans.append(dict(id=f"{kind}_{jid}_{tag}", up=e_up.getID(), up_off=a_off, down=e_down.getID(), down_off=b_off,
                          shape=shape, length=length, speed=speed, priority=e_up.getPriority() + 1,
                          name=e_up.getName() or "", bypassed=[path[k].getID() for k in range(a + 1, b)]))
    if not plans:
        return None, notes
    ctx["grade"].add(jid)
    ctx["plans"] += plans

    def edit(prefix):
        ups = {p["up"]: p for p in plans}
        downs = {p["down"]: p for p in plans}
        edg = ET.parse(f"{prefix}.edg.xml")
        root = edg.getroot()
        for e in root.iter("edge"):
            eid = e.get("id")
            if eid in ups:      # upstream piece keeps the id, the rest goes on to the junction
                p = ups[eid]
                p["up_lanes"] = int(e.get("numLanes", "1"))
                ET.SubElement(e, "split", pos=f"{p['up_off']:.1f}", id=f"{p['id']}_start", idBefore=eid, idAfter=f"{eid}.{p['id']}")
            if eid in downs:    # downstream piece keeps the id, the part from the junction lands on it
                p = downs[eid]
                p["down_lanes"] = int(e.get("numLanes", "1"))
                ET.SubElement(e, "split", pos=f"{p['down_off']:.1f}", id=f"{p['id']}_end", idBefore=f"{eid}.{p['id']}", idAfter=eid)
        for p in plans:
            ET.SubElement(root, "edge", id=p["id"], **{
                "from": f"{p['id']}_start", "to": f"{p['id']}_end", "numLanes": str(lanes), "speed": f"{p['speed']:.2f}",
                "priority": str(p["priority"]), "length": f"{p['length']:.1f}", "spreadType": "center",
                "name": f"{p['name']} {kind}".strip(), "disallow": "pedestrian bicycle tram rail_urban rail",
                "shape": " ".join(",".join(f"{c:.2f}" for c in pt) for pt in p["shape"])})
        edg.write(f"{prefix}.edg.xml")
        # connections at the old edge ends now belong to the pieces next to the junction: rename, so lanes and
        # signal link indices stay exactly as they were
        rename_from = {p["up"]: f"{p['up']}.{p['id']}" for p in plans}
        rename_to = {p["down"]: f"{p['down']}.{p['id']}" for p in plans}
        for part in ("con", "tll"):
            tree = ET.parse(f"{prefix}.{part}.xml")
            for c in tree.getroot().iter("connection"):
                if c.get("from") in rename_from:
                    c.set("from", rename_from[c.get("from")])
                if c.get("to") in rename_to:
                    c.set("to", rename_to[c.get("to")])
            if part == "con":
                for p in plans:
                    for a, b, fl, tl in _ramp_lanes(p, lanes):
                        ET.SubElement(tree.getroot(), "connection", **{"from": a, "to": b, "fromLane": str(fl), "toLane": str(tl)})
            tree.write(f"{prefix}.{part}.xml")
    return edit, notes


def _ramp_lanes(p, lanes):
    """Lane links at the ramp start and the landing (lane 0 is the kerb lane in left-hand traffic). Every ground lane
    carries on; the median-side lanes also lead up the ramp; the structure lands on the median-side lanes."""
    up, down, ground_up, ground_down = p["up"], p["down"], f"{p['up']}.{p['id']}", f"{p['down']}.{p['id']}"
    n, m = p["up_lanes"], p["down_lanes"]
    links = [(up, ground_up, i, i) for i in range(n)] + [(ground_down, down, i, i) for i in range(m)]
    k = min(lanes, n)                         # lanes that feed the ramp
    links += [(up, p["id"], n - k + j, lanes - k + j) for j in range(k)]
    links += [(p["id"], down, j, max(0, m - lanes + j)) for j in range(lanes)]   # more lanes than the road: they merge
    return links


def _deck_shape(path, a, a_off, b, b_off, z):
    """Plan view: the road between the ramps, simplified to a near-straight line. Height: 0 at both ends, z from 60 m in."""
    pts = []
    for k in range(a, b + 1):
        s = [p[:2] for p in path[k].getShape()]
        if k in (a, b):
            s = _cut(s, a_off if k == a else 0.0, b_off if k == b else geomhelper.polyLength(s))
        pts += [p for p in s if not pts or math.dist(p, pts[-1]) > 1]
    pts = _simplify(pts, 15.0)
    total = geomhelper.polyLength(pts)
    if len(pts) == 2:   # straight: add the tops of the two ramps so it rises and falls
        pts = [pts[0], geomhelper.positionAtShapeOffset(pts, min(60, total / 3)),
               geomhelper.positionAtShapeOffset(pts, max(total - 60, 2 * total / 3)), pts[1]]
    shaped, done = [], 0.0
    for i, p in enumerate(pts):
        done += math.dist(p, pts[i - 1]) if i else 0.0
        shaped.append((p[0], p[1], z * min(1.0, done / 60, (total - done) / 60)))
    return shaped


def _cut(shape, lo, hi):
    """Part of a polyline between two offsets."""
    out, done = [geomhelper.positionAtShapeOffset(shape, lo)], 0.0
    for i in range(1, len(shape)):
        done += math.dist(shape[i - 1], shape[i])
        if lo < done < hi:
            out.append(shape[i])
    out.append(geomhelper.positionAtShapeOffset(shape, hi))
    return [tuple(p) for p in out]


def _simplify(pts, tol):
    """Douglas-Peucker: drop points within `tol` m of the straight line."""
    if len(pts) < 3:
        return list(pts)
    d = [geomhelper.distancePointToLine(p, pts[0], pts[-1]) for p in pts[1:-1]]
    d = [x if x != geomhelper.INVALID_DISTANCE else math.dist(p, pts[0]) for x, p in zip(d, pts[1:-1])]
    i = max(range(len(d)), key=d.__getitem__)
    if d[i] <= tol:
        return [pts[0], pts[-1]]
    return _simplify(pts[:i + 2], tol)[:-1] + _simplify(pts[i + 1:], tol)


def check_route(net_path, plans):
    """Warnings when the corridor route (corridor_net.route, shortest A-B) skips a new structure, or when the
    fastest way from the road before its ramp to the road after its landing does not take it."""
    net = sumolib.net.readNet(str(net_path))
    notes, paths = [], {"fwd": cn.route(net), "rev": cn.route(net, reverse=True)}
    for tag, path in paths.items():
        if not path:
            notes.append(f"the {tag} corridor route is broken after the edit")
    for p in plans:
        tag = p["id"].rsplit("_", 1)[1]
        if paths[tag] and p["id"] not in {e.getID() for e in paths[tag]}:
            notes.append(f"{p['id']}: the {tag} corridor route does not use it")
        fast, _ = net.getFastestPath(net.getEdge(p["up"]), net.getEdge(p["down"]), vClass="passenger")
        if p["id"] not in {e.getID() for e in fast or []}:
            notes.append(f"{p['id']}: the fastest way past the junction does not use it")
    return notes


# ---------------------------------------------------------------- signal retime

def signal_retime(ctx, jid, kind, params):
    """New cycle and green split for every signal the corridor meets at the junction (both directions)."""
    cycle = float(params.get("cycle_s", cn.SIGNAL_CYCLE_S))
    share = float(params.get("corridor_green_share", params.get("main_share", 0.5)))
    if not 40 <= cycle <= 240:
        raise ValueError(f"signal_retime cycle_s must be 40-240, got {cycle:g}")
    if not 0.1 <= share <= 0.9:
        raise ValueError(f"signal_retime corridor_green_share must be 0.1-0.9, got {share:g}")
    net = ctx["net"]
    links, notes = {}, []     # tls id -> [(direction, link indices the corridor's through traffic needs)]
    for tag, (path, i0, i1) in sides(ctx, jid).items():
        need = {}
        for k in range(i0, i1):
            for c in path[k].getConnections(path[k + 1]):
                if c.getTLSID():
                    need.setdefault(c.getTLSID(), set()).add(c.getTLLinkIndex())
        for tls, idx in need.items():
            states = [p.state for prog in net.getTLS(tls).getPrograms().values() for p in prog.getPhases()]
            idx = {i for i in idx if not all(s[i] in "Gg" for s in states)}   # drop links that are always green
            if idx:
                links.setdefault(tls, []).append((tag, idx))
        if not any(tag == t for v in links.values() for t, _ in v):
            notes.append(f"{tag}: the corridor has no signal at this junction in this direction")
    if not links:
        on = existing_structure(ctx, jid)
        return None, [f"no signal on the corridor at {jid}" + (f" (it passes over on the {on})" if on else "") + "; nothing to retime"]

    planned = list(notes)

    def edit(prefix):    # may run twice (apply rebuilds once more when it fits flyover lengths)
        tree = ET.parse(f"{prefix}.tll.xml")
        notes[:] = planned
        for tl in tree.getroot().iter("tlLogic"):
            if tl.get("id") in links:
                notes.extend(_retime(tl, links[tl.get("id")], cycle, share))
        tree.write(f"{prefix}.tll.xml")
    return edit, notes


def _retime(tl, needs, cycle, share):
    """Rewrite one tlLogic: yellow/all-red phases keep their times, greens are split corridor/others by `share`.
    Corridor phases: those giving green to every link a direction's through traffic needs at this signal; where no
    single phase does (the corridor crosses in stages), every phase serving any of those links."""
    phases = list(tl.iter("phase"))
    green = [p for p in phases if any(ch in "Gg" for ch in p.get("state")) and "y" not in p.get("state").lower()]
    is_green = lambda p, idx, test: test(p.get("state")[i] in "Gg" for i in idx if i < len(p.get("state")))  # noqa: E731
    main = []
    for _, idx in needs:
        full = [p for p in green if is_green(p, idx, all)]
        main += [p for p in (full or [p for p in green if is_green(p, idx, any)]) if p not in main]
    other = [p for p in green if p not in main]
    avail = cycle - sum(float(p.get("duration")) for p in phases if p not in green)
    if not main:
        return [f"signal {tl.get('id')}: no phase gives the corridor green; left unchanged"]
    notes = [] if other else [f"signal {tl.get('id')}: every green phase serves the corridor; only the cycle changes"]
    for group, total in ((main, avail * (share if other else 1.0)), (other, avail * (1 - share))):
        old = sum(float(p.get("duration")) for p in group) or 1.0
        for p in group:
            p.set("duration", str(max(5, round(total * float(p.get("duration")) / old))))
    short = [p for p in green if float(p.get("duration")) < 10]
    if short:
        notes.append(f"signal {tl.get('id')}: {len(short)} phase(s) get under 10 s of green "
                     f"({', '.join(p.get('duration') + ' s' for p in short)}); cross and turning traffic will queue")
    real = sum(float(p.get("duration")) for p in phases)
    if abs(real - cycle) > 2:
        notes.append(f"signal {tl.get('id')}: cycle is {real:.0f} s, not {cycle:.0f} s (yellow times and 5 s minimum greens)")
    return notes


# ---------------------------------------------------------------- widening (stretch)

def widening(ctx, jid, kind, params):
    """Extra lanes on the corridor's edges within `length_m` either side of the junction, both directions.
    Signals there get a fresh plan from netconvert (same 120 s default type), since their lane links change."""
    net = ctx["net"]
    add = int(params.get("add_lanes", 1))
    reach = float(params.get("length_m", 300))
    if not 1 <= add <= 2:
        raise ValueError(f"widening add_lanes must be 1-2, got {add}")
    found = sides(ctx, jid)
    if not found:
        return None, [f"the corridor does not cross {jid} at ground level; nothing to widen"]
    edges = set()
    for tag, (path, i0, i1) in found.items():
        for start, step in ((i0, -1), (i1, 1)):
            k, done = start, 0.0
            while 0 <= k < len(path) and done < reach:
                edges.add(path[k].getID())
                done += path[k].getLength()
                k += step
        edges.update(path[k].getID() for k in range(i0, i1 + 1))
    edges -= ctx["widened"]
    ctx["widened"] |= edges
    tls = {c.getTLSID() for e in edges for cs in net.getEdge(e).getOutgoing().values() for c in cs if c.getTLSID()}
    tls |= {c.getTLSID() for e in edges for f, cs in net.getEdge(e).getIncoming().items() for c in cs if c.getTLSID()}
    notes = [f"signal plan re-generated (default {cn.SIGNAL_CYCLE_S} s) at {', '.join(sorted(tls))}"] if tls else []

    def edit(prefix):
        edg = ET.parse(f"{prefix}.edg.xml")
        for e in edg.getroot().iter("edge"):
            if e.get("id") in edges:
                n = int(e.get("numLanes", "1"))
                e.set("numLanes", str(n + add))
                lanes = e.findall("lane")
                for i in range(add):   # new lanes copy the outermost one
                    if lanes:
                        new = ET.SubElement(e, "lane", dict(lanes[-1].attrib))
                        new.set("index", str(n + i))
                        for child in lanes[-1]:
                            new.append(child)
        edg.write(f"{prefix}.edg.xml")
        con = ET.parse(f"{prefix}.con.xml")
        # netconvert redoes every lane link out of the widened edges and out of the edges feeding them (an edge with
        # some links loaded gets no computed ones, so clear all of its links)
        touched = edges | {c.get("from") for c in con.getroot().iter("connection") if c.get("to") in edges}
        for c in list(con.getroot()):
            if c.tag == "connection" and c.get("from") in touched:
                con.getroot().remove(c)
        con.write(f"{prefix}.con.xml")
        tll = ET.parse(f"{prefix}.tll.xml")
        for c in list(tll.getroot()):    # signals whose lane links change: netconvert makes a new plan
            if c.get("id") in tls or c.get("tl") in tls:
                tll.getroot().remove(c)
        tll.write(f"{prefix}.tll.xml")
    return edit, notes


# ---------------------------------------------------------------- one-way side road (stretch)

def one_way(ctx, jid, kind, params):
    """A side road at the junction becomes one-way for vehicles for ~`length_m` m: `direction` "in" keeps only the
    traffic driving towards the junction, "out" only the traffic driving away. The closed carriageway stays open to
    pedestrians, so lane links and signal programs keep their shape (retime separately to use the freed green)."""
    net = ctx["net"]
    direction, reach = params.get("direction", "in"), float(params.get("length_m", 200))
    if direction not in ("in", "out"):
        raise ValueError(f"one_way direction must be 'in' or 'out', got {direction!r}")
    group = {n.getID() for g in ctx["groups"].values() for n in g.get(jid, [])}
    corridor_edges = {e.getID() for p in ctx["paths"].values() for e in p}
    nodes = [net.getNode(n) for n in group]
    side = {"in": [e for n in nodes for e in n.getIncoming() if e.getFromNode().getID() not in group],
            "out": [e for n in nodes for e in n.getOutgoing() if e.getToNode().getID() not in group]}
    side = {k: [e for e in v if e.getID() not in corridor_edges and e.allows("passenger")] for k, v in side.items()}
    road_of = lambda e: e.getName() or e.getID().lstrip("-").split("#")[0]  # noqa: E731
    roads = sorted({road_of(e) for v in side.values() for e in v})
    names = {road_of(path[k]) for path, i0, i1 in sides(ctx, jid).values() for k in range(max(0, i0 - 3), min(len(path), i1 + 4))}
    two_way = [r for r in roads if r not in names and all(any(road_of(e) == r for e in v) for v in side.values())]
    if not params.get("road") and not two_way:
        return None, [f"no two-way side road at {jid}; nothing to make one-way"]
    want = params.get("road") or min(two_way, key=lambda r: sum(e.getLaneNumber() for v in side.values() for e in v if road_of(e) == r))
    if want not in roads and not any(e.getID() == want for v in side.values() for e in v):
        raise ValueError(f"one_way road {want!r} is not a side road at {jid}; use one of {', '.join(roads)}")
    closed = [e for e in side["out" if direction == "in" else "in"] if want in (road_of(e), e.getID())]
    if not closed:
        return None, [f"{want} already carries traffic only {'towards' if direction == 'in' else 'away from'} {jid}"]
    shut = set()
    for e in closed:     # follow the closed carriageway away from the junction for `reach` m
        done = 0.0
        while e is not None and done < reach and e.getID() not in corridor_edges:
            shut.add(e.getID())
            done += e.getLength()
            nxt = [x for x in (e.getOutgoing() if direction == "in" else e.getIncoming()) if road_of(x) == road_of(e)]
            e = nxt[0] if len(nxt) == 1 else None
    notes = [f"{want} is one-way {'towards' if direction == 'in' else 'away from'} the junction for {reach:.0f} m "
             f"(edges {', '.join(sorted(shut))}); traffic the other way must find another road"]

    def edit(prefix):
        edg = ET.parse(f"{prefix}.edg.xml")
        for e in edg.getroot().iter("edge"):
            if e.get("id") in shut:
                for el in [e, *e.findall("lane")]:
                    el.attrib.pop("disallow", None)
                    el.attrib.pop("allow", None)
                e.set("allow", "pedestrian")
        edg.write(f"{prefix}.edg.xml")
    return edit, notes


TEMPLATES = {"flyover": grade_separation, "underpass": grade_separation, "signal_retime": signal_retime,
             "widening": widening, "one_way": one_way}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build a corridor variant with one intervention")
    ap.add_argument("junction_id"); ap.add_argument("kind"); ap.add_argument("params", nargs="?", default="{}")
    ap.add_argument("--net", default=str(ROOT / "sim/corridor/corridor.net.xml"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    for w in apply(Path(a.net), Path(a.out), [{"junction_id": a.junction_id, "kind": a.kind, "params": json.loads(a.params)}]):
        print("WARNING:", w)
    print("built", a.out)
