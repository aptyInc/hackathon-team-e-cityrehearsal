# /sim — Simulation and Scenarios workstreams
Produces C1 vehicle frames and C2 run results (see /contracts).

## Steps
1. Install SUMO, set `SUMO_HOME`.
2. Export the YMCA Circle area from OpenStreetMap to `networks/ymca.osm.xml` (or use SUMO's osmWebWizard).
3. `bash scripts/build_network.sh` → `networks/ymca.net.xml`; fix lane counts by hand in netedit.
4. Turn the published-study counts in `/data` into routes with routeSampler; label inputs `estimated`.
5. Enable the sublane model (lateral resolution ~0.2–0.3 m) and define vehicle types: two_wheeler, car, auto, bus.
6. Calibrate demand until simulated speeds match TomTom speeds for the junction.
7. Implement a runner that takes a C3 variant spec and returns a C2 result; expose C1 frames for streaming.
