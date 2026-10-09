"""Run the same baseline traffic through several networks and compare (Scenarios / Simulation).

Usage (repo root, inside .venv): python sim/scripts/compare_variants.py [net.xml ...]
Default: baseline vs sim/out/ymca_flyover.net.xml (build it with python sim/templates/flyover.py).
Prints trips done, stuck vehicles, teleports, average speed, time lost per trip, vehicles on the flyover,
and speeds on the landing roads (the lane-drop check).
"""
import subprocess, sys, re, xml.etree.ElementTree as ET
sys.path.insert(0, "sim/scripts")
def run(net, scale, tag):
    subprocess.run([sys.executable, "sim/scripts/build_demand.py", "--scale", str(scale)], check=True, capture_output=True)
    open("sim/out/cmp.add.xml", "w").write(f'<additional><edgeData id="h" file="{tag}.edgedata.xml" begin="600" end="4200"/></additional>')
    p = subprocess.run(["sumo", "-n", net, "-r", "sim/demand/ymca_baseline.rou.xml", "-a", "sim/out/cmp.add.xml", "--lateral-resolution", "0.3",
                        "--end", "4200", "--no-step-log", "--duration-log.statistics", "--time-to-teleport", "300", "--seed", "42",
                        "--tripinfo-output", f"sim/out/{tag}.tripinfo.xml"], capture_output=True, text=True)
    s = dict(re.findall(r"\n (Inserted|Running|Waiting|Teleports|Speed|TimeLoss): ([0-9.]+)", p.stdout + p.stderr))
    trips = list(ET.parse(f"sim/out/{tag}.tripinfo.xml").getroot().iter("tripinfo"))
    ed = {e.get("id"): e for e in ET.parse(f"sim/out/{tag}.edgedata.xml").getroot().iter("edge")}
    fly = sum(int(float(ed[e].get("entered", 0))) for e in ed if e.startswith("flyover_"))
    land = {e: round(float(ed[e].get("speed", 0)) * 3.6, 1) for e in ed if e.startswith(("28110319#0", "-313328846#10")) and ed[e].get("speed")}
    return {"done": len(trips), "running+waiting": int(s.get("Running", 0)) + int(s.get("Waiting", 0)), "teleports": s.get("Teleports", "0"),
            "avg km/h": round(float(s.get("Speed", 0)) * 3.6, 1), "time lost per trip s": round(float(s.get("TimeLoss", 0))), "on flyover": fly, "landing road km/h": land}
if __name__ == "__main__":
    nets = sys.argv[1:] or ["sim/networks/ymca.net.xml", "sim/out/ymca_flyover.net.xml"]
    for scale in (0.9, 1.0):
        for net in nets:
            tag = net.split("/")[-1].replace(".net.xml", "")
            print(f"scale {scale} {tag:14}", run(net, scale, f"{tag}{scale}"), flush=True)
