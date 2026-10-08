# /sim/templates — Scenarios workstream
One template per option type; each takes C3 `params` and produces a variant network from the baseline:
- `signal_retime` — change cycle and phase lengths
- `junction_redesign` — add/remove turn connections, free left turn
- `bus_lane` — restrict one lane to buses
- `widening` — increase lanes on given edges
- `flyover` — elevated through-lanes with ramps; params: lanes, length_m, landing_edge (pre-build and test before Friday)
Method: netconvert --plain-output-prefix → patch XML with sumolib → rebuild with netconvert. Same traffic file for every variant.
