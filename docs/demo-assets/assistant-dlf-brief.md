# Fallback: the planning assistant's answer on DLF (real run, Fri 9 Oct 21:03)

Use this on stage only if the assistant tab is lost or the Claude API is down. Say: "Here is what it answered
earlier this evening, to the same question." Everything below is copied from the real run (`MOCK_SIM=0`,
model `claude-sonnet-5-5`, about 3 minutes including two new simulations, cost about US$0.07). Session `s_3d069c81`, brief `b_237a34d6`.
All trip times are **simulated** unless they say TomTom.

## The question
> Should we build a flyover at ISB Rd / DLF? Try a cheaper option first.

## What it did, in order
1. `get_corridor`: TomTom July average trip 58.2 min; slowest: j01->j02, j09->j10, A_lingampally->j01
2. `get_live_junctions`: live data for 10 junctions
3. `run_corridor`: signal_retime at j02 ISB Rd / DLF jn (cycle_s=120, corridor_green_share=0.6) @ 1.0x: 55.2 min (-0.2 min vs baseline)
4. `run_corridor`: flyover at j02 ISB Rd / DLF jn (lanes=2, speed_kmh=50) @ 1.0x: 54.5 min (-0.9 min vs baseline)
5. `write_brief`: brief b_237a34d6 written

## Its reply

**I don't recommend the flyover on this evidence.** In the simulation it saves under a minute on a trip of about 55 minutes.

**Where j02 sits.** The stretch into ISB Rd / DLF (j01→j02) is the slowest on the corridor at 13.8 min (TomTom measured). Live TomTom data shows DLF Road southbound delay of 42 s against a usual 17 s, with a queue of about 340 m (the queue is estimated).

| Option at j02 | Trip (simulated) | Change vs baseline 55.4 min |
|---|---|---|
| Signal retime (120 s cycle, 60% corridor green) | 55.2 | −0.2 |
| Flyover (2 lanes, 50 km/h) | 54.5 | −0.9 |

- **Ripple:** The flyover cuts j02 delay from 8.2 s to 0 and the queue from 58 m to 0. Only the j02→j03 leg changes, by −0.8 min. No nearby junction or leg got worse, and there were no design warnings.
- **Retime warning:** Every green phase at j02 already serves the corridor, so only the cycle length changed. That is why the retime gain is so small.
- **Model caveat:** The simulation shows only 8 s of delay at j02, while live TomTom shows 20–42 s on its approaches, so the model may understate the problem there. It has no cross-traffic at j02. Most cross volumes elsewhere are assumed at 450 veh/h, and the vehicle mix and signal plans are assumed. Counts are estimated and calibrated.
- **Where the time is:** The largest measured losses are j01→j02 (13.8 min) and j09→j10 (7.5 min), so a flyover at j02 doesn't address them.

I haven't yet re-run the flyover at 0.8× and 1.2× volume, and there is no cost figure for it. I'd do the volume runs before any construction decision.

The decision brief is saved as **b_237a34d6**, ready to attach to a case. The decision stays with the reviewers.

---

## The decision brief it wrote (`b_237a34d6`)

# Decision brief: ISB Rd / DLF (j02): flyover vs signal retime

*Lingampally -> Lakdikapul corridor. Prepared by the CityRehearsal planning assistant on 09 Oct 2026 21:03. This is a recommendation for human review, not a decision.*

## Problem

TomTom measured trip is 58.2 min over 22.4 km. The leg into j02 (j01->j02) is the slowest at 13.8 min, and j02->j03 takes 4.0 min. Live TomTom shows DLF Road southbound delay of 42 s against a usual 17 s, with a queue of about 340 m (queue estimated). The simulation baseline is 55.4 min (simulated).

## Options tested

| Option | Cost class | Volume | Trip (min, simulated) | Change vs no change (min) | Run |
|---|---|---|---|---|---|
| baseline (no change) | none | 1.0 | 55.4 | - | `rc_3adb7eb5` |
| flyover at j02 ISB Rd / DLF jn (lanes=2, speed_kmh=50) | high (construction) | 1.0 | 54.5 | -0.9 | `rc_7bcaae2e` |
| signal_retime at j02 ISB Rd / DLF jn (cycle_s=120, corridor_green_share=0.6) | low (signal timing) | 1.0 | 55.2 | -0.2 | `rc_1d64b1aa` |

Measured reference: TomTom July 2026 typical day trip time 58.2 min; TomTom time for the simulated window 56.2 min (measured).

## Ripple effects

- **signal_retime at j02 ISB Rd / DLF jn (cycle_s=120, corridor_green_share=0.6)** (volume 1.0): no nearby junction or leg got noticeably worse.
- **flyover at j02 ISB Rd / DLF jn (lanes=2, speed_kmh=50)** (volume 1.0): no nearby junction or leg got noticeably worse.

## Risks and assumptions

- All trip and junction times for options are **simulated** (SUMO traffic model); only TomTom figures are measured.
- Input labels: estimated (estimated).
- Simulation warning: j02 signal_retime: signal 1692848819: every green phase serves the corridor; only the cycle changes
- Rain: about +5% travel time while raining (estimated from 15 July days, low confidence); not simulated here.
- Volume sensitivity: reviewers should re-run the options at 0.8x and 1.2x volume before deciding.

## Recommendation (for review)

Do not approve the flyover on this evidence. A flyover at j02 saves 0.9 min of a 55.4 min trip in simulation, and a signal retime saves 0.2 min. Reviewers could approve the retime as a low-cost trial and look for the main time loss elsewhere, for example j01->j02 (13.8 min) and j09->j10 (7.5 min). Re-run at volume 0.8 and 1.2 before any construction decision.

- Signal retime at j02 (120 s cycle, 60% corridor green): -0.2 min (simulated). The tool warned that every green phase already serves the corridor, so only the cycle length changed.
- Flyover at j02 (2 lanes, 50 km/h): -0.9 min (simulated). j02 delay goes from 8.2 s to 0 and the queue from 58 m to 0. The only leg that changed is j02->j03, by -0.8 min. No design warnings. No downstream junction got worse.
- The simulation gives j02 only 8 s of delay, while live TomTom shows 20-42 s on its approaches. The model may understate j02's problem. Cross-traffic at j02 is not modelled (none), and most cross volumes are assumed at 450 veh/h.
- Counts are estimated and calibrated, signal plans are assumed, and the vehicle mix is assumed. The flyover has no cost figure, and the benefit is small compared with the measured 13.8 min on j01->j02.

The decision rests with the reviewing engineer and the approving authority.

## Evidence

| Run | SHA-256 fingerprint |
|---|---|
| `rc_3adb7eb5` | `530299c2ee5cf2a49620aa8faa9ef00c863fc3a36c82b8da8eb959fad4df6913` |
| `rc_1d64b1aa` | `d9a838d217d532b82bff8220181d7150b92c42c7125b7e430a6921a63264d049` |
| `rc_7bcaae2e` | `e1324fe6a7e664261cb02f64b925d439bfc752b65184d0ebc922d0702473b359` |

Brief fingerprint (SHA-256): `f75fd3ac85cee463c4f78d832a23d8b344b00b734ce2faad46bb69e0dba9bab3`
