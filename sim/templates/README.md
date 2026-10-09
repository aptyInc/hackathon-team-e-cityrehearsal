# /sim/templates — Scenarios workstream
One template per option type; each takes C3 `params` and produces a variant network from the baseline:
- `signal_retime` — change cycle and phase lengths
- `junction_redesign` — add/remove turn connections, free left turn
- `bus_lane` — restrict one lane to buses
- `widening` — increase lanes on given edges
- `flyover` — elevated through-lanes with ramps; params: lanes, length_m, landing_edge (pre-build and test before Friday)
Method: netconvert --plain-output-prefix → patch XML with sumolib → rebuild with netconvert. Same traffic file for every variant.

## Status (9 Oct, before the start)
- `flyover.py` works: `python sim/templates/flyover.py --lanes 3 --length_m 400` builds `sim/out/ymca_flyover.net.xml`
  (east-west flyover over YMCA Circle, the busiest straight-through axis in TomTom's morning data) and runs the
  **design check**, which warns that 3 flyover lanes merge into the 2-lane roads at both landings.
- `python sim/scripts/compare_variants.py` runs the same traffic through the baseline and the flyover. At study
  volumes: 10.1 -> 31.5 km/h average, 1,199 vehicles use the flyover, and the circle's own exit traffic at the west
  landing drops to 10-12 km/h where the flyover merges in (the lane-drop effect). The baseline roundabout capacity
  is still too low (sim/README.md), so the gain is overstated until calibration is fixed.
- Wiring lessons, already handled in the template: keep the original edge ids on the parts the traffic file uses;
  give the ramp starts and landings explicit connections; when rebuilding, clear only the outgoing connections of
  touched edges (clearing incoming ones cut the roundabout off from its exits).
- Not built yet: signal_retime, junction_redesign, bus_lane, widening.

## Corridor templates (`corridor.py`, Lingampally -> Lakdikapul)
`apply(net_path, out, interventions) -> warnings` builds a variant of `sim/corridor/corridor.net.xml` with every
intervention in one netconvert rebuild. Intervention = `{"junction_id": "j07", "kind": ..., "params": {...}}` (C5 kinds).
Unknown junction/kind or a param out of range raises `ValueError`; everything else comes back as a warning string.

| kind | params (all optional) | what it builds |
|---|---|---|
| `flyover` / `underpass` | `lanes` (1-4, default 2), `speed_kmh` (default 60, or the road's speed if faster), `length_m` (100-3000; default = junction span + 400 m) | One structure per direction (+6 m / -6 m) from ~200 m before the junction to ~200 m after it. Through traffic can take it; turning and cross traffic stay on the ground junction. Edge ids: `flyover_j07_fwd`, `flyover_j07_rev`. Not at j04 (already a flyover). |
| `signal_retime` | `cycle_s` (40-240, default 120), `corridor_green_share` (alias `main_share`, 0.1-0.9, default 0.5) | Rewrites every signal the corridor meets at the junction. Yellow times kept; the green time (cycle minus yellow) is split: `share` to the phases that give the corridor's through traffic green, the rest to the other phases (proportional to their old lengths, 5 s minimum, warning under 10 s). |
| `widening` (stretch) | `add_lanes` (1-2, default 1), `length_m` (default 300) | Extra lanes on the corridor within `length_m` either side of the junction, both directions. Signals there get a fresh default plan (warning). |
| `one_way`, `u_turn` | - | Not built yet: left out with a warning. |

Design checks in the warnings: flyover lanes vs the road before the ramp and after the landing (lane drop),
structure slower than the ground road, structures too close to each other (shortened or left out), retime phases
under 10 s green, directions where the corridor has no signal, junctions where every phase serves the corridor.

Wiring (same lessons as `flyover.py`): split road pieces keep the original edge id on the side away from the junction
(trips from the corridor's first to last edge and probes still work); the connections and signal links at the old
edge ends are renamed to the new pieces, so signal programs stay exactly as they were; ramp starts and landings get
explicit lane links. A structure's length is capped at 97% of the ground road it bypasses (lane lengths leave out
junction areas), so `corridor_net.route()` and SUMO's router both pick it.

Test: `python sim/templates/test_corridor.py` (about 2 minutes; `... j07` runs only cases with j07 in the name).
It builds each case, checks both corridor routes, runs SUMO (assumed traffic: 300 veh/h each way + 150 veh/h per side
road) and checks that >= 90% of through trips take a new structure, no extra teleports, and the local through time
(600 m either side) moves the expected way. Note: SUMO's own fastest A-B route leaves the corridor at j03, j06, j07
and j10, so the test keeps through trips on it with `via` edges; the corridor runner needs the same.
