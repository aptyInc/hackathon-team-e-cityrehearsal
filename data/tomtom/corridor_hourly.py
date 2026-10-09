"""The last TomTom Traffic Stats job: Lingampally -> Lakdikapul, hour by hour, for July 2026 and for each day 1-23 July.

Owner: Data and proof. Label of the output: `measured`.
TomTom allows 24 date ranges and 24 time sets per job, and time sets may not overlap: July 1-31 plus each single day
1-23 July (24 ranges), and 24 one-hour sets 00:00-24:00. Every set covers all weekdays, so a single-day range gets that
day's own hours. The night hours show free-flow speeds; 06:00-23:00 averages come from the hourly sets.
The route is the one job 10051304 measured ("lin to lak", drawn in the TomTom web app), pinned with via points taken
from its own geometry every ~700 m, skipping points on or near the corridor's flyovers (a point there could snap to
the road underneath).

Usage (repo root; uses the key named in KEY_ENV from .env):
    python3 data/tomtom/corridor_hourly.py build [--tag=2]   # --tag=2: the second job, 24-31 July
    python3 data/tomtom/corridor_hourly.py submit     # creates the job ONCE (account limit 20), saves its id
    python3 data/tomtom/corridor_hourly.py status
    python3 data/tomtom/corridor_hourly.py download   # saves data/tomtom/corridor/<jobId>.json when DONE
"""
import json, math, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "data/tomtom/corridor"
# job 1 (tag ""): July + each day 1-23 July; job 2 (tag "2"): each day 24-31 July (TomTom allows 24 date ranges per job)
TAG = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--tag=")), "")
DAYS_COVERED = {"": (True, range(1, 24)), "2": (False, range(24, 32))}[TAG]
REQUEST = HERE / f"hourly{TAG}.request.json"
JOB = HERE / f"hourly{TAG}_job.json"
SOURCE_JOB = HERE / "10051304.json"
API = "https://api.tomtom.com/traffic/trafficstats"
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
VIA_EVERY_M, FLYOVER_CLEAR_M = 700, 120


KEY_ENV = "TOMTOM_JA_KEY_J07"   # the main account's 20 jobs are used up; the Tolichowki trial account has Traffic Stats


def key(name=None):
    name = name or (json.loads(JOB.read_text()).get("key_env") if JOB.exists() else KEY_ENV)
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{name} is missing from .env")


def dist(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))


def flyover_points():
    """Every node of an OSM flyover near the corridor (bridge=yes with 'Flyover' in its name)."""
    root = ET.parse(ROOT / "sim/corridor/corridor.osm.xml").getroot()
    nodes = {n.get("id"): (float(n.get("lat")), float(n.get("lon"))) for n in root.iter("node")}
    pts = []
    for w in root.iter("way"):
        t = {x.get("k"): x.get("v") for x in w.iter("tag")}
        if t.get("bridge") not in (None, "no") and "flyover" in t.get("name", "").lower():
            pts += [nodes[n.get("ref")] for n in w.iter("nd") if n.get("ref") in nodes]
    return pts


def build():
    route = json.loads(SOURCE_JOB.read_text())["routes"][0]
    shape = [(p["latitude"], p["longitude"]) for s in route["segmentResults"] for p in s["shape"]]
    flys = flyover_points()
    via, run = [], 0.0
    for a, b in zip(shape, shape[1:]):
        run += dist(a, b)
        if run >= VIA_EVERY_M and dist(b, shape[-1]) > 300 and min(dist(b, f) for f in flys) > FLYOVER_CLEAR_M:
            via.append({"latitude": round(b[0], 6), "longitude": round(b[1], 6)})
            run = 0.0
    body = {
        "jobName": "CityRehearsal Lingampally to Lakdikapul hourly, July 2026" + (f" (part {TAG})" if TAG else ""),
        "distanceUnit": "KILOMETERS", "acceptMode": "AUTO",
        "routes": [{"name": "lin to lak hourly", "start": {"latitude": shape[0][0], "longitude": shape[0][1]},
                    "via": via, "end": {"latitude": shape[-1][0], "longitude": shape[-1][1]},
                    "fullTraversal": False, "zoneId": "Asia/Kolkata", "probeSource": "ALL"}],
        "dateRanges": ([{"name": "July 2026", "from": "2026-07-01", "to": "2026-07-31"}] if DAYS_COVERED[0] else []) +
                      [{"name": f"2026-07-{d:02d}", "from": f"2026-07-{d:02d}", "to": f"2026-07-{d:02d}"} for d in DAYS_COVERED[1]],
        # time sets may not overlap (TomTom rejects that), so no 06:00-23:00 set: 24 one-hour sets cover the whole day
        "timeSets": [{"name": f"{h:02d}:00-{h + 1:02d}:00", "timeGroups": [{"days": DAYS, "times": [f"{h:02d}:00-{h + 1:02d}:00"]}]}
                     for h in range(24)],
    }
    REQUEST.write_text(json.dumps(body, indent=1))
    print(f"{len(via)} via points over {sum(dist(a, b) for a, b in zip(shape, shape[1:])) / 1000:.1f} km, "
          f"{len(body['dateRanges'])} date ranges, {len(body['timeSets'])} time sets -> {REQUEST}")


def curl(*args):
    out = subprocess.run(["curl", "-s", *args], capture_output=True, text=True)
    return json.loads(out.stdout) if out.stdout.strip().startswith(("{", "[")) else out.stdout


def submit():
    if JOB.exists():
        sys.exit(f"Already submitted: {JOB.read_text().strip()} (the account allows 20 jobs; do not resubmit)")
    res = curl("-X", "POST", "-H", "Content-Type: application/json", "--data-binary", f"@{REQUEST}",
               f"{API}/routeanalysis/1?key={key()}")
    print(res)
    if isinstance(res, dict) and res.get("jobId"):
        JOB.write_text(json.dumps({"jobId": res["jobId"], "key_env": KEY_ENV}))


def status():
    job = json.loads(JOB.read_text())["jobId"]
    return curl(f"{API}/status/1/{job}?key={key()}")


def download():
    s = status()
    print({k: s.get(k) for k in ("jobId", "jobState", "responseStatus")})
    for url in s.get("urls", []) if isinstance(s, dict) else []:
        if url.endswith(".json") or "json" in url:
            out = HERE / f"{s['jobId']}.json"
            subprocess.run(["curl", "-s", "-o", str(out), url], check=True)
            print("saved", out)


if __name__ == "__main__":
    cmd = next((a for a in sys.argv[1:] if not a.startswith("--")), "status")
    r = {"build": build, "submit": submit, "status": lambda: print(status()), "download": download}[cmd]()
