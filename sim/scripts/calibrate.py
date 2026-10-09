"""Calibration check: simulated vs TomTom speeds on the last 240 m of each road into YMCA Circle.

Runs the baseline through sim/runner.py at several *count scales* (multiples of the 2020 study counts) and seeds,
and prints the 3-seed mean speed per approach next to TomTom's weekday 09:00 speed (July 2026), plus the
simulated delay next to TomTom Junction Analytics' median morning delay (9 Oct 2026, 08:00-11:00).

Usage (repo root, inside .venv):  python sim/scripts/calibrate.py [--scales 1.0,1.1,1.2,1.3] [--seeds 1,2,3]
The runner's CALIBRATED_SCALE is switched off here so the scales are raw count scales.
"""
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner  # noqa: E402

runner.CALIBRATED_SCALE = 1.0
DIRS = ("ne", "e", "s", "w")


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


scales = [float(x) for x in arg("--scales", "1.0,1.1,1.2,1.3").split(",")]
seeds = [int(x) for x in arg("--seeds", "1,2,3").split(",")]
print(f"{'count scale':11} | speed km/h   NE     E     S     W  | delay s   NE     E     S     W  | speed err | trips (min-max)")
ref = None
for sc in scales:
    rows = [runner.run({"variant_id": "baseline", "template": "baseline", "params": {}}, sc,
                       run_id=f"calib_{sc}_{sd}", seed=sd, frames=False) for sd in seeds]
    ref = ref or rows[0]
    sp = {d: st.mean(r["approach_speed_kmh"][d] for r in rows) for d in DIRS}
    de = {d: st.mean(r["approach_delay_s"][d] or 0 for r in rows) for d in DIRS}
    err = st.mean(abs(sp[d] - ref["tomtom_speed_kmh"][d]) for d in DIRS)
    trips = [r["trips"] for r in rows]
    print(f"{sc:<11} | " + " ".join(f"{sp[d]:5.1f}" for d in DIRS) + "          | " + " ".join(f"{de[d]:5.1f}" for d in DIRS)
          + f"        | {err:6.1f}    | {st.mean(trips):5.0f} ({min(trips)}-{max(trips)})", flush=True)
print(f"{'TomTom':11} | " + " ".join(f"{ref['tomtom_speed_kmh'][d]:5.1f}" for d in DIRS) + "          | "
      + " ".join(f"{ref['tomtom_delay_s'].get(d, 0):5.1f}" for d in DIRS) + "        (09:00 speeds; median 08-11 delay)")
