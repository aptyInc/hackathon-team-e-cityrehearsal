"""Collect live data for the corridor junctions from TomTom Junction Analytics, every minute.

Owner: Data and proof. Label: speeds, delays and turn ratios `measured`; volume and queue `estimated` (TomTom model).
Junctions and the .env name of each one's key: data/tomtom/junction/corridor_junctions.json (one trial account each).
TomTom's archive only serves whole days, so today's minutes are collected here; from tomorrow use --archive.

Usage (repo root):
    nohup python3 data/tomtom/collect_corridor_junctions.py > data/tomtom/junction/corridor_collector.log 2>&1 &
    python3 data/tomtom/collect_corridor_junctions.py --once                 # one snapshot, for testing
    python3 data/tomtom/collect_corridor_junctions.py --archive 2026-10-09   # whole past days from TomTom's archive
Writes:
    data/raw/tomtom_corridor_junction_live.csv   one row per junction approach per minute
    data/raw/tomtom_corridor_turn_ratios.csv     one row per approach -> exit per minute
    data/tomtom/junction/corridor/<jid>_definition.json   approach/exit names and geometry (fetched once)
"""
import csv, io, json, subprocess, sys, time, zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data/tomtom/junction/corridor_junctions.json"
DEFS = ROOT / "data/tomtom/junction/corridor"
LIVE_CSV = ROOT / "data/raw/tomtom_corridor_junction_live.csv"
TURNS_CSV = ROOT / "data/raw/tomtom_corridor_turn_ratios.csv"
API = "https://api.tomtom.com/junction-analytics/junctions/1"
IST = timezone(timedelta(hours=5, minutes=30))
EVERY_S = 60
LABEL = "measured (volume, queue: estimated)"


def env():
    return dict(l.split("=", 1) for l in (ROOT / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))


def curl(url, binary=False):
    out = subprocess.run(["curl", "-s", "--compressed", url], capture_output=True, timeout=120)
    return out.stdout if binary else json.loads(out.stdout)


def names(j, key):
    """Approach and exit names from the junction definition (unnamed approaches get their direction and id)."""
    path = DEFS / f"{j['corridor_id']}_definition.json"
    if not path.exists():
        DEFS.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(curl(f"{API}/{j['tomtom_id']}/definition?key={key}&includeGeometry=true")))
    m = json.loads(path.read_text())["junctionModel"]
    label = lambda x: (x.get("name") or "").strip() or f"{x.get('direction', '?')} #{x['id']}"
    return {a["id"]: label(a) for a in m["approaches"]}, {e["id"]: label(e) for e in m.get("exits", [])}


def append(path, rows):
    if not rows:
        return
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        if new:
            w.writeheader()
        w.writerows(rows)


def live_row(j, ts, approach_id, approach, r):
    return {"time": ts, "junction_id": j["corridor_id"], "junction": j["name"], "approach_id": approach_id, "approach": approach,
            "travel_time_s": r["travelTimeSec"], "free_flow_travel_time_s": r["freeFlowTravelTimeSec"], "delay_s": r["delaySec"],
            "usual_delay_s": r["usualDelaySec"], "queue_m": r["queueLengthMeters"], "volume_per_hour": r["volumePerHour"],
            "stops": r["stops"], "closed": r["isClosed"], "source": f"TomTom Junction Analytics {j['tomtom_id']}", "label": LABEL}


def snapshot(junctions, keys):
    ts = datetime.now(IST).isoformat(timespec="seconds")
    for j in junctions:
        try:
            key = keys[j["key_env"]]
            approaches, exits = names(j, key)
            d = curl(f"{API}/{j['tomtom_id']}/live-data?key={key}")
            live, turns = [], []
            for a in d["approachesLiveData"]:
                live.append(live_row(j, ts, a["id"], approaches.get(a["id"], a["id"]), a))
                for t in a["turnRatios"]:
                    turns.append({"time": ts, "junction_id": j["corridor_id"], "approach": approaches.get(a["id"], a["id"]),
                                  "exit": exits.get(t["exitId"], t["exitId"]), "ratio_percent": t["ratioPercent"],
                                  "probes": t["probesCount"], "source": f"TomTom Junction Analytics {j['tomtom_id']}", "label": "measured"})
            append(LIVE_CSV, live)
            append(TURNS_CSV, turns)
            print(ts, j["corridor_id"], f"{len(live)} approaches, {len(turns)} turn rows", flush=True)
        except Exception as e:   # keep collecting the others through a bad response or a network blip
            print(ts, j["corridor_id"], "error:", repr(e)[:200], flush=True)


def archive(junctions, keys, start, end):
    """Whole past days from TomTom's archive, appended in the same format as the live rows."""
    for j in junctions:
        key = keys[j["key_env"]]
        approaches, _ = names(j, key)
        data = curl(f"{API}/archive/{j['tomtom_id']}/data/flat/daily?key={key}&from={start}&to={end}", binary=True)
        if not data.startswith(b"PK"):
            print(j["corridor_id"], "archive failed:", data[:200]); continue
        zf = zipfile.ZipFile(io.BytesIO(data))
        rows = [live_row(j, datetime.fromisoformat(r["time"].replace("Z", "+00:00")).astimezone(IST).isoformat(timespec="seconds"),
                         r["approachId"], approaches.get(int(r["approachId"]), r["approachId"]),
                         {"travelTimeSec": r["travelTimeSec"], "freeFlowTravelTimeSec": r["freeFlowTravelTimeSec"],
                          "delaySec": r["delaySec"], "usualDelaySec": r["usualDelaySec"], "queueLengthMeters": r["queueLengthMeters"],
                          "volumePerHour": r["volumePerHour"], "stops": r["stops"], "isClosed": r["isClosed"]})
                for r in csv.DictReader(io.TextIOWrapper(zf.open("csv/live-data/approaches.csv")))]
        append(LIVE_CSV, rows)
        print(j["corridor_id"], f"{len(rows)} archived approach-minutes")


if __name__ == "__main__":
    cfg = json.loads(CONFIG.read_text())["junctions"]
    keys = env()
    missing = [j["key_env"] for j in cfg if j["key_env"] not in keys]
    if missing:
        sys.exit(f"missing in .env: {missing}")
    if "--archive" in sys.argv:
        days = sys.argv[sys.argv.index("--archive") + 1:]
        archive(cfg, keys, days[0], days[1] if len(days) > 1 else days[0])
    else:
        while True:
            snapshot(cfg, keys)
            if "--once" in sys.argv:
                break
            time.sleep(EVERY_S)
