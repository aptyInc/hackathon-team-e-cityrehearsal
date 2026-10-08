"""Request YMCA Circle hourly speeds from TomTom Traffic Stats (Route Analysis API) and download the results.

Owner: Data and proof. Label of the output: `measured`.

Usage (from the repo root, with TOMTOM_API_KEY in .env):
    python3 data/tomtom/fetch_traffic_stats.py submit      # creates the job, saves its id in job.json
    python3 data/tomtom/fetch_traffic_stats.py status      # shows the job state
    python3 data/tomtom/fetch_traffic_stats.py download    # waits until DONE, saves files in data/tomtom/results/

The request (8 road stretches in and out of the circle, weekdays 1-31 Jul 2026, the only range the trial allows, 24 one-hour slots)
is in ymca_route_analysis.request.json. Docs: https://docs.tomtom.com/traffic-stats/documentation/api/route-analysis
"""
import json, os, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = "https://api.tomtom.com/traffic/trafficstats"
JOB_FILE = HERE / "job.json"
RESULTS = HERE / "results"


def api_key():
    key = os.getenv("TOMTOM_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("TOMTOM_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        sys.exit("TOMTOM_API_KEY is missing: add it to .env (never commit it).")
    return key


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def submit():
    if JOB_FILE.exists():
        sys.exit(f"A job was already submitted ({JOB_FILE.read_text().strip()}). Do not resubmit; run 'status'.")
    body = json.loads((HERE / "ymca_route_analysis.request.json").read_text())
    res = call("POST", f"{API}/routeanalysis/1?key={api_key()}", body)
    print(res)
    if res.get("jobId"):
        JOB_FILE.write_text(json.dumps({"jobId": res["jobId"]}))


def status():
    job = json.loads(JOB_FILE.read_text())["jobId"]
    return call("GET", f"{API}/status/1/{job}?key={api_key()}")


def download():
    while True:
        s = status()
        print(time.strftime("%H:%M:%S"), s.get("jobState"), s.get("messages", ""))
        if s.get("jobState") == "DONE":
            break
        if s.get("jobState") in ("ERROR", "REJECTED", "CANCELLED", "EXPIRED"):
            sys.exit(f"Job ended without results: {s}")
        time.sleep(60)
    RESULTS.mkdir(exist_ok=True)
    for url in s.get("urls", []):
        name = url.split("?")[0].rsplit("/", 1)[-1]
        urllib.request.urlretrieve(url, RESULTS / name)
        print("saved", RESULTS / name)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"submit": submit, "status": lambda: print(status()), "download": download}[cmd]()
