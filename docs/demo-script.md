# Demo script: 4 minutes, one screen

**Story in one line:** a real 58-minute commute in Hyderabad, measured from real vehicles. Terascope AI copies it into
a simulator with Indian drivers and checks the copy against reality. It advises on each junction, cheap fix first.
One flyover over two signals saves 3 minutes, even in heavy rain. A reviewer re-tests at 10% more traffic; the
commissioner signs off with a tamper-proof record. Build only what was tested.

**The storyline in 7 beats**
1. **Predict:** 58 minutes, where the time goes, what is happening at the junctions right now, the weather now.
2. **Trust:** real 56.2 vs simulated 56.6 on the same roads; "Tolichowki already has a flyover"; YMCA; Gariahat.
3. **Advise:** "What should we do at Nanal Nagar?" Cheap fix first; the signal change is inside the noise; build the
   underpass. One flyover over Nanal Nagar + Rethibowli: **−3.1 min**. Cars on the new deck in 3D; follow a car.
4. **Rain:** heavy rain makes the trip **7.2 min** longer, partly at reported water-logging points. The flyover still wins.
5. **Live:** simulate the corridor as it is right now, tuned to live traffic, in about 20 seconds.
6. **Review:** re-test at 110% traffic. The flyover still saves.
7. **Decide:** the commissioner approves with a reason; every step sealed with a fingerprint; the Decisions log.

**Screens** (one app, `make demo`; the top bar on every page links them all)
- Home: http://localhost:8000/
- Corridor (the whole demo, one screen, no tabs): http://localhost:8000/corridor.html
- YMCA close-up: http://localhost:8000/ymca.html (optional, 3 seconds in the Trust beat)
- Decisions (read-only log): http://localhost:8000/decisions.html · About the data: http://localhost:8000/data.html
- API (backup, every endpoint): http://localhost:8000/docs

**Browser tabs on the demo laptop** (set up in the pre-flight)
- **Tab 1:** Corridor page, fresh (Reset view, nothing simulated yet).
- **Tab 2:** Corridor page with the answer to *"What should we do at Nanal Nagar?"* already on screen. Never reload it.
- **Tab 3:** YMCA close-up (optional).

**Roles on stage:** Presenter (talks), Driver (clicks). The driver never talks; the presenter never touches the mouse.

**Words on stage:** the product is **Terascope AI**. Say **real data** or **measured** for anything measured, and
**simulated** for everything the engine produces. Never name a data vendor or a month on stage; the About-the-data
page names the sources. Never say the old project name.

---

## The numbers

All **simulated** unless marked real data. Every change is measured against the simulation of today's roads (56.6),
not against real data. Noise (run-to-run): about **±0.5 min** for a change at one junction, **±1.5 min** for a
corridor-wide change such as rain. Anything inside the noise is "no clear effect".

| What | Trip | Change |
|---|---|---|
| Real data, typical day, the real 22.4 km route (header, trip strip "Real data · typical day") | 58.2 min | measured |
| Real data on the 21.6 km the simulation drives | 56.2 min | measured |
| Simulated today's roads (**Start engine**), typical day | 56.6 min | +0.7% vs real; every hour 06:00–23:00 within 3% |
| Quick action: Flyover at Nallagandla (j01, 2 lanes, 600 m) | 54.6 min | −2.0 |
| Quick action: Flyover at ISB Rd / DLF (j02, 2 lanes, 600 m) | 54.7 min | −1.9 |
| Quick action: One flyover over Nanal Nagar + Rethibowli (j08, 1.2 km) | **53.5 min** | **−3.1** |
| Quick action: Give DLF's side roads more green (j02 signal, 30% of green to the main road) | 57.3 min | +0.7 (ripple: the queue before DLF) |
| Weather: Light rain, today's roads | 58.1 min | +1.5 |
| Weather: Heavy rain, today's roads | 63.8 min | +7.2, about 2.7 of it at reported water-logging points |
| Heavy rain + the Nanal Nagar + Rethibowli flyover | 61.2 min | −2.6 vs today's roads in heavy rain |
| Reviewer re-test at 110% traffic: Nanal Nagar + Rethibowli flyover | | still saves (read the case table) |
| Advisor at Nanal Nagar: signal retime | | −0.3, inside the noise |

Pre-computed advisor verdicts (**✦ Advise me**; each is "a recommendation for review, not a decision"):

| Junction | Verdict |
|---|---|
| Nanal Nagar | Signal retime is inside the noise (−0.3). Build the underpass. |
| ISB Rd / DLF | Build the flyover. |
| Nallagandla | Build the underpass. |
| Rethibowli | One-way side road first; build nothing yet. |
| Khajaguda | Nothing tested beats the noise; the time is lost elsewhere. |
| Gachibowli, Biodiversity, Shaikpet, Tolichowki, NMDC, Masab Tank | The main road already crosses on a flyover; nothing to build. |

On screen: "Simulated today: 56.6 min (real data 56.2)" after **Start engine**; "With your changes: 53.5 min · −3.1 min
vs the simulation of today's roads (56.6)" after a change.

---

## Beat by beat

| Time | Beat | Click (Driver) | Say (Presenter) |
|---|---|---|---|
| 0:00 | **Hook** | Tab 1. Whole corridor, route in 3D. Point at the header "Lingampally → Lakdikapul · 22.4 km commute through 11 junctions" and the weather chip next to it. | "This is the drive from Lingampally to Lakdikapul in Hyderabad. 22 kilometres, 11 junctions." "On a typical day it takes **58 minutes**. Measured from real vehicles, not guessed." "A flyover costs crores. Today a city finds out if it works only after it is built." |
| 0:15 | **Predict: where the time goes** | Hover the widest block in the trip strip at the bottom (bar "Real data · typical day", tag REAL). | "Each block is one stretch between two junctions. Wider means slower." "The worst: Nallagandla to the ISB Road junction. Almost **14 minutes** of the 58." |
| 0:25 | **Wow 1: right now** | Right panel, **Live junctions**: expand **ISB Rd / DLF**; the map flies there (queues drawn on the road, delay badge on the pin). Collapse it; the map flies back. | "And this is **right now**. Ten of the eleven junctions send live data every minute: delay and queue on every approach." "ISB Road right now: [[LIVE_DELAY]] seconds of delay on its worst approach, against the usual." (Read it off the screen.) "The weather up there is live too. It matters; you will see why." |
| 0:45 | **Trust: the copy** | **Start engine** (about 2 s when cached). Headline under the strip: "Simulated today: 56.6 min (real data 56.2)". | "Now the copy. A simulator drives cars, two-wheelers, autos, buses and trucks through every arm of every junction, with Indian driver behaviour: amber running, box blocking, free lefts, riders filtering to the front." "The simulation drives 21.6 of the 22.4 km. On that distance real data says **56.2** minutes. The simulation says **56.6**. Under one percent, and every hour of the day within three." |
| 1:00 | **Trust: it knows the road** | Under **Simulated**: pick **7 · Tolichowki**, chip **Flyover**. The note appears at once ("The main road already crosses Tolichowki on the Tolichowki Flyover; this would duplicate it."). Optional: Tab 3 for 3 seconds, back. | "It knows the real road. Ask for a flyover at Tolichowki..." "**Tolichowki already has a flyover.** Nothing to build. The main road already uses five flyovers; it stops at signals at five junctions." "We checked it two more ways: at YMCA Circle the model's speeds match real data within **3 km/h**, and we replayed a flyover built in Kolkata, Gariahat: the model finds the same big win the field study found." |
| 1:20 | **Wow 2: Advise** | Switch to **Tab 2** (the answer to *"What should we do at Nanal Nagar?"* already on screen). Scroll slowly through the ranked table. | "Now ask it what to do. We asked before we came on stage: *What should we do at Nanal Nagar?*" "It tries the cheap fix first: a signal retime. **0.3 minutes**: inside the noise, so it says so." "Then the structures. Its answer: **build the underpass.** And it writes that down as a recommendation for review, not a decision." |
| 1:40 | **Build where it pays** | Close the chat (✕). Quick action **One flyover over Nanal Nagar + Rethibowli** (about 2 s). The second bar "Simulated with your changes" appears; point at the headline "With your changes: 53.5 min · −3.1 min". | "Nanal Nagar and Rethibowli are two signals 420 metres apart. One 1.2 km flyover clears both." "The trip drops from 56.6 to **53.5 minutes**: 3.1 minutes saved, for every trip on this road. The other two flyover sites save about 2." |
| 1:55 | **Wow 3: cars on the new deck** | It plays by itself (playback pill at the top of the map; playback runs at 3×, one timeline). In the **Junctions** table click **8 · Nanal Nagar**; the map flies there. Then **Follow a car** in the pill. **Reset view** (R) when done. | "The new flyover in 3D. Simulated vehicles drive over the deck; turning traffic stays on the ground." "Follow a car: one test car's whole trip from Lingampally, past every signal." |
| 2:10 | **Rain** | Weather slider under the changes: drag to **Heavy rain** (both runs re-simulate; cached, seconds). Point at the sentence under the slider ("Heavy rain: expect longer queues at Shaikpet, Tolichowki, Lakdikapul... (reported water-logging points)") and the droplets on the map. Then the headline: "With your changes: 61.2 min · −2.6 min vs the simulation of today's roads (63.8)". | "Monsoon. In heavy rain today's roads take **63.8 minutes**: 7.2 minutes more. About 2.7 of that is at the reported water-logging points, Shaikpet, Tolichowki, Lakdikapul, where the lanes flood." "And the flyover **still wins back 2.6 minutes** in the rain. Rain does not change the case." |
| 2:35 | **Wow 4: Live** | Right panel: point at **Live trip now, A → B** (live minutes vs "Typical day, same hour", confidence). Click **Simulate now** (about 20 s). The clock in the pill says "Simulated now-cast (real data · live)". | "This is the trip right now, from live speeds: [[LIVE_TRIP]] minutes against a typical [[TYPICAL_SAME_HOUR]] at this hour." "**Simulate now** runs the whole corridor as it is this minute, tuned to the live traffic. Twenty seconds." "So a traffic engineer can test a change against today, not against an average." |
| 2:55 | **Review at 110%** | Slider back to **As measured** (cached). **Decision** section: title *"Flyover over Nanal Nagar + Rethibowli"*, your name, **Send for review**. As reviewer: name, **Re-test at 110% traffic** (cached: seconds). Point at the case table. | "The engineer sends it for review." "A second person must re-test it with **10% more traffic**. The evening is busier than a typical day." "At 110% the flyover **still saves**." |
| 3:20 | **Decide + Wow 5: fingerprint** | As decider: name "Commissioner", reason *"Biggest tested saving; holds in heavy rain and at 110% traffic. Approve for detailed design and costing."* **Approve**. Point at the record and its fingerprints. Then top bar: **Decisions**. | "The commissioner approves, and must give a reason." "Every step is sealed with a SHA-256 fingerprint of the evidence. Change one number later and it no longer matches." "Here is the log: who, when, why, and the brief behind it." |
| 3:40 | **Close** | Tab 1, **Reset view**. | "Predict where jams form. Try the cheap fix first. Build only what was tested. Every decision on record." "Terascope AI runs on data cities can buy today, plus their own counts. First buyers: traffic police and municipal engineers." |
| 4:00 | End | | "Thank you." |

If Tab 2 shows different numbers from the table (it was re-asked in the pre-flight), say the numbers on the screen.

## The "wow" moments (do not cut these)
1. **Right now:** live delay and queues at 10 of the 11 junctions, this minute, on the map; the weather now.
2. **It knows the real road:** 56.6 simulated against 56.2 measured, and "Tolichowki already has a flyover".
3. **The advisor:** cheap fix first, inside the noise, build the underpass; a recommendation for review.
4. **Cars on the new flyover** over Nanal Nagar + Rethibowli: 3.1 minutes saved; follow a car.
5. **Rain:** 7.2 minutes lost in heavy rain, with the water-logging points on the map; the flyover still wins 2.6.
6. **Simulate now:** the corridor as it is this minute, in 20 seconds.
7. **Review and seal:** still saves at 110%; commissioner approves with a reason; fingerprint on screen.

## Lines to keep honest
- Say "measured" or "real data" for the 58 minutes, the stretch times, the live panel and the weather. Say
  "simulated" for everything after **Start engine**. Never name the vendor on stage; if asked, "the About-the-data
  page lists every source and its label: counted, estimated or assumed."
- 58 vs 56.2: the real route is 22.4 km; the simulation drives 21.6 km of it. Compare on the same distance: 56.2.
- **Noise:** ±0.5 min for a one-junction change, ±1.5 min corridor-wide. The DLF side-road change (+0.7) is only just
  beyond the noise; say "slightly worse, and the queue moves back towards Nallagandla", not "much worse". The Nanal
  Nagar signal retime (−0.3) is inside it. The two 600 m flyovers (−2.0 / −1.9) are too close to rank.
- **Traffic volume:** the model carries 1,215 vehicles an hour each way end to end, plus 40% of the measured junction
  volumes on every arm. That is lighter than the evening estimates; it is calibrated to the trip time, hour by hour
  (06:00–23:00 within 3%). If asked, say so; it is one reason the reviewer re-tests at 110%.
- The live panel's queue and volume are **estimates**; delay is measured. Masab Tank has no live data.
- **Rain:** the rain factor is estimated from a month of measured hourly trip times and hourly rain (light rain about
  +1.5 min, heavy rain +7.2), low to moderate confidence. "Heavy rain" is the wettest hour measured, not a cloudburst.
  The water-logging points are **reported** in public sources, not measured by us; the simulation slows the lanes
  around them. Do not claim more.
- **Advisor:** the verdicts were pre-computed before the demo (say so). The cost ladder it ranks by is **assumed**
  (retime, then one-way, widening, underpass, flyover). It recommends; people decide. At Khajaguda it says honestly
  that nothing tested beats the noise.
- Gariahat: "reproduces the study's main finding" (delay down 59%, study 75%). Not "matches field data": the study's
  after-numbers are a model too.
- Cost: we have no sourced flyover cost. "Whether 3 minutes is worth a flyover is the city's call. We give them the
  number." Only if a sourced figure is found: "about [[COST]] crore".

---

## What must be ready (check at 08:00 Sat, feature freeze)

| Needed for | Owner | Status at Sat 05:40 | If not ready |
|---|---|---|---|
| Corridor page, one screen: quick actions, Start engine / Run with changes, weather slider with water-logging, junctions, decision, live trip + Simulate now, live junctions, playback pill, Ask Terascope AI | Frontend | Done (`frontend/corridor.html`) | - |
| Live junction panel (10 of 11) and live trip | Data | Done; needs the collector running (`make demo` starts it) and keys valid | Screenshot (see fallback) |
| Calibrated runs with Indian driver behaviour (`MOCK_SIM=0`) | Simulation | Done: 56.6 vs 56.2 min; hourly within 3% (`sim/corridor/calibration.json`) | Recording |
| Advisor verdicts pre-computed for every junction (`✦ Advise me`, chat) | AI agent | Done (`app.agent.advise_all`); re-run after any sim change (rows go `stale`) | `docs/demo-assets/advice-nanal-nagar.png` (to capture) |
| Review / decide (Decision section) and Decisions page | Frontend + AI agent | Done | Show the same calls in http://localhost:8000/docs |
| Gariahat backtest | Simulation | Done (`sim/gariahat/README.md`, `chart.png`): −59% vs study −75% | Show `sim/gariahat/chart.png` on the deck |
| Screenshots of each beat, `live-panel.png`, `advice-nanal-nagar.png`, 4-minute recording `demo.mp4` | Business and pitch + Driver | To do (after build freeze) | - |

## Fallback plan

**Rule:** never debug on stage. If something takes more than 5 seconds, say the fallback line and move on.

| What fails | What you see | Do this | Say this |
|---|---|---|---|
| A quick action, rain run or re-test is slow | Spinner ("Simulating 21 km of traffic, usually under 2 minutes") | The cache was not warmed on this laptop, or the sim code or calibration changed after the warm-up. Do not wait: go to the recording at the same beat. Re-run the warm-up afterwards. | "A real run takes a minute or two; here is the same run from our rehearsal." |
| API not running | Status line "API: ..." in red; strip tagged SAMPLE DATA | Restart `make demo` in the spare terminal. **Do not switch to `MOCK_SIM=1` on stage**: the sample file still shows an old "flyover at Tolichowki" result, which contradicts the story. Use the recording instead. | "Let me show you the recording of the same run." |
| Live panel or live trip missing (collector stopped, key expired) | "Live trip unavailable right now"; empty Live junctions | Show `docs/demo-assets/live-panel.png`; skip **Simulate now**. | "Here is what it showed this morning." |
| Simulate now takes more than 30 s | Spinner under the live trip | Say the line, move to Review. | "The first now-cast in a 10-minute slot takes up to a minute; the next ones are instant." |
| Map tiles or 3D do not load (network) | Grey map | Switch to the screen recording, at the same beat. | "Let me show you the recording of the same run." |
| Tab 2 lost, or the Claude API down | No answer in the chat | Pick **8 · Nanal Nagar** and press **✦ Advise me**: the pre-computed verdict shows without the chat. If that is gone too, show `docs/demo-assets/advice-nanal-nagar.png`. (`assistant-dlf-brief.md` is from the old model and contradicts the new DLF verdict: do not use it.) | "Here is what it advised this morning, to the same question." |
| Laptop dies | - | Second laptop: same branch, servers running, its own warm cache, recording on the desktop. | - |

**Prepare by Sat 08:00** (Business and pitch owner, with the Driver):
- [ ] `docs/demo-assets/`: screenshots of each beat, `live-panel.png`, `advice-nanal-nagar.png`, and a full 4-minute
      screen recording (`demo.mp4`, not in git if over a few MB; keep it on both laptops).
- [ ] Two dry runs with a timer. Cut words, not beats.
- [ ] Browser: zoom 100%, bookmarks bar hidden, notifications off, laptop on power, screen sleep off.

## Pre-flight, 30 minutes before (on both laptops)

1. `make demo` running; http://localhost:8000/health shows `"mock": false`; every page in the top bar loads.
2. Corridor page: the weather chip in the header shows; **Live junctions** shows data less than 15 minutes old;
   **Live trip now** shows minutes, "Typical day, same hour" and a confidence.
3. **Warm the cache** (each laptop has its own). Run the block below. Every line must say `cached`. A line that says
   `NEW RUN` took 1-2 minutes; that is the warm-up working. Run the block again until all lines say `cached`.
   Warm up again after any merge that touches `sim/corridor/calibration.json`, `sim/corridor/corridor_runner.py`,
   `sim/corridor/corridor_net.py` or `sim/templates/corridor.py`: a change there starts fresh runs.
   ```bash
   warm() { curl -s -m 900 -X POST http://localhost:8000/corridor/runs -H 'Content-Type: application/json' -d "$1" |
     python3 -c 'import sys,json; r=json.load(sys.stdin); print("cached " if r.get("cached") else "NEW RUN", round(r["journey"]["total_s"]/60,1), "min")'; }
   NANAL='{"junction_id":"j08","kind":"flyover","params":{"lanes":2,"length_m":1200}}'
   for v in 1 0.8 1.1; do warm '{"volume_scale":'$v',"interventions":[]}'; done                                        # today at 100 / 80 / 110%
   warm '{"volume_scale":1,"interventions":[{"junction_id":"j01","kind":"flyover","params":{"lanes":2,"length_m":600}}]}'   # Nallagandla
   warm '{"volume_scale":1,"interventions":[{"junction_id":"j02","kind":"flyover","params":{"lanes":2,"length_m":600}}]}'   # ISB Rd / DLF
   warm '{"volume_scale":1,"interventions":['$NANAL']}'                                                                    # Nanal Nagar + Rethibowli
   warm '{"volume_scale":1,"interventions":[{"junction_id":"j02","kind":"signal_retime","params":{"cycle_s":120,"corridor_green_share":0.3}}]}'  # DLF side roads
   warm '{"volume_scale":1,"interventions":[],"weather":"heavy_rain"}'                                                     # heavy rain, today
   warm '{"volume_scale":1,"interventions":['$NANAL'],"weather":"heavy_rain"}'                                             # heavy rain + the flyover (Rain beat)
   warm '{"volume_scale":1.1,"interventions":['$NANAL']}'                                                                  # the reviewer's 110% re-test
   ```
   Expected: 56.6 at 100% (note the 80% and 110% values on the cue card); 54.6, 54.7, 53.5, 57.3; 63.8; 61.2; then the
   110% flyover run (lower than the 110% today).
4. **Advisor:** every junction has fresh advice:
   ```bash
   curl -s http://localhost:8000/agent/advice | python3 -c 'import sys,json; d=json.load(sys.stdin); [print(r["junction"], r["status"], "STALE" if r.get("stale") else "ok", (r.get("advice") or {}).get("verdict_code")) for r in d["junctions"]]'
   ```
   Any `STALE` or missing row: `cd backend && CR_DB=$PWD/cityrehearsal.db python -m app.agent.advise_all` (10-15 runs
   per ground junction; do this before the cache warm-up if the sim changed).
5. Click each quick action once in Tab 1: answers in about 2 seconds. Slide the weather to Heavy rain and back. Then
   reload Tab 1 and press **Reset view** (fresh for the hook).
6. **Tab 2:** open the corridor page, **Ask Terascope AI**, click the suggestion *"What should we do at Nanal Nagar?"*.
   With the advice pre-computed it answers in seconds (a fresh run would take minutes). Check: signal retime first
   (−0.3, inside the noise), then the underpass verdict, and a brief. Note its numbers on the cue card if they differ
   from the table above.
7. Recording open on both laptops; second laptop at the same point.

---

## 30-second version (elevator, or if time is cut)

> "This is the drive from Lingampally to Lakdikapul in Hyderabad: 58 minutes, measured from real vehicles. *(trip
> strip)* We copied it into a traffic simulator with Indian drivers: 56.6 minutes against 56.2 measured on the same
> roads. It knows which junctions already have a flyover. *(Ask Terascope AI)* Ask it what to do at Nanal Nagar: it
> tries the signal first, finds nothing, and recommends an underpass. *(Nanal Nagar + Rethibowli)* One flyover over
> two signals saves 3 minutes, still 2.6 in heavy rain, and still saves at 10% more traffic. A reviewer re-tests, the
> commissioner approves with a reason, and the record is sealed with a fingerprint. *(fingerprint)* Terascope AI:
> test before you build."

---

## Placeholders still open

| Placeholder | What | Where it comes from |
|---|---|---|
| `[[LIVE_DELAY]]` | Live delay on the worst approach at ISB Rd / DLF | Read off the Live junctions panel on stage |
| `[[LIVE_TRIP]]` / `[[TYPICAL_SAME_HOUR]]` | Live trip minutes and the typical-day minutes at the same hour (at night about 33 vs 35) | Read off the Live trip card on stage |
| `[[COST]]` | Rough cost of a 1.2 km flyover, only if we find a sourced figure (for example a recent GHMC tender) | Leave the line out if unsourced |
