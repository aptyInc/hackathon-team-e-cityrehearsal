"""Flyover template: build a variant of the YMCA Circle network with an east-west flyover over the roundabout.

C3 params (contracts/variant_spec.schema.json):
    lanes      lanes on the flyover, each direction (default 3)
    length_m   approximate length; ramps start and land length_m / 2 from the circle centre (default 400)
    axis       only "east_west" for now: Raja Bahadur Venkata Rama Reddy Marg <-> Narayanguda Main Road,
               the busiest straight-through axis in TomTom's morning data (81% of the east road goes straight)
Method (sim/templates/README.md): export the baseline as plain XML, split the four road pieces where the ramps
start and land, add one flyover edge per direction, drop the affected lane connections and rebuild, so netconvert
creates fresh ones. The baseline network and the traffic file are never edited.

Design check: a flyover with more lanes than the road it lands on forces a lane drop at the landing
(the Barapullah Phase-III problem). The check reports it and suggests the extension that removes it.

Usage (repo root, inside .venv):
    python sim/templates/flyover.py --lanes 3 --length_m 400 --out sim/out/ymca_flyover.net.xml
"""
import argparse, json, math, subprocess, sys, tempfile, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sim/scripts"))
import build_demand as bd  # noqa: E402  (shared helpers: approach matching, road walking)
import sumolib  # noqa: E402

BASE = ROOT / "sim/networks/ymca.net.xml"
AXES = {"east_west": [  # (approach the ramp leaves from, exit it lands on, direction label)
    ("Raja Bahadur Venkata Rama Reddy Marg West Bound", "YMCA to Ramkoti Road West Bound", "wb"),
    ("YMCA to Ramkoti Road East Bound", "Raja Bahadur Venkata Rama Reddy Marg East Bound", "eb")]}


def point_on_road(net, centre, edge, distance, backwards):
    """Edge and offset along it where the road is `distance` metres from the circle centre."""
    e, seen = edge, set()
    while True:
        a, b = (e.getFromNode(), e.getToNode())
        da = math.dist(a.getCoord()[:2], centre); db = math.dist(b.getCoord()[:2], centre)
        near, far = (db, da) if backwards else (da, db)
        if far >= distance > near and e.getLength() > 10:
            frac = (distance - near) / (far - near)
            pos = e.getLength() * (1 - frac) if backwards else e.getLength() * frac
            return e, max(5.0, min(e.getLength() - 5.0, pos))
        seen.add(e.getID())
        nxt = [x for x in (e.getIncoming() if backwards else e.getOutgoing()) if x.getID() not in seen
               and (x.getFromNode() != e.getToNode() if backwards else x.getToNode() != e.getFromNode())]
        nxt = [x for x in nxt if abs(math.remainder(bd.angle(x) - bd.angle(e), 2 * math.pi)) < math.radians(80)]
        if not nxt:
            raise SystemExit(f"road from {edge.getID()} ends before {distance} m")
        e = min(nxt, key=lambda x: abs(math.remainder(bd.angle(x) - bd.angle(e), 2 * math.pi)))


def build(lanes=3, length_m=400, axis="east_west", out=ROOT / "sim/out/ymca_flyover.net.xml"):
    net = sumolib.net.readNet(str(BASE))
    definition = json.loads((ROOT / "data/tomtom/junction/ymca_definition.json").read_text())
    ins, outs = bd.approach_edges(net, definition)
    centre = net.convertLonLat2XY(*definition["rawJunction"]["geometry"]["coordinates"])
    splits, flyovers, checks = {}, [], []
    for approach, exit_name, tag in AXES[axis]:
        up_edge, up_pos = point_on_road(net, centre, ins[approach], length_m / 2, backwards=True)
        down_edge, down_pos = point_on_road(net, centre, outs[exit_name], length_m / 2, backwards=False)
        start, end = f"flyover_{tag}_start", f"flyover_{tag}_end"
        # keep the original edge id on the part the traffic file uses: upstream part of an approach (where
        # vehicles enter), downstream part of an exit (where they leave), so every variant runs the same traffic
        splits.setdefault(up_edge.getID(), []).append((up_pos, start, "before"))
        splits.setdefault(down_edge.getID(), []).append((down_pos, end, "after"))
        flyovers.append((f"flyover_{tag}", start, end, exit_name))
        checks.append((f"flyover_{tag}", exit_name, down_edge))
    with tempfile.TemporaryDirectory() as tmp:
        p = f"{tmp}/plain"
        subprocess.run(["netconvert", "-s", str(BASE), "--plain-output-prefix", p], check=True, capture_output=True)
        edg = ET.parse(f"{p}.edg.xml"); root = edg.getroot()
        for e in root.iter("edge"):
            for pos, node, keep in sorted(splits.get(e.get("id"), [])):
                eid = e.get("id")
                ids = {"idBefore": eid, "idAfter": f"{eid}_ramp"} if keep == "before" else {"idBefore": f"{eid}_landing", "idAfter": eid}
                ET.SubElement(e, "split", pos=f"{pos:.1f}", id=node, **ids)
        for fid, start, end, _ in flyovers:
            ET.SubElement(root, "edge", id=fid, **{"from": start, "to": end, "numLanes": str(lanes), "speed": "13.89",
                                                    "priority": "13", "type": "highway.primary", "name": "YMCA Flyover",
                                                    "spreadType": "center", "width": "3.3"})
        edg.write(f"{p}.edg.xml")
        con = ET.parse(f"{p}.con.xml"); croot = con.getroot()
        touched = set(splits) | {c.get("from") for c in croot if c.tag == "connection" and c.get("to") in splits}
        for c in list(croot):
            if c.tag == "connection" and c.get("from") in touched:  # only outgoing: see apply_widths.py
                croot.remove(c)
        # netconvert does not wire the new flyover by itself: at each ramp start give both ways out (stay on
        # the road to the circle, or go up), at each landing both ways in. Lanes are assigned by netconvert.
        for edge_id, items in splits.items():
            for _, node, keep in items:
                if keep == "before":
                    fid = node.replace("_start", "")
                    ET.SubElement(croot, "connection", **{"from": edge_id, "to": f"{edge_id}_ramp"})
                    ET.SubElement(croot, "connection", **{"from": edge_id, "to": fid})
                else:  # landing: the road from the circle and the flyover both continue onto the original road
                    fid = node.replace("_end", "")
                    ET.SubElement(croot, "connection", **{"from": f"{edge_id}_landing", "to": edge_id})
                    ET.SubElement(croot, "connection", **{"from": fid, "to": edge_id})
        con.write(f"{p}.con.xml")
        args = ["netconvert", "--node-files", f"{p}.nod.xml", "--edge-files", f"{p}.edg.xml", "--connection-files",
                f"{p}.con.xml", "--lefthand", "-o", str(out)]
        for kind, opt in (("tll", "--tllogic-files"), ("typ", "--type-files")):
            if Path(f"{p}.{kind}.xml").exists():
                args += [opt, f"{p}.{kind}.xml"]
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(args, check=True, capture_output=True)
    return out, design_check(Path(out), lanes)


def design_check(path, lanes):
    """Warn when a flyover lands on a road with fewer lanes (forced lane drop)."""
    net = sumolib.net.readNet(str(path))
    warnings = []
    for e in net.getEdges():
        if not e.getID().startswith("flyover_"):
            continue
        landing = [x for x in e.getOutgoing()]
        for x in landing:
            drop = e.getLaneNumber() - x.getLaneNumber()
            if drop > 0:
                ext, total = [], 0.0
                y = x
                while y.getLaneNumber() < e.getLaneNumber() and total < 1500:
                    ext.append(y); total += y.getLength()
                    nxt = [z for z in y.getOutgoing() if z.getToNode() != y.getFromNode()]
                    if not nxt: break
                    y = max(nxt, key=lambda z: z.getLaneNumber())
                warnings.append({"flyover": e.getID(), "lanes": e.getLaneNumber(), "lands_on": x.getID(),
                                 "landing_lanes": x.getLaneNumber(), "message":
                                 f"{e.getID()}: {e.getLaneNumber()} lanes merge into {x.getLaneNumber()} at the landing "
                                 f"({x.getName() or x.getID()}), and the road stays {x.getLaneNumber()} lanes for at least "
                                 f"{round(total, -1):.0f} m. Add a lane past the landing (test 400 m) or build the flyover "
                                 f"with {x.getLaneNumber()} lanes."})
    return warnings


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanes", type=int, default=3); ap.add_argument("--length_m", type=float, default=400)
    ap.add_argument("--axis", default="east_west"); ap.add_argument("--out", default=str(ROOT / "sim/out/ymca_flyover.net.xml"))
    a = ap.parse_args()
    out, warnings = build(a.lanes, a.length_m, a.axis, a.out)
    print(f"built {Path(out).relative_to(ROOT)}")
    for w in warnings:
        print("DESIGN WARNING:", w["message"])
    if not warnings:
        print("design check: no lane drop at the landings")
