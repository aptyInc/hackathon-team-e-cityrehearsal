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
