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
| Gariahat backtest | `gariahat/backtest.py`, `gariahat/results.json`, `gariahat/README.md` | Before/after the flyover with the 2004 study's counted volumes on a purpose-built 13-node network: Gariahat delay −59% (study −75%); Phari gets slower in the same direction as the study but by less, unless the flyover attracts ~15% more traffic. See `gariahat/README.md` |

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

## Simulating a specific moment (TomTom junction data)
`python sim/runner.py '{...baseline...}' --window 2026-10-09T09:00 --minutes 15` rebuilds the traffic for that quarter
hour: vehicles per road = TomTom's estimated vehicles/hour then, turns = the turns TomTom measured then (morning
shares if fewer than 20 vehicles were seen), vehicle mix from the 2020 count. The result carries `tomtom_window`
(TomTom's delay, queue, volume and speed per road for the same minutes) for a like-for-like check. Any window since
Thu 8 Oct 23:17 works; the API takes `window: "live"` to refresh the data and simulate the last 15 minutes.
Labels: volumes `estimated`, turns `measured`, mix `assumed`. The calibration factor is not applied (TomTom's volumes
are absolute); at 09:00 today the model's speeds were within ~4 km/h of TomTom's on three roads.

## Corridor: Indian driver behaviour and traffic on every arm (Sat 10 Oct)
Spec: `docs/driver-behaviour.md`. Code: `sim/corridor/corridor_runner.py` (VEHICLES, junction_arms, demand),
`sim/corridor/corridor_net.py` (signal_plans). Labels as the doc: measured / estimated / assumed; calibrated = fitted.

| Item (doc section) | Status | Label |
|---|---|---|
| 7 vehicle types, shares 47/19/27/4/3, fast riders 30% of two-wheelers and 50% of autos (the doc's table; its prose says the reverse), sizes, top speeds, pull-away/braking (s2) | built | assumed |
| speeding (speedFactor), following gap / reaction time (s3) | built | assumed |
| capacity x1.35 (s1) | built as following headways / 1.55 (saturation headway 1.31 -> 0.97 s); lanes unchanged, so the templates see the same roads | estimated |
| imperfection 0.5 / 0.6 (s3) | **0.2 / 0.24**: at 0.5 the near-capacity Nanal Nagar section varied ~70 s (sd) between seeds | calibrated (spec 0.5) |
| amber 4 s, red running 2 s (fast) / 1 s / buses and trucks stop at 40 km/h, box blocking 0/5/10 s, 15 s blocker rule (s7) | built (jmDriveAfterYellowTime, jmDriveAfterRedTime + jmDriveRedSpeed, jmIgnoreKeepClearTime, --ignore-junction-blocker 15) | assumed |
| giving way below 1.5 m/s at 30% per 0.5 s; smaller gaps after 30 s (s6) | built (jmIgnoreFoeSpeed/Prob, --time-to-impatience 30) | assumed |
| side streets force in below 5 m/s at 50% (s6) | built: side-street vType variants (`*_side`) for arms that give way | estimated |
| free left in every phase; amber 4 s; protected right-turn phase 12 s; main road >= 65% of the green; cycle 120 s (s5) | built | assumed / estimated |
| one approach at a time at big junctions, 150 s cycle (s5) | built, **off** (`CR_BIG_JUNCTIONS=j02,j08,j09`): each corridor direction gets ~1/4 of the cycle and j02/j08 gridlocked (leg j07-j08 4.6x TomTom) | assumed |
| police-style actuated greens (s5) | not built: the calibration fits static green shares; left for after the demo | - |
| U-turns at signals (s5) | where TomTom's turn ratios show them | measured |
| lateral position, filtering, weaving, side clearance (s4); creeping past the stop line (s7) | out of scope: non-sublane model (sublane was ~11x slower); stop-line creep is a viewer effect (jmStoplineGap 0) | - |

Every arm of every junction now carries traffic, including the ground roads under the flyovers (j03, j04, j06, j07)
and the side roads merging at j10/j11. Each arm takes TomTom Junction Analytics' volume (mean of the minutes between
06 and 23 h) x `cross_scale` and leaves by TomTom's turn shares (left/straight/right/U by angle, probe-weighted);
without TomTom (j01's and j05's TomTom areas lie 1.3-2 km off the corridor; j06's ground arms; j11) volumes and splits
are assumed. No double counting: at each corridor approach TomTom measures, the traffic already arriving (through
traffic, earlier joins and top-ups) is counted first and only the shortfall is added, taking the turning traffic
first. Where TomTom measured an arm on the corridor before a flyover splits off (j04, j07), 81% of its through
traffic stays on the flyover (measured). Demand is planned on the unchanged network, so a variant carries exactly the
baseline's traffic.

Recalibrated (`calibration.json`): 56.6 vs 56.2 min, every leg within 6%; through 1,215 veh/h each way and
`cross_scale` 0.405 (old: 1,500 and 0.5): the Nanal Nagar (j08) eastbound approach is 2 lanes in OSM and cannot take
more, and the calibration lowers all traffic together. Runs take 35-60 s with 3 SUMO processes.

## Next steps (Simulation / Scenarios owners)
1. Templates for `signal_retime`, `bus_lane`, `junction_redesign`, `widening` in `sim/templates/` (same pattern as
   `flyover.py`: plain-XML edit, rebuild, return the network path and any design warnings), then add them to
   `runner.network_for`.
2. (Done 9 Oct, see `gariahat/README.md`.) Gariahat backtest traffic: match the paper's approaches A–E to the network roads (Figure 1 of the paper),
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
