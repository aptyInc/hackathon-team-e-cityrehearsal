# /sim — Simulation and Scenarios workstreams
Produces C1 vehicle frames and C2 run results (see /contracts). Install and run steps are in the main README (section 2).

## What exists (9 Oct 2026, before the start)
| Piece | File | Status |
|---|---|---|
| YMCA Circle road network | `networks/ymca.net.xml` (`make network`) | Built from OpenStreetMap; left-hand traffic; main roads only; roundabout + 8 roads touching it widened to 3 lanes / 9.9 m to match the 2020 study (`networks/ymca_widths.edg.xml`, applied by `scripts/apply_widths.py`) |
| Hyderabad road defaults | `networks/india_urban.typ.xml` | Speeds 30–50 km/h, tertiary roads 2 lanes, where OSM has no tag (`assumed`) |
| Baseline traffic | `demand/ymca_baseline.rou.xml` (`python sim/scripts/build_demand.py --scale 0.9`) | Volumes per road and class from the 2020 study (`counted`); turns from TomTom Junction Analytics (`measured`); car/auto split 70/30 and leg-to-road matching (`assumed`/`estimated`) |
| Vehicle types | inside the demand file | two_wheeler, auto, car, bus; sublane model (run SUMO with `--lateral-resolution 0.3`) |
| Calibration check | `scripts/calibrate.py` | Prints simulated vs TomTom 09:00 speeds per road |
| Gariahat backtest networks | `networks/gariahat_after.net.xml`, `networks/gariahat_before.net.xml` (`bash sim/scripts/build_gariahat.sh`) | With and without the Gariahat Flyover; Gariahat crossing and Ballygunge Phari both present. No traffic yet: needs the 2004 study's volumes (paper not accessible online; request on ResearchGate) |

## Calibration so far (scale = share of the 2020 study volumes)
| Scale | NE Narayanguda Rd | E Raja Bahadur V. R. Reddy Marg | S Narayanguda Rd | W Narayanguda Main Rd | Mean error | Teleports |
|---|---|---|---|---|---|---|
| TomTom 09:00 (target) | 23.0 | 18.9 | 19.2 | 17.6 | | |
| 0.8 | 41.3 | 29.2 | 39.9 | 27.3 | 14.7 km/h | 1 |
| **0.9** | **15.6** | **17.9** | **10.8** | **16.1** | **4.6 km/h** | 21 |
| 1.0 | 5.0 | 4.1 | 3.2 | 3.5 | 15.7 km/h | 98 |

The circle sits at its tipping point: free flow at 80%, gridlock at 100%. **Use scale 0.9 as the baseline** until calibration improves.

## Next steps (Simulation owner)
1. South road (10.8 vs 19.2 km/h) and north-east road (15.6 vs 23.0) are too slow at 0.9: check the merge where three roads feed the south entry (`747373024#0`) and the upstream junctions in `netedit`.
2. Replace the overnight turn ratios with rush-hour ones once Friday's TomTom data is in: `build_demand.py --since 08:00 --until 11:00`.
3. Reduce teleports (21 at scale 0.9): check lane changes just before the roundabout.
4. Free-flow speeds are too high at low volume (NE 41 km/h vs TomTom ~27 km/h at 03:00): lower `speedFactor` or the 60 km/h OSM limits on the approaches.
5. Implement the runner: C3 variant spec in, C2 run result and C1 frames out (contracts in `/contracts`).

## Original steps
1. Install SUMO (`make setup-sim`).
2. Export the YMCA Circle area from OpenStreetMap to `networks/ymca.osm.xml`.
3. `make network` → `networks/ymca.net.xml`; check lane counts in netedit.
4. Turn the study counts and TomTom turn ratios into traffic (`scripts/build_demand.py`); label inputs.
5. Sublane model (lateral resolution 0.3 m) and vehicle types two_wheeler, car, auto, bus.
6. Calibrate demand until simulated speeds match TomTom speeds for the junction (`scripts/calibrate.py`).
7. Implement a runner that takes a C3 variant spec and returns a C2 result; expose C1 frames for streaming.
