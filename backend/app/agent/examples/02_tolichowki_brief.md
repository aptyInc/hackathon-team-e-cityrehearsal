# Decision brief: Tolichowki (j07): signal retime vs flyover

*Lingampally -> Lakdikapul corridor. Prepared by the CityRehearsal planning assistant on 09 Oct 2026 18:39. This is a recommendation for human review, not a decision.*

## Problem

TomTom (measured, typical July day) puts the corridor at 58.2 min. Tolichowki's approach leg j06->j07 is 4.7 min at 36 km/h, one of the faster legs. The slowest legs are j01->j02 (13.8 min), j09->j10 (7.5 min) and Lingampally->j01 (6.7 min). Live TomTom data shows j07 delays about double the usual (56-59 s vs 28-29 s on two approaches). The simulation runs below are MOCK (sample, illustrative numbers, not a real simulation).

## Options tested

| Option | Cost class | Volume | Trip (min, simulated) | Change vs no change (min) | Run |
|---|---|---|---|---|---|
| baseline (no change) | none | 1.0 | 97.5 | - | `rc_78863c58` |
| flyover at j07 Tolichowki | high (construction) | 1.0 | 93.8 | -3.7 | `rc_c83f5bb3` |
| signal_retime at j07 Tolichowki | low (signal timing) | 1.0 | 95.5 | -2.1 | `rc_856975f1` |

Measured reference: TomTom July 2026 typical day trip time 58.2 min (measured).

## Ripple effects

- **signal_retime at j07 Tolichowki** (volume 1.0): worse at j08 Nanal Nagar jn delay 85->89.2 s, queue 520->546 m.
- **flyover at j07 Tolichowki** (volume 1.0): worse at j08 Nanal Nagar jn delay 85->120 s, queue 520->690 m. slower legs: j07->j08 (Tolichowki -> Nanal Nagar jn) +4.0 min.

## Risks and assumptions

- All trip and junction times for options are **simulated** (SUMO traffic model); only TomTom figures are measured.
- Input labels: sample (assumed).
- **Mock mode (MOCK_SIM=1): these numbers are sample or illustrative data, not simulations. Re-run with MOCK_SIM=0 before any decision.**
- Simulation warning: flyover_j07: 2 flyover lanes land 180 m before Nanal Nagar jn; queues from the junction reach the landing at peak
- Rain: about +5% travel time while raining (estimated from 15 July days, low confidence); not simulated here.
- Volume sensitivity: reviewers should re-run the options at 0.8x and 1.2x volume before deciding.

## Recommendation (for review)

Do not approve a flyover at j07 on this evidence. Approve a j07 signal retime as a low-cost pilot, and look at j08 and the slower legs (j01->j02, j09->j10). Re-run with real SUMO (MOCK_SIM=0) and counted volumes before any construction decision.

- MOCK data: signal retime at j07 -2.1 min vs 97.5 min baseline; flyover -3.7 min. The flyover saves only 1.6 min more.
- Both options push more queue onto j08 Nanal Nagar (delay 85 s to 89 s with retime, to 120 s with flyover).
- Flyover warning: its 2 lanes land 180 m before j08, and queues reach the landing at peak. The j07->j08 leg gets 4.0 min worse.
- Inputs are labelled assumed (sample counts). Volume sensitivity at 0.8 and 1.2 is not yet tested.
- TomTom measured data does not show Tolichowki as the main time loss on the corridor.

The decision rests with the reviewing engineer and the approving authority.

## Evidence

| Run | SHA-256 fingerprint |
|---|---|
| `rc_78863c58` | `73aab82991b287c23f787c3111164a2aa79cc85d145ae3246d8390f313e6756f` |
| `rc_856975f1` | `329e05b5f548c4b5a45b73006e1767caff0f22cc710548e1ca18a0fa21be7547` |
| `rc_c83f5bb3` | `38eefa4f367edb9444a1f3f4652061a2d1cc1f141c80627fce50ddc66d1da213` |
