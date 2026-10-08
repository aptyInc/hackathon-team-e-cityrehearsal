"""Collect YMCA Circle live data from TomTom Junction Analytics every 5 minutes.

Owner: Data and proof. Label of the output: `measured`.
Junction: YMCA Circle Narayanaguda, id 6ac7d6870b461bdaf5cd8158 (created 2026-10-08 23:14 IST, trial allows one junction).

Usage (from the repo root, with TOMTOM_API_KEY in .env):
    nohup python3 data/tomtom/collect_junction_live.py > data/tomtom/junction/collector.log 2>&1 &
    python3 data/tomtom/collect_junction_live.py --once      # one snapshot, for testing

Writes:
    data/raw/tomtom_ymca_junction_live.csv   one row per approach per snapshot (delay, queue, volume, stops)
    data/raw/tomtom_ymca_turn_ratios.csv     one row per approach -> exit per snapshot
Uses curl because Python's own certificate check fails on some laptops here. TomTom also keeps history:
the web app's "Historical data export" (hourglass icon) downloads up to six months as a zip.
"""
import csv, json, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUNCTION = "6ac7d6870b461bdaf5cd8158"
URL = "https://api.tomtom.com/junction-analytics/junctions/1/{j}/live-data?key={k}"
LIVE_CSV = ROOT / "data/raw/tomtom_ymca_junction_live.csv"
TURNS_CSV = ROOT / "data/raw/tomtom_ymca_turn_ratios.csv"
DEFINITION = ROOT / "data/tomtom/junction/ymca_definition.json"  # approach and exit names
EVERY_S = 300


def api_key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TOMTOM_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("TOMTOM_API_KEY is missing from .env")


def append(path, rows):
    if not rows:
        return
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        if new:
            w.writeheader()
        w.writerows(rows)


def snapshot(key):
    out = subprocess.run(["curl", "-s", "--compressed", URL.format(j=JUNCTION, k=key)], capture_output=True, text=True, timeout=60)
    d = json.loads(out.stdout)
    m = d.get("junctionModel") or json.loads(DEFINITION.read_text())["junctionModel"]
    approaches = {a["id"]: a["name"] for a in m["approaches"]}
    exits = {e["id"]: e["name"] for e in m["exits"]}
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    live, turns = [], []
    for a in d["approachesLiveData"]:
        live.append({"time": ts, "approach": approaches[a["id"]], "travel_time_s": a["travelTimeSec"],
                     "free_flow_travel_time_s": a["freeFlowTravelTimeSec"], "delay_s": a["delaySec"],
                     "usual_delay_s": a["usualDelaySec"], "queue_m": a["queueLengthMeters"],
                     "volume_per_hour": a["volumePerHour"], "stops": a["stops"], "closed": a["isClosed"],
                     "source": f"TomTom Junction Analytics {JUNCTION}", "label": "measured"})
        for t in a["turnRatios"]:
            turns.append({"time": ts, "approach": approaches[a["id"]], "exit": exits.get(t["exitId"], t["exitId"]),
                          "ratio_percent": t["ratioPercent"], "probes": t["probesCount"],
                          "source": f"TomTom Junction Analytics {JUNCTION}", "label": "measured"})
    append(LIVE_CSV, live)
    append(TURNS_CSV, turns)
    print(ts, f"{len(live)} approaches, {len(turns)} turn rows", flush=True)


if __name__ == "__main__":
    key = api_key()
    while True:
        try:
            snapshot(key)
        except Exception as e:  # keep collecting through a bad response or a network blip
            print(datetime.now().isoformat(timespec="seconds"), "error:", e, flush=True)
        if "--once" in sys.argv:
            break
        time.sleep(EVERY_S)
