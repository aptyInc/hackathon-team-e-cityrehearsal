# CityRehearsal — Team E

> Test city infrastructure on a virtual city before spending public money: **Predict, Mitigate, Build.**

Apty Hackathon 2026 · Theme: Sustainable Cities and Communities — Smart cities

## What is CityRehearsal? (plain words)
CityRehearsal is a **rehearsal for road decisions**. We build a computer copy of real roads, fill it with simulated
cars, two-wheelers, autos and buses that behave like real Hyderabad traffic, and check it against measured data. Then
a city can try a change in the copy (a flyover, an underpass, new signal timing, a wider road, a one-way side road)
and see what happens to the trip **before** building anything.

- **Predict** where jams form today.
- **Mitigate** with low-cost fixes first (signal timing).
- **Build** only designs that were tested (flyovers, underpasses, widening).
- Every decision is **reviewed and recorded**: a reviewer re-tests at more and less traffic, a commissioner approves
  with a reason, and the evidence is sealed with a SHA-256 fingerprint.

New to the words? See the [glossary](docs/glossary.md).

## The demo: Lingampally to Lakdikapul, Hyderabad
A real commute of about **22.5 km**, split at **11 junctions** (among them Gachibowli Circle, Tolichowki, Nanal Nagar,
Rethibowli and Masab Tank; full list in `data/corridor/corridor.json`). TomTom measured it at **58.2 minutes** on an average July 2026 day.
The slowest stretch is Nallagandla to the ISB Rd / DLF junction (13.8 min).

On the corridor screen you can:
1. See the trip split by stretch: **measured** by TomTom (REAL) next to our **simulation** (SIMULATED).
2. See **live** delay and queues at 5 junctions (TomTom Junction Analytics: Gachibowli, Tolichowki, Nanal Nagar,
   Rethibowli, NMDC).
3. Add a change at any junction (flyover, underpass, signal retime, widening, one-way side road) and see how many
   minutes the trip gains or loses, and which junction gets worse (ripple).
4. Watch it in 3D, with simulated vehicles driving over the new flyover.

Two more places back up the model:
- **YMCA Circle, Narayanaguda** (Hyderabad): the deep-dive junction. The model's speeds match TomTom within about
  3 km/h (`sim/README.md`).
- **Gariahat, Kolkata**: a backtest on a flyover that was really built, checked against a 2004 before/after study
  (`data/gariahat/README.md`).

An **AI planning assistant** (Claude with tool use) proposes and tests options, cheapest first, and writes a decision
brief. It only builds options from fixed templates and never decides; people do.

Demo script: [docs/demo-script.md](docs/demo-script.md) · Business case: [docs/business-case.md](docs/business-case.md)
· Deck outline: [docs/deck-notes.md](docs/deck-notes.md)

## Quick start (URLs)
With the setup below done:
```bash
make dev                                        # API (mock mode); MOCK_SIM=0 make dev for real simulations
cd frontend && python3 -m http.server 5174      # screens
```
| What | URL |
|---|---|
| Corridor demo (main screen) | http://localhost:5174/corridor.html |
| YMCA Circle 3D view (deep-dive junction) | http://localhost:5174/index.html |
| API, interactive docs | http://localhost:8000/docs |
| API health (`mock: true` means sample data) | http://localhost:8000/health |

Any free port works for the screens (the team uses 5174 because 5173 is often taken). Without the API running, the corridor page still opens and shows sample data, tagged SAMPLE DATA.

## Data sources and labels
Every traffic input is labelled **counted** (or **measured**), **estimated** or **assumed**, and every number on screen
is tagged **REAL** or **SIMULATED**. Full list with files: [data/README.md](data/README.md).

| Source | What we use it for | Label |
|---|---|---|
| TomTom Traffic Stats | Corridor trip and stretch times, July 2026; YMCA road speeds | measured |
| TomTom Junction Analytics | Live delay, queue, vehicles per hour and turn shares at YMCA Circle and 5 corridor junctions | delay and turns measured; queue and volume estimated (TomTom model) |
| IJRAR 2020 study (YMCA Circle) | Vehicle counts by type, road widths | counted (study); 2.0x growth to 2026 estimated |
| Maitra et al. 2004 (Gariahat) | Volumes, turns, before/after delays for the backtest | counted; after-flyover delays are the study's model |
| OpenStreetMap | Road network (lanes, speed limits, junctions) | counted; defaults where missing are assumed |
| Overture Maps | Building footprints for the 3D view | footprints measured; heights mostly assumed |
| Open-Meteo | Rain, July 2026 (rain adds about 5% while raining, low confidence; `data/rain/README.md`) | measured (weather model) |
| Our own settings | Car/auto split, driver following gaps | assumed |

## Workstreams
Each workstream owns one folder (see `CLAUDE.md`). Team members are listed at the end.

| Workstream | Folder | What it owns |
|---|---|---|
| Simulation | `sim/` | SUMO road networks, traffic, calibration, the runner |
| Scenarios | `sim/templates/` | The fixes: flyover, underpass, signal retime, widening, one-way |
| AI agent | `backend/` (incl. `backend/app/agent/`) | API, database, planning assistant, decision brief, fingerprints |
| Frontend and 3D | `frontend/` | Corridor and YMCA screens, 3D map, chat, review screens |
| Data and proof | `data/` | TomTom, counts, buildings, rain, Gariahat |
| Business and pitch | `docs/` | Business case, demo script, deck notes, glossary |
| Contracts | `contracts/` | The data formats everyone shares (AI agent lead only) |

## Project overview
**The problem.** Cities invest crores in roads, flyovers, junctions and drainage without being able to reliably test their impact before construction, so problems surface only after projects are completed: congestion shifts to nearby junctions, roads flood, and new infrastructure needs redesign.

**The proposed solution.** CityRehearsal is a virtual environment where cities simulate proposed decisions, compare alternatives, identify unintended consequences and record an evidence-based approval process before construction begins.

**What the team actually built** (status Fri 9 Oct, evening; the 24-hour build is the roads and traffic module):
- Lingampally to Lakdikapul corridor: road network from OpenStreetMap, TomTom stretch times, live data at 5 junctions,
  the corridor API and the 3D corridor screen with quick demos.
- Five kinds of fixes as templates, each with design checks (for example a warning when flyover lanes squeeze into
  fewer lanes).
- YMCA Circle: calibrated simulation (within about 3 km/h of TomTom), 3D view, simulate any moment since 8 Oct
  from TomTom junction data, or live.
- Case workflow in the API: options, runs, submit with a SHA-256 fingerprint, reviewer must re-run before
  recommending, commissioner decides with a reason (checked by `make smoke`).
- In progress: corridor calibration, planning assistant loop and chat, review screens, Gariahat traffic replay.

## Business case
Full version: [docs/business-case.md](docs/business-case.md).
- **Use case:** a traffic engineer with a jam tests the cheapest fix first, then structures only if needed, on a
  calibrated copy of the corridor; a reviewer re-tests; the decision-maker approves with a reason; the record is sealed.
- **Buyers:** city traffic police, municipal engineering (GHMC), HMDA, metro and smart-city SPVs, traffic and
  engineering consultancies.
- **Go-to-market (first 100 users):** one Hyderabad design partner, 2-3 universities, 5 consultancies, 2 more cities.
- **Unit economics:** subscription per corridor (assumption: Rs 15-25 lakh a year); biggest cost is traffic data
  licences (commercial quote needed).
- **Business model canvas:** see `docs/business-case.md`.
- **12-month plan and what would have to be true:** the model must predict real changes (test: a real signal change,
  predicted before and measured after), data must be affordable, and engineers must trust it enough to act.

## Key features
- [x] Corridor screen: TomTom trip strip, live junction panel, add fixes, 3D view with vehicles (Predict, Build)
- [x] Corridor fix templates: flyover, underpass, signal retime, widening, one-way side road
- [x] 3D view of YMCA Circle with calibrated mixed traffic (Predict)
- [x] Review and sign-off API with logged decisions and evidence fingerprints
- [ ] Corridor calibrated against TomTom trip times
- [ ] AI agent testing low-cost fixes first, with a decision brief (Mitigate)
- [ ] Review and sign-off screens
- [ ] Gariahat backtest replay

## Deployment

### What you need
- **Python 3.10 or newer** (`python3 --version`) and **git**.
- macOS or Linux. On Windows, use WSL, or run the commands inside each `make` target by hand.
- Keys (only for the parts that use them), shared privately, never committed:
  - `ANTHROPIC_API_KEY` — Claude API key from [platform.claude.com](https://platform.claude.com/settings/keys) (needs API credits; a Claude chat or Claude Code plan does not include API use).
  - `TOMTOM_API_KEY` — from the TomTom MOVE menu at [move.tomtom.com](https://move.tomtom.com) (30-day trial: Traffic Stats, Junction Analytics, Area Analytics, O/D Analysis, Route Monitoring).

### 1. App in mock mode (everyone, 10 minutes)
No SUMO needed: the backend serves sample data from `/contracts/samples`.
```bash
git clone git@github.com:aptyInc/hackathon-team-e-cityrehearsal.git
cd hackathon-team-e-cityrehearsal
cp .env.example .env      # paste in the keys you were sent; keep MOCK_SIM=1
make setup                # creates .venv and installs the backend
make dev                  # API at http://localhost:8000 — /health shows {"status":"ok","mock":true}
make smoke                # in a second terminal: must print SMOKE TEST PASSED
cd frontend && python3 -m http.server 5174   # screens at http://localhost:5174/corridor.html and /index.html
```

### 2. Simulation with SUMO (simulation and scenarios laptops, 10 minutes)
SUMO 1.28 is installed from the official `eclipse-sumo` Python package into `.venv`, so no Homebrew tap, installer or `SUMO_HOME` setup is needed.
```bash
make setup-sim            # installs eclipse-sumo, sumolib, traci, pyproj; prints the SUMO version
make network              # sim/networks/ymca.osm.xml -> sim/networks/ymca.net.xml
make sim-test             # 10 minutes of random traffic; expect "Inserted: 400", "Running: 0", "Waiting: 0"
make sim-run              # one real run of today's traffic: C2 result + C1 frames in sim/out/runs/<id>/
python sim/scripts/compare_variants.py           # baseline vs flyover (inside .venv)
MOCK_SIM=0 make dev       # the API runs real simulations instead of sample data
```
Status, calibration results and next steps: [sim/README.md](sim/README.md).
- The road map is an OpenStreetMap extract of the YMCA Circle area (`sim/networks/ymca.osm.xml`, downloaded 9 Oct 2026). To refresh it: `curl -A "cityrehearsal" "https://api.openstreetmap.org/api/0.6/map?bbox=78.4843,17.3902,78.4975,17.4005" -o sim/networks/ymca.osm.xml`
- `sim/scripts/build_network.sh` sets left-hand traffic, keeps main roads only, and uses `sim/networks/india_urban.typ.xml` for speeds and lane counts where OpenStreetMap has none (labelled `assumed`). It then applies `sim/networks/ymca_widths.edg.xml`, which widens the roundabout and the 8 roads touching it to 3 lanes (9.9 m), matching the widths measured in the 2020 study (`counted`).
- The visual editors `sumo-gui` and `netedit` also come with the package. On macOS they need [XQuartz](https://www.xquartz.org) (`brew install --cask xquartz`, then log out and back in).
- To use SUMO's own tools: `export SUMO_HOME=$(python -c "import sumo; print(sumo.SUMO_HOME)")` inside `.venv`.

### 3. Traffic data (data workstream)
All data and its sources are listed in [data/README.md](data/README.md). The files are already in the repo; these commands only refresh them and need `TOMTOM_API_KEY` in `.env`.
- **Hourly speeds** (TomTom Traffic Stats): the request files are in `data/tomtom/*.request.json`; `data/tomtom/fetch_traffic_stats.py` shows the submit, status and download steps. The trial only allows dates in July 2026.
- **YMCA Circle junction data** (TomTom Junction Analytics, junction `6ac7d6870b461bdaf5cd8158`): delay, queue, volume and turn ratios per minute since 8 Oct 23:17. Refresh with `make junction-data` (API only, no MOVE login; TomTom keeps the history, so nothing needs to run in between). Pull it at each checkpoint: Fri 16:00, Fri 22:00, Sat 04:00. For a live 5-minute feed instead: `python3 data/tomtom/collect_junction_live.py` (`--once` for one snapshot).
- If Python reports `CERTIFICATE_VERIFY_FAILED`: run `export SSL_CERT_FILE=$(python -m certifi)` inside `.venv` (python.org Python on macOS ships without certificates), or use `curl` for TomTom calls (the collector already does).
- Building footprints (Overture Maps): `pip install overturemaps` then `overturemaps download --bbox=78.4843,17.3902,78.4975,17.4005 -f geojson --type=building -o data/raw/ymca_buildings.geojson`.

### 4. Corridor API (Lingampally to Lakdikapul)
The backend serves the corridor screen (`frontend/corridor.html`); code in `backend/app/corridor.py`, contract C5.
- `GET /corridor`: the 13 corridor points, TomTom leg times for the typical July day and each day 1-15 July (**measured**), and the route the simulation drives as GeoJSON (A->B and B->A, whole route and per leg). The route is cached in `backend/.cache` after the first call.
- `POST /corridor/runs` `{interventions: [{junction_id: "j07", kind: "flyover", params: {}}], volume_scale}`: a **simulated** journey. With `MOCK_SIM=1` it returns the sample (with a warning when you asked for something else). With `MOCK_SIM=0` it runs SUMO (1-2 minutes, one run at a time) and needs `sim/corridor/calibration.json`. The same request again returns the stored result instantly (`cached: true`); a change to the calibration or to the runner/template code starts a fresh run.
- Long runs: `POST /corridor/runs?async=1` answers at once with `{run_id, status}`; poll `GET /corridor/runs/{run_id}` until `status` is `done` (with `result`) or `failed` (with `error`).
- `GET /corridor/junctions/live`: the latest TomTom Junction Analytics minute per approach at Tolichowki, Nanal Nagar and Rethibowli, plus the last-60-minute mean (delay **measured**, queue and volume **estimated**). Reads `data/raw/tomtom_corridor_junction_live.csv`, or the path in `CR_CORRIDOR_JA_LIVE`.
- `GET /corridor/buildings` (`data/corridor/buildings/index.json`) and `GET /corridor/buildings/{point_id}` (`A_lingampally`, `j01`..`j11`, `B_lakdikapul`): building footprints for the 3D view; 404 with a message until the files exist. Large responses are gzipped.
- Corridor runs work with `GET /runs/{id}`, `WS /stream/{id}` (vehicle `z` passed through, > 0 on flyovers) and `GET /runs/{id}/roads` like YMCA runs.
- Disk: after each real run the API keeps only the newest 15 run folders (`CR_KEEP_RUNS`), at most 1.5 GB (`CR_KEEP_RUNS_MB`), under `sim/out/runs` and `sim/out/corridor` (or `CR_SIM_OUT`), and trims a corridor run's vehicle frames to the runner's playback window (`FRAMES`).

Deployed URL: _(add if deployed)_

## Team
Team E: Chetan, Harish, Anushree, Shivam, Vinay, Mudit — _add each person's contribution_
