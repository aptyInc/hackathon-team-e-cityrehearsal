"""Run the same traffic through several options and compare them (Scenarios / Simulation).

Usage (repo root, inside .venv):
    python sim/scripts/compare_variants.py                       # baseline vs the 3-lane 400 m flyover
    python sim/scripts/compare_variants.py '{"variant_id":"flyover_2lane","template":"flyover","params":{"lanes":2}}' ...
    python sim/scripts/compare_variants.py --scale 0.8 ...       # C2 volume_scale (1.0 = today's calibrated traffic)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner  # noqa: E402

scale = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 1.0
specs = [json.loads(a) for a in sys.argv[1:] if a.startswith("{")] or [
    {"variant_id": "baseline", "template": "baseline", "params": {}},
    {"variant_id": "flyover_3lane_400m", "template": "flyover", "params": {"lanes": 3, "length_m": 400}}]
print(f"{'option':22} {'circle delay':>12} {'circle queue':>12} {'corridor':>9} {'trips':>6}  approach speeds km/h (NE E S W)      warnings")
for spec in specs:
    r = runner.run(spec, scale, run_id=f"cmp_{spec['variant_id']}", frames=False)
    c = next(j for j in r["junctions"] if j["id"] == "ymca_circle")
    sp = r["approach_speed_kmh"]
    print(f"{spec['variant_id']:22} {c['avg_delay_s']:10.1f} s {c['max_queue_m']:10} m {r['corridor_travel_time_s']:7} s {r['trips']:6}  "
          + " ".join(f"{sp[d]:5.1f}" for d in ("ne", "e", "s", "w")) + f"   {len(r['warnings'])}", flush=True)
    for j in r["junctions"]:
        if j["id"] != "ymca_circle" and (j["avg_delay_s"] > 15 or j["max_queue_m"] > 100):
            print(f"    ripple: {j['id']} delay {j['avg_delay_s']} s, queue {j['max_queue_m']} m")
    for w in r["warnings"]:
        print("    warning:", w)
