# /sim — Simulation and Scenarios workstreams
Produces C1 vehicle frames and C2 run results (see /contracts). Install steps are in the main README (section 2).

## How to run
```bash
make setup-sim                     # SUMO 1.28 into .venv (once)
make network                       # rebuild sim/networks/ymca.net.xml from OpenStreetMap
make sim-run                       # one baseline run: C2 result printed, C1 frames in sim/out/runs/<id>/frames.jsonl
python sim/runner.py '{"variant_id":"flyover_3lane_400m","template":"flyover","params":{"lanes":3,"length_m":400}}' --scale 1.0
python sim/scripts/compare_variants.py          # baseline vs flyover side by side, with ripple and warnings
python sim/scripts/calibrate.py                 # simulated vs TomTom speeds at several count scales and seeds
MOCK_SIM=0 make dev                             # the API runs real simulations (POST /runs, WS /stream/{run_id})
```
A run simulates 30 minutes in 3–9 seconds of wall time. `--scale` is the C2 `volume_scale`: 1.0 is today's
calibrated traffic, 0.8 is the reviewer's 20%-less test.

## What exists (Fri 9 Oct, 11:45)
| Piece | File | Status |
|---|---|---|
| YMCA Circle road network | `networks/ymca.net.xml` (`make network`) | From OpenStreetMap; left-hand traffic; main roads only. Ring and the 8 roads touching it set to the study's measured widths as **two wide lanes** (ring 2 × 5.6 m, roads 2 × 4.9 m; `networks/ymca_widths.edg.xml`, applied by `scripts/apply_widths.py`) at 25 / 30 km/h |
| Hyderabad road defaults | `networks/india_urban.typ.xml` | Speeds and lanes where OSM has no tag (`assumed`) |
| Baseline traffic | `scripts/build_demand.py` | Vehicles per road and class from the 2020 study (`counted`) × 1.2 (`estimated`, see calibration); turns from TomTom Junction Analytics, morning 08–11 (`measured`); car/auto split 70/30 (`assumed`); two_wheeler, auto, car, bus with the sublane model |
| **Runner** (C3 in → C2 + C1 out) | `runner.py` | Builds the option's network and traffic, runs SUMO, measures delay/queues per zone and the approach speeds vs TomTom, writes frames. Wired into the backend for `MOCK_SIM=0` |
| Flyover option | `templates/flyover.py` | East–west flyover from C3 params; design check flags the 3→2 lane drop at both landings |
| Other options | — | `signal_retime`, `junction_redesign`, `bus_lane`, `widening` not built yet (runner returns 501 for them) |
| Gariahat backtest | `networks/gariahat_after.net.xml`, `gariahat_before.net.xml`, `scripts/build_gariahat.sh` | Networks with and without the flyover; the 2004 study's volumes and turns are in `data/gariahat/`; traffic not built yet |

## Calibration (what "today's traffic" means)
The target is TomTom's measured weekday 09:00 speed on the last 240 m of each road into the circle (July 2026).
Three findings shaped the model:
1. **A 60 km/h ring never lets anyone in.** SUMO sizes the gap an entering vehicle needs by the ring speed; at
   the OSM limit the circle jammed at 4 km/h. At 25 km/h (entries 30 km/h) it flows. Slower still (20 km/h)
   cuts capacity again, so 25/30 is the setting (`estimated`).
2. **Two wide lanes beat three narrow ones.** Same measured width, but with three 3.3 m lanes the south
   entry starved behind the heavy east→west stream. Two 4.9–5.6 m lanes let two-wheelers filter and share gaps.
3. **The 2020 counts are too low for 2026.** Speeds match at 1.2 × the study counts (TomTom's own volume
   estimates are higher still). Below 1.1 every approach is free-flowing; at 1.3 the circle breaks down.

3-seed means, count scale = multiple of the 2020 counts (`python sim/scripts/calibrate.py`):

| Count scale | NE Narayanguda Rd | E Raja Bahadur V. R. Reddy Marg | S Narayanguda Rd | W Narayanguda Main Rd | Mean error | Trips in 25 min |
|---|---|---|---|---|---|---|
| TomTom 09:00 | 23.0 | 18.9 | 19.2 | 17.6 | | |
| 1.0 | 22.3 | 27.6 | 23.2 | 23.8 | 4.9 km/h | 1,199 |
| 1.1 | 21.4 | 23.5 | 19.0 | 18.4 | 1.8 km/h | 1,158 |
| **1.2** | **21.6** | **21.1** | **19.4** | **19.0** | **1.3 km/h** | 1,370 |
| 1.3 | 22.1 | 24.6 | 16.4 | 15.9 | 2.8 km/h | 889–1,438 (unstable) |

**The circle is bistable.** At the calibrated volume, 6 of 9 random seeds flow at 25–27 km/h and 3 tip into
congestion at 16–18 km/h, which is where TomTom's morning readings sit. A 10% change in traffic flips it.
Demo runs use seed 1 (`runner.SEED`), which reproduces TomTom's congested morning within 1.3 km/h on all four
roads; claims in the pitch should quote multi-seed means.

Other caveats: about 2–4% of vehicles are removed after sublane collisions (SUMO's default); simulated
per-approach delays (8–46 s) run above TomTom's median morning delays (2–10 s) even where speeds match, because
ours average every vehicle in a busy half hour and TomTom's is a median over minutes. Speeds are the cleaner
comparison.

## Next steps (Simulation / Scenarios owners)
1. Templates for `signal_retime`, `bus_lane`, `junction_redesign`, `widening` in `sim/templates/` (same pattern as
   `flyover.py`: plain-XML edit, rebuild, return the network path and any design warnings), then add them to
   `runner.network_for`.
2. Gariahat backtest traffic: match the paper's approaches A–E to the network roads (Figure 1 of the paper),
   build flows from `data/gariahat/volumes.csv` + `turns.csv` the way `build_demand.py` does, run before/after.
3. Flyover frames: the flyover edges have no height yet, so C1 `z` is 0 on the flyover. Give the flyover edges
   an elevation in `templates/flyover.py` (or lift vehicles on `flyover_*` edges when writing frames).
4. Evening calibration once the TomTom 17:00–21:00 junction data is in (`make junction-data` at Checkpoint 2).

## Method notes
Network: `netconvert` from OSM with `--lefthand`, main roads only, Hyderabad type map, widths patch.
Demand: per-approach counts × class split → flows per (approach, exit, class) with TomTom turn shares;
vehicles start and end 600 m from the circle so the next junctions carry traffic. Zones: `ymca_circle` =
ring + 240 m of each road; `next_<dir>` = 240–700 m out. Delay for the circle = time lost on the last 240 m
of each road per vehicle (TomTom-comparable); queue = longest queue on any lane in the zone.
