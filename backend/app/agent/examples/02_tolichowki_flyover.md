# Should we build a flyover at Tolichowki?

*Recorded 9 Oct 2026 with `claude-sonnet-5-5`, API on MOCK_SIM=1 with CR_MOCK_SYNTH=1: TomTom figures are real (measured); every simulated number is illustrative mock data, as the assistant says. Re-record with MOCK_SIM=0 once the corridor simulation is calibrated.*

**User:** Should we build a flyover at Tolichowki? Try a cheaper option first.

<details><summary>Tool calls</summary>

- `get_corridor`  -> TomTom July average trip 58.2 min; slowest: j01->j02, j09->j10, A_lingampally->j01
- `get_live_junctions`  -> live data for 5 junctions
- `run_corridor` {"interventions": [{"junction_id": "j07", "kind": "signal_retime", "params": {}}]} -> signal_retime at j07 Tolichowki @ 1.0x: 95.5 min (-2.1 min vs baseline) [mock]
- `run_corridor` {"interventions": [{"junction_id": "j07", "kind": "flyover", "params": {}}]} -> flyover at j07 Tolichowki @ 1.0x: 93.8 min (-3.7 min vs baseline) [mock]
- `write_brief`  -> brief b_5e90ded2 written

</details>

**Assistant:**

**I wouldn't recommend a flyover at Tolichowki (j07) on this evidence. A signal retime looks like the better first step.**

**The simulation is in mock mode (MOCK_SIM=1).** Every simulated number below is sample or illustrative data, not a real simulation. The inputs are labelled "assumed".

**Measured TomTom data**
- The typical July trip is 58.2 min.
- The leg into Tolichowki (j06->j07) takes 4.7 min at 36 km/h, which is one of the faster legs.
- The biggest losses are on j01->j02 (13.8 min), j09->j10 (7.5 min) and Lingampally->j01 (6.7 min).
- Live data shows Tolichowki delays about double their usual level (56–59 s against 28–29 s on two approaches). So the junction is congested, but it isn't the main loss on the corridor.

**Simulated results (mock)** (baseline 97.5 min)

| Option | Trip change | Ripple |
|---|---|---|
| Signal retime at j07 | −2.1 min | j08 Nanal Nagar delay 85 s → 89 s |
| Flyover at j07 | −3.7 min | j08 delay 85 s → 120 s; j07->j08 leg 4.0 min slower |

- The flyover saves only 1.6 min more than the retime.
- The flyover design warning is that its 2 lanes land 180 m before j08, and peak queues reach the landing.
- Both options move congestion downstream to j08.

**Recommendation (for reviewers to decide)**
- Pilot the retime at j07.
- Look at j08 and the slower legs before any construction.
- Re-run with real SUMO and counted volumes, including volume at 0.8 and 1.2, before anyone decides on construction.

The brief is saved as **b_5e90ded2**, so it can be attached to a case for review.

*(5 tool calls, ~$0.0404 API cost)*

---

**User:** Does the signal retime still help if traffic grows 20%? Keep it short.

<details><summary>Tool calls</summary>

- `run_corridor` {"interventions": [{"junction_id": "j07", "kind": "signal_retime", "params": {}}], "volume_scale": 1.2} -> signal_retime at j07 Tolichowki @ 1.2x: 121.4 min (-3.0 min vs baseline) [mock]

</details>

**Assistant:**

**Yes, in this run the retime still helps at +20% traffic. The numbers are mock (MOCK_SIM=1): illustrative sample data, not a real simulation, with assumed inputs.**

| Volume | Baseline | With j07 retime | Change |
|---|---|---|---|
| 1.0× | 97.5 min | 95.5 min | −2.1 min |
| 1.2× | 124.4 min | 121.4 min | −3.0 min |

- The saving is slightly larger at 1.2× (−3.0 min against −2.1 min).
- Tolichowki delay falls from 100.8 s to 80.6 s, and its queue from 691 m to 553 m.
- The ripple is the same as before. Nanal Nagar (j08) gets a little worse, with delay going from 122.4 s to 128.5 s and its queue from 749 m to 786 m.
- The retime saves only about 3 min out of a 124 min trip. Growth of 20% adds about 27 min to the baseline, which is far more than the retime recovers. So it helps, but it doesn't solve the problem.

I haven't re-run the flyover at 1.2×. I also haven't re-run anything with real SUMO. I'd do both before reviewers decide. The run ID for this result is rc_2f4c2151.

*(1 tool calls, ~$0.0128 API cost)*

---

The brief was then attached to a corridor case over the API: `POST /corridor/cases` (case `cc_36c83ce5`, stage proposed) -> `POST /corridor/cases/{id}/review` by a traffic engineer at volume 1.2 (re-ran the retime, the flyover and the baseline) -> `POST /corridor/cases/{id}/decide` by the commissioner: **revise** ("Pilot the retime; re-run with real SUMO before considering the flyover"). Final record fingerprint `f952d96e38b60ce0ba424842e6d6d234f28019416e93f535de326eab3aa45f5f`.
