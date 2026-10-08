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
```bash
cp .env.example .env      # add keys; keep MOCK_SIM=1 to run without SUMO
make setup
make dev                  # API at http://localhost:8000
make smoke                # smoke test
# frontend: cd frontend && python3 -m http.server 5173  → http://localhost:5173
```
Deployed URL: _(add if deployed)_

## Team
Team E: Chetan, Harish, Anushree, Shivam, Vinay, Mudit — _add each person's contribution_
