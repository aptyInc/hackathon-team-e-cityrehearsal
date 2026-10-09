# Demo script: 4 minutes, corridor first

**Story in one line:** a real 1-hour commute in Hyderabad, measured by TomTom; we copy it into a simulator, try a
flyover and a cheap signal fix, let an AI assistant compare them, and a human reviewer and commissioner sign off with a
tamper-proof record. Build only what was tested.

**Screens**
- Corridor: http://localhost:5174/corridor.html (main demo)
- YMCA Circle (deep-dive junction): http://localhost:5174/index.html
- API (backup, shows every endpoint): http://localhost:8000/docs

**Roles on stage:** Presenter (talks), Driver (clicks). The driver never talks; the presenter never touches the mouse.

Placeholders in `[[double brackets]]` get filled after the corridor calibration run (see the list at the end).

---

## Beat by beat

| Time | Beat | Click (Driver) | Say (Presenter) |
|---|---|---|---|
| 0:00 | **Hook** | Corridor page already open, "Whole corridor" view, Lingampally to Lakdikapul route visible in 3D. | "This is the drive from Lingampally to Lakdikapul. 22 and a half kilometres. On an average day in July it took **58 minutes**." "A city flyover costs crores of rupees. Today a city finds out whether it works only after it is built." |
| 0:20 | **Predict: what is real** | Point at the trip strip at the bottom (row "Measured by TomTom", tag REAL). Hover the widest block. | "Every block is one stretch between two junctions. This is measured by TomTom from real vehicles." "The slowest stretch: Nallagandla to the ISB road, almost **14 minutes**." |
| 0:35 | **Wow 1: live panel** | Point at "Live now at junctions" (REAL, green dots on the map). Click Tolichowki in the panel; the map flies there. | "And this is **right now**. Five junctions on this road send us live data every minute: delay and queue on every approach, against the usual." "Tolichowki right now: [[LIVE_DELAY]] seconds of delay." (Read the number off the screen.) |
| 0:55 | **Simulate today** | Section 3, click **Simulate today**. Second row appears in the trip strip, tag SIMULATED. | "Now our copy. A traffic simulator drives thousands of cars, two-wheelers, autos and buses on the same roads." "Simulated: [[SIM_BASE_MIN]] minutes. Measured: 58. Within [[CAL_GAP_PCT]] percent." |
| 1:15 | **Why trust it** (one breath) | No click. Optional: switch to the YMCA tab for 3 seconds. | "We checked the model twice. At YMCA Circle it matches TomTom's speeds within about **3 km/h**. And on a real Kolkata flyover, Gariahat, it reproduces the 2004 study's big win: delay at Gariahat down 59% (the study: 75%). It also flags the next junction, Phari: if the flyover draws about 15% more traffic, the delay into Phari doubles, as the study warned." |
| 1:30 | **Build: flyover at Tolichowki** | Quick demos: **Flyover at Tolichowki**. Wait for the result (cached, instant). | "Suppose the city wants a flyover at Tolichowki. We build it in the copy first." |
| 1:40 | **Wow 2: the number** | Point at the third strip row and the green delta chips. | "The trip drops from [[SIM_BASE_MIN]] to [[FLYOVER_MIN]] minutes. The flyover saves **[[X]] minutes**." If there is a ripple: "But look: Nanal Nagar, the next junction, gets [[RIPPLE_S]] seconds worse. The jam moved." |
| 1:55 | **Wow 3: cars on the flyover** | Click Tolichowki in the junction table, **Play** (10x), then **Follow a test car**. Let it climb the flyover. | "This is the flyover in 3D, with simulated cars driving over it. Turning traffic stays on the ground." |
| 2:15 | **Mitigate: AI tries the cheap fix first** | Open the planning assistant. Type: *"Tolichowki is slow in the evening. What should we do?"* | "Now the planning assistant. It is Claude, connected to our simulator." "Watch the order. It does **not** start with the flyover. It tries the cheapest fix first: signal timing." (As it runs:) "It gave the main road [[RETIME_SHARE]] percent of the green. Saves [[RETIME_MIN]] minutes, for almost zero cost." "Then it compares with the flyover and writes a one-page brief, with every assumption labelled." |
| 2:50 | **Review: re-test at 120%** | Submit the chosen option. As reviewer, click re-run at **120% traffic**. | "A second engineer reviews it. The system will not let them recommend anything until they re-run it with **20% more traffic**." "At 120%, the option still saves [[X_120]] minutes." (or: "...it breaks down, so the reviewer sends it back.") |
| 3:15 | **Decide + Wow 4: fingerprint** | As commissioner: Approve, type reason *"Cheapest option that still works at 120% traffic"*. Fingerprint appears. | "The commissioner approves and must give a reason." "This code is a fingerprint of all the evidence: every option, every run. Change one number later and it no longer matches. Every decision can be audited." |
| 3:35 | **Close** | Back to the whole-corridor view. | "Predict where jams form. Try the cheap fix first. Build only what was tested. Every decision on record." "It runs on data cities can buy today: TomTom, OpenStreetMap, and their own counts. Our first buyers: traffic police and municipal engineers. Next: every corridor a city plans to spend on." |
| 4:00 | End | | "Thank you." |

## The four "wow" moments (do not cut these)
1. **Live TomTom panel:** real delay and queues at 5 junctions, this minute.
2. **Trip strip:** measured 58 minutes next to the simulated trip, then the flyover saving **[[X]] minutes**.
3. **3D flyover with cars on top:** follow a test car over Tolichowki.
4. **Human sign-off:** reviewer forced to re-test at 120%, commissioner approves with a reason, fingerprint on screen.

## Lines to keep honest
- Say "TomTom measured" for the 58 minutes and the live panel. Say "simulated" for everything after we click Simulate.
- The live panel's queue and volume are TomTom **estimates**; delay is measured. If asked, say so.
- Rain: "Light monsoon showers added about 5% to this trip, and that is not statistically certain." Do not claim more.
- Gariahat: "reproduces the study's finding", not "matches field data after the flyover" (the study's after-numbers
  are a model too).
- If the flyover result is small: say it. "The flyover saves only [[X]] minutes for [[COST]] crore. That is the
  point of testing first."

---

## What must be ready (check at 08:00 Sat, feature freeze)

| Needed for | Owner | Status at Fri 18:35 | If not ready |
|---|---|---|---|
| Corridor page, trip strip, quick demos, 3D, follow a test car | Frontend | Done (`frontend/corridor.html`) | - |
| Live junction panel (5 junctions) | Data | Done; needs the collector running and keys valid | Screenshot (see fallback) |
| Real corridor runs (`MOCK_SIM=0`) with calibration | Simulation | In progress (`sim/corridor-calibration`) | Mock mode: strip shows SAMPLE DATA; say "sample run" |
| Planning assistant (chat) on the corridor | AI agent | Tools defined (`backend/app/agent/tools.py`); loop and UI in progress | Pre-recorded brief + screenshots of the agent's steps |
| Review / decide screens | Frontend + AI agent | Backend done (`/cases/.../submit`, `/review`, `/decide`, smoke test covers it); screen in progress | Show the same calls in http://localhost:8000/docs |
| Gariahat backtest numbers | Simulation | Done (`sim/gariahat/README.md`, `results.json`, `chart.png`): Gariahat −59% vs study −75%; Phari slows in the same direction, and matches the study only with ~15% more traffic drawn by the flyover | Show `sim/gariahat/chart.png`; quote the study's own numbers (74.8% less delay at Gariahat, Phari approach 42 s to 110 s) as the study's |

## Fallback plan

**Rule:** never debug on stage. If something takes more than 5 seconds, say the fallback line and move on.

| What fails | What you see | Do this | Say this |
|---|---|---|---|
| A simulation is slow (real SUMO runs take 1-2 minutes) | Spinner with a clock | Prevent it: run every demo request once before going on stage (warm the cache). The same request then returns instantly (`cached: true`). | - |
| API not running | Status line: "API not running ... the page uses sample data." Strip tagged SAMPLE DATA | Restart `MOCK_SIM=0 make dev` in the spare terminal. If it fails, carry on with sample data. | "This is a saved sample run; the live one gives [[X]] minutes." |
| Simulation errors (gridlock, crash) | Red message | Switch to mock mode: `MOCK_SIM=1 make dev`. Sample results load. | Same as above. |
| Live TomTom panel missing (collector stopped, key expired) | The "Live now" box is hidden | Show screenshot `docs/demo-assets/live-panel.png`. | "Here is what it showed this morning." |
| Map tiles or 3D do not load (network) | Grey map | Switch to the screen recording, at the same beat. | "Let me show you the recording of the same run." |
| Claude API slow or down | Assistant does not answer within 10 s | Open the pre-generated brief `docs/demo-assets/brief-tolichowki.md` and the screenshots of its steps. | "Here is the brief it wrote for the same question earlier today." |
| Laptop dies | - | Second laptop with the same branch, servers already running, and the screen recording on the desktop. | - |

**Prepare by Sat 08:00** (Business and pitch owner, with the Driver):
- [ ] `docs/demo-assets/` with: screenshots of each beat, `live-panel.png`, the brief from a real assistant run, and a
      full 4-minute screen recording (`demo.mp4`, not in git if over a few MB; keep it on both laptops).
- [ ] Warm the cache: baseline, flyover at Tolichowki, Khajaguda retime, Nanal Nagar + Rethibowli, and the 120% re-runs.
- [ ] Two dry runs with a timer. Cut words, not beats.
- [ ] Browser: zoom 100%, bookmarks bar hidden, notifications off, laptop on power, screen sleep off.

**Pre-flight, 30 minutes before**
1. `MOCK_SIM=0 make dev` running; http://localhost:8000/health answers.
2. `python3 -m http.server 5174` in `/frontend`; both pages load.
3. Live panel shows data less than 15 minutes old.
4. Click each quick demo once: answers instantly (cached).
5. Planning assistant answers a test question.
6. Second laptop ready, recording open.

---

## 30-second version (elevator, or if time is cut)

> "This is the drive from Lingampally to Lakdikapul in Hyderabad: 58 minutes, measured by TomTom. *(trip strip)*
> We copied it into a traffic simulator and checked it against real data. *(click Flyover at Tolichowki)*
> A flyover here saves [[X]] minutes. But our AI planning assistant first tries a signal retime, which costs almost
> nothing and saves [[RETIME_MIN]]. *(brief)* A reviewer re-tests at 20% more traffic, the commissioner approves with a
> reason, and the whole decision is sealed with a fingerprint. *(fingerprint)*
> CityRehearsal: test before you build."

---

## Placeholders to fill after calibration

| Placeholder | What | Where it comes from |
|---|---|---|
| `[[SIM_BASE_MIN]]` | Simulated baseline trip, minutes | `POST /corridor/runs` with no interventions, `journey.total_s / 60` |
| `[[CAL_GAP_PCT]]` | Gap between simulated and TomTom trip | `abs(total_s - tomtom_total_s) / tomtom_total_s` |
| `[[FLYOVER_MIN]]`, `[[X]]` | Trip with the Tolichowki flyover, and the saving | Quick demo "Flyover at Tolichowki" |
| `[[RIPPLE_S]]` | Extra delay at Nanal Nagar (j08) with the flyover, if any | Junction table, j08 |
| `[[RETIME_SHARE]]`, `[[RETIME_MIN]]` | Green share the assistant picks, and the saving | Assistant run (or the Khajaguda quick demo as a stand-in) |
| `[[X_120]]` | Saving of the chosen option at 120% traffic | Reviewer re-run, `volume_scale: 1.2` |
| `[[LIVE_DELAY]]` | Read live off the screen | Live panel |
| `[[COST]]` | Rough flyover cost, only if we have a sourced figure | Leave out if unsourced |
