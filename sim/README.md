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

## What exists (Fri 9 Oct, 15:00)
| Piece | File | Status |
|---|---|---|
| YMCA Circle road network | `networks/ymca.net.xml` (`make network`) | From OpenStreetMap; left-hand traffic; main roads only. Ring and the 8 roads touching it set to the study's measured widths as **two wide lanes** (ring 2 × 5.6 m, roads 2 × 4.9 m; `networks/ymca_widths.edg.xml`, applied by `scripts/apply_widths.py`) at 25 / 30 km/h |
| Hyderabad road defaults | `networks/india_urban.typ.xml` | Speeds and lanes where OSM has no tag (`assumed`) |
| Baseline traffic | `scripts/build_demand.py` | Vehicles per road and class from the 2020 study (`counted`) × 2.0 (`estimated`, see calibration); turns from TomTom Junction Analytics, morning 08–11 (`measured`); car/auto split 70/30 (`assumed`); two_wheeler, auto, car, bus with the sublane model |
| **Runner** (C3 in → C2 + C1 out) | `runner.py` | Builds the option's network and traffic, runs SUMO, measures delay/queues per zone and the approach speeds vs TomTom, writes frames. Wired into the backend for `MOCK_SIM=0` |
| Flyover option | `templates/flyover.py` | East–west flyover from C3 params; design check flags the 3→2 lane drop at both landings |
| Other options | — | `signal_retime`, `junction_redesign`, `bus_lane`, `widening` not built yet (runner returns 501 for them) |
| Gariahat backtest | `networks/gariahat_after.net.xml`, `gariahat_before.net.xml`, `scripts/build_gariahat.sh` | Networks with and without the flyover; the 2004 study's volumes and turns are in `data/gariahat/`; traffic not built yet |

## Calibration (what "today's traffic" means)
Two TomTom yardsticks exist for the last 240 m of each road into the circle, and they disagree with each other by
3–6 km/h: the **July 2026 route speeds** (Traffic Stats, weekday 09:00; the east route includes a side street) and
**this morning's junction data** (Junction Analytics, 08:00–11:00, approach length / median travel time). The model
sits between them. Four findings shaped it:
1. **A 60 km/h ring never lets anyone in.** SUMO sizes the gap an entering vehicle needs by the ring speed; at
   the OSM limit the circle jammed at 4 km/h. At 25 km/h (entries 30 km/h) it flows; slower still cuts capacity
   again (`estimated`).
2. **Two wide lanes beat three narrow ones.** Same measured width, but with three 3.3 m lanes the south entry
   starved behind the heavy east→west stream. Two 4.9–5.6 m lanes let two-wheelers filter and share gaps.
3. **Indian traffic follows closer than SUMO's defaults.** With default gaps the circle carried ~3,300 vehicles/h
   at TomTom's speeds and flipped between flowing and jammed from one random seed to the next. With close
   following (two-wheelers 0.5 m / 0.6 s, autos 0.7 / 0.7, cars 1.0 / 0.8, buses 1.5 / 1.0; `assumed`) it carries
   ~5,700/h, close to TomTom's own volume estimate, and every seed gives the same picture.
4. **The 2020 counts are far too low for 2026.** Speeds match at 2.0 × the study counts. TomTom's volume estimate
   for this morning (~7,400/h at the peak) is higher still; the truth is probably between.

3-seed means with close following, count scale = multiple of the 2020 counts (`python sim/scripts/calibrate.py`):

| Count scale | NE Narayanguda Rd | E Raja Bahadur V. R. Reddy Marg | S Narayanguda Rd | W Narayanguda Main Rd | Error vs July | Vehicles/h |
|---|---|---|---|---|---|---|
| TomTom July 09:00 | 23.0 | 18.9 | 19.2 | 17.6 | | |
| TomTom junction, this morning | 29.7 | 23.8 | 25.8 | 22.4 | | ~7,400 (estimate) |
| 1.8 | 22.0 | 26.9 | 19.8 | 19.4 | 2.9 km/h | 5,100 |
| **2.0** | **22.2** | **26.4** | **19.6** | **19.1** | **2.6 km/h** | **5,700** |
| 2.2 | 21.8 | 26.1 | 20.0 | 19.7 | 2.8 km/h | 6,200 |
| 2.5 | 21.3 | 25.4 | 20.5 | 20.2 | 3.0 km/h | 6,200 (saturated) |

Demo runs use seed 2 (`runner.SEED`), the closest of nine seeds to their mean; at the calibrated volume the nine
seeds give 17–26 s delay at the circle and ~300 m queues (TomTom saw 200–520 m this morning).

Caveats to say out loud: the east road runs 25–27 km/h in the model, between the two TomTom figures (18.9 July,
23.8 this morning); about 2–4% of vehicles are removed after sublane collisions (SUMO's default); simulated
per-approach delays run above TomTom's median morning delays because ours average every vehicle in a busy half
hour and TomTom's is a median over minutes. Speeds are the cleaner comparison, and both references are reported
in every run result (`tomtom_speed_kmh`, `tomtom_junction_speed_kmh`).

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
