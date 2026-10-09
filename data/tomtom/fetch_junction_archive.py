"""Download the YMCA Circle Junction Analytics archive from TomTom and turn it into our CSVs.

Owner: Data and proof. Label: speeds, delays and turn ratios `measured`; volume and queue `estimated` (TomTom model).
No MOVE login needed: only TOMTOM_API_KEY in .env. TomTom keeps the history since the junction was created
(2026-10-08 23:14 IST), with one row per approach per minute and turn ratios over rolling 30-minute windows.

Usage (repo root):  python3 data/tomtom/fetch_junction_archive.py 2026-10-08 [2026-10-10]
Writes:
    data/tomtom/junction/archive/<from>_<to>/          the unzipped archive (readme.pdf, csv/...)
    data/raw/tomtom_ymca_junction_live.csv             per minute: delay, queue, volume per approach (IST)
    data/raw/tomtom_ymca_turn_ratios.csv               per minute: approach -> exit share and probes (IST)
Docs: https://docs.tomtom.com/junction-analytics/documentation/junction/junction-archive
"""
import csv, io, subprocess, sys, zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUNCTION = "6ac7d6870b461bdaf5cd8158"
URL = "https://api.tomtom.com/junction-analytics/junctions/1/archive/{j}/data/flat/daily?key={k}&from={f}&to={t}"
IST = timezone(timedelta(hours=5, minutes=30))
SOURCE = f"TomTom Junction Analytics archive {JUNCTION}"


def api_key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TOMTOM_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("TOMTOM_API_KEY is missing from .env")


def ist(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(IST).isoformat(timespec="seconds")


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "2026-10-08"
    end = sys.argv[2] if len(sys.argv) > 2 else datetime.now(IST).date().isoformat()
    out = subprocess.run(["curl", "-s", "-f", "-H", "Content-Type: application/octet-stream",
                          URL.format(j=JUNCTION, k=api_key(), f=start, t=end)], capture_output=True)
    if out.returncode != 0 or not out.stdout.startswith(b"PK"):
        sys.exit(f"Download failed (curl exit {out.returncode}): {out.stdout[:300]!r}")
    folder = ROOT / f"data/tomtom/junction/archive/{start}_{end}"
    folder.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(io.BytesIO(out.stdout)); zf.extractall(folder)

    names = {}
    for f in sorted(folder.glob("csv/definition/*.csv")):
        for r in csv.DictReader(open(f)):
            names[r["id"]] = r["name"]

    live = [{"time": ist(r["time"]), "approach": names.get(r["approachId"], r["approachId"]),
             "travel_time_s": r["travelTimeSec"], "free_flow_travel_time_s": r["freeFlowTravelTimeSec"],
             "delay_s": r["delaySec"], "usual_delay_s": r["usualDelaySec"], "queue_m": r["queueLengthMeters"],
             "volume_per_hour": r["volumePerHour"], "stops": r["stops"], "closed": r["isClosed"],
             "source": SOURCE, "label": "measured (volume, queue: estimated)"}
            for r in csv.DictReader(open(folder / "csv/live-data/approaches.csv"))]
    turns = [{"time": ist(r["time"]), "approach": names.get(r["approachId"], r["approachId"]),
              "exit": names.get(r["exitId"], r["exitId"]), "ratio_percent": r["ratioPercent"],
              "probes": r["probesCount"], "source": SOURCE, "label": "measured"}
             for r in csv.DictReader(open(folder / "csv/live-data/turn_ratios.csv"))]
    for path, rows in ((ROOT / "data/raw/tomtom_ymca_junction_live.csv", live),
                       (ROOT / "data/raw/tomtom_ymca_turn_ratios.csv", turns)):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{len(live)} approach-minutes and {len(turns)} turn rows, {live[0]['time']} to {live[-1]['time']} (IST)")


if __name__ == "__main__":
    main()
