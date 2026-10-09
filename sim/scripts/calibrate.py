"""Compare simulated approach speeds at YMCA Circle with TomTom Traffic Stats (weekday 09:00, July 2026).

For each volume scale: rebuilds the baseline traffic, runs 70 simulated minutes (first 10 discarded) with the
sublane model, and prints the speed on the last ~240 m of each road into the circle next to TomTom's.
Usage (repo root, inside .venv): python sim/scripts/calibrate.py [scale ...]     e.g. 0.8 0.9 1.0
"""
import subprocess, sys, math, csv, json, re, xml.etree.ElementTree as ET
sys.path.insert(0, "sim/scripts"); import build_demand as bd, sumolib
net = sumolib.net.readNet("sim/networks/ymca.net.xml")
ins, _ = bd.approach_edges(net, json.load(open("data/tomtom/junction/ymca_definition.json")))
tt = {(r["route"], int(r["hour"])): float(r["avg_speed_kmh"]) for r in csv.DictReader(open("data/raw/tomtom_ymca_speeds.csv"))}
match = {"Narayanguda Road South Bound": "NE Narayanaguda Road - in", "Narayanguda Road North Bound": "S road - in",
         "Raja Bahadur Venkata Rama Reddy Marg West Bound": "SE Basant Talkies side - in", "YMCA to Ramkoti Road East Bound": "W Narayanguda Main Road - in"}
def chain(entry, metres=240):
    out, total, e = [entry], entry.getLength(), entry
    while total < metres:
        prev = [x for x in e.getIncoming() if abs(math.remainder(bd.angle(x) - bd.angle(e), 2*math.pi)) < math.radians(40)]
        if not prev: break
        e = max(prev, key=lambda x: x.getLaneNumber()); out.append(e); total += e.getLength()
    return out
def run(label, scale, extra_attrs):
    subprocess.run([sys.executable, "sim/scripts/build_demand.py", "--scale", str(scale)], check=True, capture_output=True)
    rou = open("sim/demand/ymca_baseline.rou.xml").read()
    rou = re.sub(r'(<vType id="[^"]+")', r'\1 ' + extra_attrs, rou)
    open("sim/out/calib.rou.xml", "w").write(rou)
    p = subprocess.run(["sumo", "-n", "sim/networks/ymca.net.xml", "-r", "sim/out/calib.rou.xml", "-a", "sim/scripts/edgedata.add.xml",
                        "--lateral-resolution", "0.3", "--end", "4200", "--no-step-log", "--duration-log.statistics",
                        "--time-to-teleport", "300", "--seed", "42", "--output-prefix", "calib_"], capture_output=True, text=True, cwd=".")
    stats = dict(re.findall(r"\n (Teleports|Speed|TimeLoss): ([0-9.]+)", p.stdout + p.stderr))
    ed = {e.get("id"): e for e in ET.parse("sim/out/calib_baseline.edgedata.xml").getroot().iter("edge")}
    res = []
    err = 0
    for a, entry in ins.items():
        edges = chain(entry); L = sum(e.getLength() for e in edges); t = 0
        for e in edges:
            d = ed.get(e.getID()); sp = float(d.get("speed")) if d is not None and d.get("speed") else e.getSpeed()
            t += e.getLength() / max(sp, 0.1)
        v = L / t * 3.6; res.append(v); err += abs(v - tt[(match[a], 9)])
    print(f"{label:46} NE {res[0]:5.1f}  E {res[1]:5.1f}  S {res[2]:5.1f}  W {res[3]:5.1f} | mean abs err {err/4:5.1f} km/h | teleports {stats.get('Teleports','?')}", flush=True)
print(f"{'TomTom 09:00 (target)':46} NE {tt[(match[list(ins)[0]],9)]:5.1f}  E {tt[(match[list(ins)[1]],9)]:5.1f}  S {tt[(match[list(ins)[2]],9)]:5.1f}  W {tt[(match[list(ins)[3]],9)]:5.1f}")
for scale in [float(x) for x in sys.argv[1:]] or [0.8, 0.9, 1.0]:
    run(f"scale {scale}", scale, "")
