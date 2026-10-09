# Demo script: 4 minutes, corridor first

**Story in one line:** a real 58-minute commute in Hyderabad, measured by TomTom. We copy it into a simulator and check
the copy against reality. We try new flyovers and a cheap signal change. An AI assistant tests the cheap fix first and
advises against a weak flyover. A reviewer re-tests at 20% more traffic, and the commissioner signs off with a
tamper-proof record. Build only what was tested.

**The storyline in 7 steps**
1. **Predict:** 58 minutes, where the time goes, what is happening right now.
2. **Trust:** the copy matches TomTom; checked at YMCA Circle and Gariahat; it knows the flyovers already on the road.
3. **Build where it pays:** one new flyover over Nanal Nagar + Rethibowli saves 2.1 minutes. Cars on the new deck in 3D.
4. **Mitigate first, watch the ripple:** more green for DLF's side roads makes the trip 2.6 minutes worse.
5. **The AI assistant** tries the cheap fix first, then says "do not build" to a weak flyover.
6. **Review:** re-test at 120% traffic. The Nanal Nagar + Rethibowli flyover still saves 2.0 minutes.
7. **Decide:** the commissioner approves with a reason; every step sealed with a fingerprint.

**Screens** (one app; the top bar on every page links them all)
- Home: http://localhost:5174/
- Corridor (main demo): http://localhost:5174/corridor.html
- YMCA close-up: http://localhost:5174/ymca.html
- Decisions (read-only log): http://localhost:5174/decisions.html · About the data: http://localhost:5174/data.html
- API (backup, every endpoint): http://localhost:8000/docs

**Browser tabs on the demo laptop** (set up in the pre-flight)
- **Tab 1:** Corridor page, "Whole corridor" view. Nothing simulated yet.
- **Tab 2:** Corridor page with the assistant's answer already on screen. Never reload this tab.
- **Tab 3:** YMCA close-up (optional, 3 seconds in the Trust beat).

**Roles on stage:** Presenter (talks), Driver (clicks). The driver never talks; the presenter never touches the mouse.

---

## The numbers

All **simulated** unless marked TomTom. "±" is the run-to-run noise of the simulation (random traffic): treat any
change smaller than about 1 minute as "no clear effect".

| What | Trip | Change |
|---|---|---|
| TomTom, average July day 06:00-23:00, TomTom's own 22.4 km route | 58.2 min | measured |
| TomTom on the 21.6 km our copy drives | 56.2 min | measured |
| Our copy, today's roads ("Simulate today") | 55.4 min | 1.4% under TomTom; every one of the 12 stretches within about 5% |
| Quick demo: Flyover at Nallagandla (j01, 2 lanes, 600 m) | 53.5 min | −1.9 ± 0.8 |
| Quick demo: Flyover at ISB Rd / DLF (j02, 2 lanes, 600 m) | 53.8 min | −1.7 ± 0.9 |
| Quick demo: One flyover over Nanal Nagar + Rethibowli (j08, 1.2 km) | 53.4 min | −2.1 ± 0.9 |
| Quick demo: Give DLF's side roads more green (j02 signal, 30% of green to the main road) | 58.0 min | +2.6 ± 0.9; the stretch Nallagandla → DLF +163 s (+2.7 min) |
| Reviewer re-test at 120% traffic: today | 57.0 min | |
| 120%: Nanal Nagar + Rethibowli flyover | 55.0 min | −2.0 |
| 120%: Nallagandla flyover / DLF flyover | 55.5 / 55.6 min | −1.5 / −1.4 |
| AI assistant (real run, brief `b_237a34d6`): DLF signal retime | 55.2 min | −0.2 (no clear effect) |
| AI assistant: its own DLF flyover design (2 lanes, 50 km/h) | 54.5 min | −0.9 (barely above noise) |

On screen, whole-trip totals are rounded to the minute ("55 → 53 min") and changes show one decimal ("−2.1 min").

---

## Beat by beat

| Time | Beat | Click (Driver) | Say (Presenter) |
|---|---|---|---|
| 0:00 | **Hook** | Tab 1. Whole corridor view, route in 3D. | "This is the drive from Lingampally to Lakdikapul, in Hyderabad. About 22 kilometres." "On an average July day it took **58 minutes**. TomTom measured that, from real vehicles." "A flyover costs crores. Today a city finds out if it works only after it is built." |
| 0:15 | **Predict: where the time goes** | Hover the widest block in the trip strip (row "Measured by TomTom", tag REAL). | "Each block is one stretch between two junctions. Wider means slower." "The worst: Nallagandla to the ISB Road junction. Almost **14 minutes**." "Second worst: Rethibowli to NMDC, seven and a half." |
| 0:30 | **Wow 1: live panel** | Point at "Live now at junctions" (REAL). Click **ISB Rd / DLF** in the panel; the map flies there. | "And this is **right now**. Ten of the eleven junctions on this road send us live data every minute: delay and queue on every approach." "ISB Road / DLF right now: [[LIVE_DELAY]] seconds of delay on its worst approach." (Read the number off the screen.) |
| 0:50 | **Simulate today** | Section 3: **Simulate today** (about 2 s). The SIMULATED row appears above the TomTom row. Point at the line under the strip. | "Now our copy. A simulator drives cars, two-wheelers, autos and buses on the same roads." "Our copy drives 21.6 of TomTom's 22.4 km. On that same distance TomTom says **56.2** minutes. Our copy says **55.4**. Within 2 percent, and every stretch within about 5." |
| 1:10 | **Trust** | Optional: Tab 3 (YMCA) for 3 seconds, back to Tab 1. Then section 2: pick **7 · Tolichowki** and **Flyover**. A note appears at once. Point at "(flyover exists)" in the junction table. | "Why trust it? At YMCA Circle, the model matches TomTom's speeds within about **3 km/h**. And we replayed a real flyover in Kolkata, Gariahat: our copy finds the same big win a 2004 study found, and points to the same next bottleneck." "And it knows the real road. Ask for a flyover at Tolichowki..." "It answers: **Tolichowki already has a flyover.** The main road crosses on it. Nothing to build." "The main road already uses five flyovers. It stops at signals at only five junctions." |
| 1:35 | **Build where it pays** | Quick demos: **One flyover over Nanal Nagar + Rethibowli** (about 2 s). Point at the headline "55 → 53 min" and the green chips. | "Nanal Nagar and Rethibowli are two signals only 420 metres apart. One 1.2 km flyover clears both." "The trip drops from 55.4 to 53.4 minutes. It saves **2.1 minutes**, give or take 0.9." "We tried two other sites: Nallagandla and ISB Road save about the same. This one clears two signals with one structure." |
| 1:50 | **Wow 2: cars on the new deck** | It plays by itself. Click **8 · Nanal Nagar** in the junction table; the map flies there. Optional: **Follow a test car**. | "This is the new flyover in 3D. Simulated cars drive over the deck. Turning traffic stays on the ground." |
| (optional, +20 s) | **Rain what-if** | Section 1: **Hour 18:00–19:00** (the rows re-simulate: 62 min), then **Weather: Heavy rain** (66 min; cached runs take seconds). Point at the trip rows "…18:00–19:00, heavy rain" and the result line "+7.9% (95% range −3.9% to +16.1%) estimated". Then Quick demos: **One flyover over Nanal Nagar + Rethibowli**. | "Monsoon evening. With the heaviest rain July had, the 18:00 trip takes about **3.7 minutes longer**: 62 becomes 66." "And the flyover over Nanal Nagar and Rethibowli **still saves about 2.2 minutes** in that rain. Rain does not change the case." "The rain effect itself is measured hour by hour from a month of TomTom and weather data: about 3% in a rainy hour, 4 to 8% when it keeps raining. An estimate, low to moderate confidence." |
| 2:05 | **Mitigate first, watch the ripple** | Quick demos: **Give DLF's side roads more green (watch the ripple)** (about 2 s). Point at the red chip on the stretch Nallagandla → ISB Rd / DLF (+2.7 min). | "Cheap fixes come first. Signal timing costs almost nothing. But cheap is not automatically good." "Here we give DLF's side roads more green. The trip gets **2.6 minutes worse**." "And look where: the stretch *before* DLF. The queue backs up towards Nallagandla. The jam moved. We see it before anyone touches a signal." |
| 2:25 | **Wow 3: the assistant says no** | Switch to **Tab 2** (answer already on screen). Scroll slowly through the steps. Click **Open the decision brief**, 3 seconds, close. | "Now the planning assistant. It is Claude, connected to our simulator." "We asked it before we came on stage: should we build a flyover at ISB Road? Try a cheaper option first. It took about 3 minutes and cost 7 cents." "It tried the cheap fix first: signal timing. **0.2 minutes.** Then a flyover: **0.9 minutes.**" "Its answer: **do not build on this evidence.** The big losses are elsewhere: before DLF, and after Rethibowli." "It even warns that our model may understate DLF: 8 seconds of delay in the model, 20 to 42 live." "It recommends. People decide." |
| 2:55 | **Review at 120%** | Still Tab 2. Close the chat (✕). Quick demos: **One flyover over Nanal Nagar + Rethibowli** (about 2 s). Section 4: **Send for review**. As reviewer: name, then **Re-test at 120% traffic**. | "Back to the option that paid. We send it for review." "A second engineer must re-test it with **20% more traffic**. The evening is busier than our average day." "At 120%: today 57 minutes, with the flyover 55. **Still saves 2 minutes.**" |
| 3:15 | **Decide + Wow 4: fingerprint** | As decider: name "Commissioner", reason *"Biggest tested saving; holds at 120% traffic. Approve for detailed design and costing."* **Approve**. Point at the record and its fingerprints. Then top bar: **Decisions**. | "The commissioner approves, and must give a reason." "Every step is sealed with a fingerprint of the evidence. Change one number later and it no longer matches." "Here is the log: who, when, why. With the brief that said no to the DLF flyover." |
| 3:40 | **Close** | Tab 1, **Whole corridor**. | "Predict where jams form. Try the cheap fix first. Build only what was tested. Every decision on record." "It runs on data cities can buy today: TomTom, OpenStreetMap and their own counts. First buyers: traffic police and municipal engineers." |
| 4:00 | End | | "Thank you." |

If Tab 2 shows different numbers from the table (it was re-asked in the pre-flight), say the numbers on the screen.

## The "wow" moments (do not cut these)
1. **Live TomTom panel:** real delay and queues at 10 of the 11 junctions, this minute.
2. **It knows the real road:** 55.4 minutes simulated against 56.2 measured, and "Tolichowki already has a flyover".
3. **Cars on the new flyover** over Nanal Nagar + Rethibowli: 2.1 minutes saved.
4. **The ripple:** a "cheap" signal change at DLF pushes the jam back 2.7 minutes onto the stretch before it.
5. **The assistant says no** to a weak flyover; the chosen flyover still saves 2.0 minutes at 120%; commissioner
   approves with a reason; fingerprint on screen.

## Lines to keep honest
- Say "TomTom measured" for the 58 minutes, the stretch times and the live panel. Say "simulated" for everything after
  "Simulate today".
- 58 vs 56.2: TomTom's own route is 22.4 km; our copy drives 21.6 km of it. Compare on the same distance: 56.2.
- **Noise:** every simulated change is ± about 0.9 minutes. Under a minute means "no clear effect". The three flyover
  sites (−1.7 to −2.1) are too close to rank firmly; Nanal Nagar + Rethibowli wins because one structure clears two
  signals and it holds best at 120%.
- **Traffic volume:** the model carries 1,500 vehicles an hour each way through the corridor, plus half of TomTom's
  evening cross-road volumes. That is below TomTom's evening estimates (about 1,500-2,000 vs 3,000-5,700 vehicles an
  hour on the main-road approaches). We calibrated to the all-day trip time, not the evening peak. If asked, say so;
  it is one reason the reviewer re-tests at 120%.
- The live panel's queue and volume are TomTom **estimates**; delay is measured. Masab Tank is the one junction
  without live data.
- At DLF the model shows about 8 s of delay; live TomTom shows 20-42 s. The model may understate DLF. The assistant
  says this itself: let it.
- Rain: "About 3% slower in a rainy hour, 4 to 8% when rain persists; estimated from July 2026, low to moderate
  confidence." "Heavy rain" is July's wettest hours (1–5 mm an hour), not a cloudburst; waterlogging is not modelled.
  Do not claim more.
- Gariahat: "reproduces the study's main finding at Gariahat" (delay down 59%, study 75%). At Phari the direction is
  right; the size matches only if the flyover draws about 15% more traffic. Not "matches field data": the study's
  after-numbers are a model too.
- Cost: we have no sourced flyover cost. Do not quote one. "Whether 2 minutes is worth a flyover is the city's call.
  We give them the number." Only if a sourced figure is found: "about [[COST]] crore".
- The assistant was asked before we went on stage. Say so.

---

## What must be ready (check at 08:00 Sat, feature freeze)

| Needed for | Owner | Status at Fri 21:10 | If not ready |
|---|---|---|---|
| Corridor page: trip strip, 4 quick demos, existing-flyover notes, 3D, follow a test car | Frontend | Done (`frontend/corridor.html`) | - |
| Live junction panel (10 of 11 junctions) | Data | Done; needs the collector running and keys valid | Screenshot (see fallback) |
| Calibrated corridor runs (`MOCK_SIM=0`), routed over the existing flyovers | Simulation | Done: 55.4 vs 56.2 min (`sim/corridor/calibration.json`) | Recording |
| Planning assistant (chat) | AI agent | Done: real run, brief `b_237a34d6`, about 7 US cents | `docs/demo-assets/assistant-dlf-brief.md` |
| Review / decide (corridor section 4) and Decisions page | Frontend + AI agent | Done | Show the same calls in http://localhost:8000/docs |
| Gariahat backtest | Simulation | Done (`sim/gariahat/README.md`, `chart.png`): Gariahat −59% vs study −75%; Phari right direction, size only with ~15% more traffic | Show `sim/gariahat/chart.png` on the deck |
| Screenshots of each beat, `live-panel.png`, 4-minute recording `demo.mp4` | Business and pitch + Driver | To do (after build freeze) | - |

## Fallback plan

**Rule:** never debug on stage. If something takes more than 5 seconds, say the fallback line and move on.

| What fails | What you see | Do this | Say this |
|---|---|---|---|
| A quick demo or re-test is slow | Spinner with a clock ("Simulating 21 km of traffic...") | The cache was not warmed on this laptop, or code or calibration changed after the warm-up. Do not wait: go to the recording at the same beat. Re-run the warm-up afterwards. | "A real run takes a minute or two; here is the same run from our rehearsal." |
| API not running | Status line "API not running ..."; strip tagged SAMPLE DATA | Restart `MOCK_SIM=0 make dev` in the spare terminal. **Do not switch to `MOCK_SIM=1` on stage**: the sample file still shows an old "flyover at Tolichowki" result, which contradicts the story. Use the recording instead. | "Let me show you the recording of the same run." |
| Live TomTom panel missing (collector stopped, key expired) | The "Live now" box is hidden | Show `docs/demo-assets/live-panel.png`. | "Here is what it showed this morning." |
| Map tiles or 3D do not load (network) | Grey map | Switch to the screen recording, at the same beat. | "Let me show you the recording of the same run." |
| Tab 2 lost, or the Claude API down | No answer in the chat | Open `docs/demo-assets/assistant-dlf-brief.md` (the real 21:03 run: steps, reply and brief). | "Here is what it answered this evening, to the same question." |
| Laptop dies | - | Second laptop: same branch, servers running, its own warm cache, recording on the desktop. | - |

**Prepare by Sat 08:00** (Business and pitch owner, with the Driver):
- [ ] `docs/demo-assets/`: screenshots of each beat, `live-panel.png`, and a full 4-minute screen recording
      (`demo.mp4`, not in git if over a few MB; keep it on both laptops). The assistant fallback is already there
      (`assistant-dlf-brief.md`).
- [ ] Two dry runs with a timer. Cut words, not beats.
- [ ] Browser: zoom 100%, bookmarks bar hidden, notifications off, laptop on power, screen sleep off.

## Pre-flight, 30 minutes before (on both laptops)

1. `MOCK_SIM=0 make dev` running; http://localhost:8000/health shows `"mock": false`.
2. `python3 -m http.server 5174` in `/frontend`; http://localhost:5174/ and every page in its top bar load.
3. Live panel shows data less than 15 minutes old.
4. **Warm the cache** (each laptop has its own). Run the block below. Every line must say `cached`. A line that says
   `NEW RUN` took 1-2 minutes; that is the warm-up working. Run the block again until all lines say `cached`.
   Warm up again after any merge that touches `sim/corridor/calibration.json`, `sim/corridor/corridor_runner.py`,
   `sim/corridor/corridor_net.py` or `sim/templates/corridor.py`: a change there starts fresh runs.
   ```bash
   warm() { curl -s -m 900 -X POST http://localhost:8000/corridor/runs -H 'Content-Type: application/json' -d "$1" |
     python3 -c 'import sys,json; r=json.load(sys.stdin); print("cached " if r.get("cached") else "NEW RUN", round(r["journey"]["total_s"]/60,1), "min")'; }
   for v in 1 1.2; do                                                         # today and the reviewer's 120% re-test
     warm '{"volume_scale":'$v',"interventions":[]}'                                                           # today
     warm '{"volume_scale":'$v',"interventions":[{"junction_id":"j01","kind":"flyover","params":{"lanes":2,"length_m":600}}]}'   # Nallagandla
     warm '{"volume_scale":'$v',"interventions":[{"junction_id":"j02","kind":"flyover","params":{"lanes":2,"length_m":600}}]}'   # ISB Rd / DLF
     warm '{"volume_scale":'$v',"interventions":[{"junction_id":"j08","kind":"flyover","params":{"lanes":2,"length_m":1200}}]}'  # Nanal Nagar + Rethibowli
   done
   warm '{"volume_scale":1,"interventions":[{"junction_id":"j02","kind":"signal_retime","params":{"cycle_s":120,"corridor_green_share":0.3}}]}'  # DLF side roads
   warm '{"volume_scale":1,"interventions":[{"junction_id":"j02","kind":"signal_retime","params":{"cycle_s":120,"corridor_green_share":0.6}}]}'  # assistant's retime
   warm '{"volume_scale":1,"interventions":[{"junction_id":"j02","kind":"flyover","params":{"lanes":2,"speed_kmh":50}}]}'                        # assistant's flyover
   ```
   Expected: 55.4, 53.5, 53.8, 53.4 at 100%; 57.0, 55.5, 55.6, 55.0 at 120%; then 58.0, 55.2, 54.5.
5. Click each quick demo once in Tab 1: answers in about 2 seconds. Then reload Tab 1 (fresh for the hook).
6. **Tab 2:** open the corridor page, **Ask CityRehearsal**, click the suggestion *"Should we build a flyover at ISB
   Rd / DLF? Try a cheaper option first."* Allow up to 5 minutes (about 7 US cents). Check: it tries the retime first,
   then a flyover, and writes a brief. Note its numbers on the cue card if they differ from the table above.
7. Recording open on both laptops; second laptop at the same point.

---

## 30-second version (elevator, or if time is cut)

> "This is the drive from Lingampally to Lakdikapul in Hyderabad: 58 minutes, measured by TomTom. *(trip strip)*
> We copied it into a traffic simulator: 55.4 minutes against TomTom's 56.2 on the same roads. It even knows which
> junctions already have a flyover. *(Nanal Nagar + Rethibowli)* One new flyover over two signals saves 2 minutes,
> still 2 at 20% more traffic. *(Tab 2)* Our AI assistant tests the cheap fix first, and it advised against a weak
> flyover at DLF. A reviewer re-tests, the commissioner approves with a reason, and the record is sealed with a
> fingerprint. *(fingerprint)* CityRehearsal: test before you build."

---

## Placeholders still open

| Placeholder | What | Where it comes from |
|---|---|---|
| `[[LIVE_DELAY]]` | Live delay on the worst approach at ISB Rd / DLF | Read off the live panel on stage |
| `[[COST]]` | Rough cost of a 1.2 km flyover, only if we find a sourced figure (for example a recent GHMC tender) | Leave the line out if unsourced |
