# CityRehearsal — Team E

> Test city infrastructure on a virtual city before spending public money: **Predict, Mitigate, Build.**

Apty Hackathon 2026 · Theme: Sustainable Cities and Communities — Smart cities

## Project overview
**The problem.** Cities invest crores in roads, flyovers, junctions and drainage without being able to reliably test their impact before construction, so problems surface only after projects are completed: congestion shifts to nearby junctions, roads flood, and new infrastructure needs redesign.

**The proposed solution.** CityRehearsal is a virtual environment where cities simulate proposed decisions, compare alternatives, identify unintended consequences and record an evidence-based approval process before construction begins.

**What the team actually built.** _(fill in as you go)_

## Business case
- **Use case:** _who uses this, in what situation, to do what_
- **Go-to-market (first 100 users):** _..._
- **Unit economics:** _..._
- **Business model canvas:** see `docs/business-case.md`
- **12-month plan and what would have to be true:** _..._

## Key features
- [ ] 3D view of YMCA Circle with simulated mixed traffic (Predict)
- [ ] AI agent testing low-cost fixes (Mitigate)
- [ ] Widening and flyover options with ripple and design checks (Build)
- [ ] Review and sign-off flow with logged decisions and evidence fingerprints
- [ ] Gariahat backtest

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
cd frontend && python3 -m http.server 5173   # screen at http://localhost:5173
```

### 2. Simulation with SUMO (simulation and scenarios laptops, 10 minutes)
SUMO 1.28 is installed from the official `eclipse-sumo` Python package into `.venv`, so no Homebrew tap, installer or `SUMO_HOME` setup is needed.
```bash
make setup-sim            # installs eclipse-sumo, sumolib, traci, pyproj; prints the SUMO version
make network              # sim/networks/ymca.osm.xml -> sim/networks/ymca.net.xml
make sim-test             # 10 minutes of random traffic; expect "Inserted: 400", "Running: 0", "Waiting: 0"
python sim/scripts/build_demand.py --scale 0.9   # real baseline traffic (inside .venv)
python sim/scripts/calibrate.py 0.9              # simulated vs TomTom speeds per road
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

Deployed URL: _(add if deployed)_

## Team
Team E: Chetan, Harish, Anushree, Shivam, Vinay, Mudit — _add each person's contribution_
