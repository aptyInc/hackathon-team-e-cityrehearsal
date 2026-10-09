"""Apply numLanes, width and speed from an .edg.xml patch and let netconvert recompute lane connections.

Patching a built network directly keeps its old connections, so a new third lane would lead nowhere.
Instead: export the network as plain XML, set numLanes/width on the listed edges, drop every connection
of those edges and of the edges feeding them, and rebuild from the plain files so netconvert creates fresh connections.
Usage: python apply_widths.py <net.xml> <patch.edg.xml>
"""
import subprocess, sys, tempfile, xml.etree.ElementTree as ET
from pathlib import Path

net, patch = Path(sys.argv[1]), Path(sys.argv[2])
widen = {e.get("id"): e for e in ET.parse(patch).getroot().iter("edge")}
with tempfile.TemporaryDirectory() as tmp:
    prefix = f"{tmp}/plain"
    subprocess.run(["netconvert", "-s", str(net), "--plain-output-prefix", prefix], check=True, capture_output=True)
    edg = ET.parse(f"{prefix}.edg.xml")
    for e in edg.getroot().iter("edge"):
        if e.get("id") in widen:
            for lane in list(e.findall("lane")):
                e.remove(lane)  # per-lane overrides would pin the old lane count
            for attr in ("numLanes", "width", "speed"):
                if widen[e.get("id")].get(attr):
                    e.set(attr, widen[e.get("id")].get(attr))
    edg.write(f"{prefix}.edg.xml")
    con = ET.parse(f"{prefix}.con.xml"); root = con.getroot()
    # netconvert computes no further connections for an edge that has any loaded connection, so clear ALL
    # connections of every edge that touches a widened edge, not only the ones to or from it.
    touched = set(widen) | {c.get("from") for c in root if c.tag == "connection" and c.get("to") in widen}
    for c in list(root):
        if c.tag == "connection" and c.get("from") in touched:
            root.remove(c)
    con.write(f"{prefix}.con.xml")
    args = ["netconvert", "--node-files", f"{prefix}.nod.xml", "--edge-files", f"{prefix}.edg.xml",
            "--connection-files", f"{prefix}.con.xml", "--lefthand", "-o", str(net)]
    for kind, opt in (("tll", "--tllogic-files"), ("typ", "--type-files")):
        if Path(f"{prefix}.{kind}.xml").exists():
            args += [opt, f"{prefix}.{kind}.xml"]
    subprocess.run(args, check=True)
print(f"widened {len(widen)} edges in {net} and rebuilt their lane connections")
