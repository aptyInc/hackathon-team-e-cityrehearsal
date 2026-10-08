# CityRehearsal — Team E (Apty Hackathon 2026)

CityRehearsal lets a city test infrastructure decisions on a simulated copy of real roads before building:
**Predict** where jams form, **Mitigate** with low-cost fixes, **Build** only designs that are tested,
with every decision reviewed and recorded. The 24-hour build is the roads and traffic module,
demoed on **YMCA Circle, Narayanaguda, Hyderabad**, plus a Gariahat (Kolkata) backtest.

## Folder ownership — stay in your folder
| Folder | Owner (workstream) | Notes |
|---|---|---|
| `/sim` | Simulation | SUMO network, traffic demand, baseline runs |
| `/sim/templates` | Scenarios | signal_retime, junction_redesign, bus_lane, widening, flyover |
| `/backend` (incl. `/backend/app/agent`) | AI agent | FastAPI, database, agent tools, decision brief |
| `/frontend` | Frontend and 3D | MapLibre + deck.gl 3D view, chat, review screens |
| `/data` | Data and proof | YMCA Circle counts, TomTom exports, Gariahat |
| `/docs` | Business and pitch | business case, demo script, deck notes |
| `/contracts` | AI agent lead only | the four data formats everyone depends on |

When working with Claude Code: edit only your own folder. Read `/contracts`, never edit it unless you own it.

## The four contracts (`/contracts`)
- **C1 vehicle frame** (sim → frontend): `vehicle_frame.schema.json`
- **C2 run result** (sim → agent, frontend, db): `run_result.schema.json`
- **C3 variant spec** (agent → scenarios): `variant_spec.schema.json`
- **C4 workflow API** (frontend → backend): `api.md`

Rules: fields may be **added**, never renamed or removed. Announce any change to the team.
Every contract has a sample in `/contracts/samples` — build against it until the real producer is ready.

## Mocks
`MOCK_SIM=1` (default) makes the backend return sample C2 results and replay sample C1 frames.
Nobody waits for SUMO. Switch to `MOCK_SIM=0` at integration checkpoints.

## Commands
- `make setup` — create venv, install backend deps
- `make dev` — run the API on http://localhost:8000 (mock mode by default)
- `make smoke` — smoke test; must pass before every merge to `main`
- Frontend: open `frontend/index.html` with the API running (or `python3 -m http.server` in `/frontend`)

## Working rules
1. `main` always runs. Run `make smoke` before merging.
2. One branch per person (`sim/...`, `agent/...`, `frontend/...`). Merge every 2–3 hours.
3. Integration checkpoints: Fri 18:00, Sat 00:00, Sat 06:00 — 15-minute pause, one person merges, run the full demo.
4. Feature freeze Sat 10:00. Build freeze Sat 12:00 (final version on `main`).
5. Secrets go in `.env` only (see `.env.example`). No production data, credentials or customer data (handbook rule).
6. Label every traffic input as `counted`, `estimated` or `assumed` (`inputs.counts_source` in C2).
7. The agent builds variants only from templates in `/sim/templates`; it never edits raw network files.
8. Keep the README updated as you go (handbook requirement).

## Tech stack
SUMO (sublane model for two-wheelers) · Python + FastAPI + WebSockets · SQLite + SHA-256 evidence fingerprints ·
Claude API with tool use · MapLibre GL JS + deck.gl (optional: Google Photorealistic 3D Tiles) · TomTom Traffic Stats.
