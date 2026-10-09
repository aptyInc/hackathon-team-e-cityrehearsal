# Deck notes: 9 slides

One key message per slide. Few words on the slide, the rest in the speaker notes. The live demo sits in the middle
(slide 5); if the demo fails, slide 5 has screenshots as backup (see `docs/demo-script.md`, fallback plan).

All corridor numbers come from the calibrated runs (Fri 9 Oct, evening; table in `docs/demo-script.md`, "The
numbers"). The only open placeholder is `[[ASK]]`. Figures marked *(to verify)* must be checked before they go on a
slide, or dropped.

---

### 1. Title
**Key message:** Test before you build.

**On the slide:** CityRehearsal. "Rehearse a road decision on a copy of the city before spending public money."
Team E. Photo or 3D view of the corridor.

**Speaker notes:** "We are Team E. CityRehearsal lets a city test a road decision on a simulated copy of its real
roads, before it builds anything."

---

### 2. The problem
**Key message:** Cities commit to costly, permanent road projects with little testing, and the jam often just moves.

**On the slide:** Three short lines: "Built first, tested later." "The jam moves to the next junction." "Cheap fixes
get skipped." One example: Gariahat, Kolkata: delay at the flyover junction down 75%, delay into the next junction up
from 42 s to 110 s.

**Speaker notes:** "A flyover takes years to build and can't be undone. At Gariahat in Kolkata, a 2004 study found
the flyover cut delay there by three quarters, but the road into the next junction, Phari, got more than twice as
slow. Overall, peak-hour delay went up. Nobody could test that before building." Optional, if verified: the
Biodiversity flyover on our own corridor was closed weeks after opening in 2019 for a safety review *(to verify)*.

---

### 3. Our corridor: a real one-hour commute
**Key message:** We picked a real, painful trip and measured it.

**On the slide:** Map of Lingampally to Lakdikapul. "22.4 km · 11 junctions · 58 minutes (TomTom, July 2026 average)."
"5 flyovers already on the route · signals at 5 junctions · live data at 10." Trip strip: slowest stretch Nallagandla
to ISB Rd / DLF, 13.8 min; next, Rethibowli to NMDC, 7.5 min.

**Speaker notes:** "This is a commute thousands of people make every day, from Lingampally to Lakdikapul. TomTom
measured it at 58 minutes on an average July day; about 62 on a weekday, 48 on a Sunday. We split it into 12
stretches between junctions, so we can see exactly where the time goes. The main road already crosses five flyovers;
it stops at signals at five junctions: Nallagandla, ISB Road / DLF, Khajaguda, Nanal Nagar and Rethibowli. And ten of
the eleven junctions send us live data every minute."

---

### 4. How it works: Predict, Mitigate, Build
**Key message:** Real data in, a calibrated copy, cheap fixes first, structures only when tested, humans decide.

**On the slide:** A simple left-to-right flow:
Real data (TomTom, OpenStreetMap, counts) → Simulated copy (checked against TomTom) → Options (signal timing first,
then flyover, underpass, widening) → AI assistant compares and writes a brief → Reviewer re-tests at 120% →
Commissioner approves → Sealed record.

**Speaker notes:** "Predict: where do jams form today? Mitigate: what is the cheapest fix that works, like signal
timing? Build: only if needed, and only a design we have tested. Every number on screen says whether it is REAL,
measured, or SIMULATED. Every input says whether it was counted, estimated or assumed."

---

### 5. Live demo
**Key message:** See it work on the real corridor.

**On the slide:** Just the URL and the word "Demo". Backup: 6 screenshots (trip strip with the live panel,
"Tolichowki already has a flyover", the new flyover over Nanal Nagar + Rethibowli in 3D, the DLF ripple chip, the
assistant's answer, the case at 120% with its fingerprint).

**Speaker notes:** Follow `docs/demo-script.md`, beats 0:15 to 3:40 (about 3.5 minutes). Storyline: Predict (58 min
measured, where it goes, live panel) → Trust (55.4 simulated vs 56.2 measured on the same roads; YMCA; Gariahat;
"Tolichowki already has a flyover") → Build where it pays (one flyover over Nanal Nagar + Rethibowli, −2.1 min, cars
on the deck) → Mitigate first and watch the ripple (more green for DLF's side roads: +2.6 min) → the assistant tries
the cheap fix first and advises against a weak DLF flyover → reviewer re-test at 120% (still −2.0 min) →
commissioner approves with a reason; fingerprint.

---

### 6. Why you can trust it
**Key message:** We check the model against reality, and we say how far off it is.

**On the slide:** Three proof points:
- YMCA Circle, Hyderabad: model speeds within about 3 km/h of TomTom.
- Gariahat, Kolkata: our replay cuts delay at Gariahat by 59% (study: 75%); Phari slows in the same direction, and its approach delay doubles if the flyover draws ~15% more traffic (the study expected the inflow to "increase substantially" but gave no number).
- Corridor: simulated trip 55.4 min vs 56.2 min measured by TomTom on the same 21.6 km; every one of the 12
  stretches within about 5%. It drives over the five flyovers that already exist, and refuses to "build" a sixth at
  Tolichowki ("already has a flyover").
Visual: `sim/gariahat/chart.png` (study vs simulator, before and after).
Small print: run-to-run noise about ±0.9 min per option. Simulated main-road traffic is below TomTom's evening
estimates (calibrated to the all-day trip). Rain adds about 5% while it rains (not statistically certain).

**Speaker notes:** "A simulator is only useful if it matches reality. On our corridor it is within 2 percent of
TomTom's trip time, and every stretch within about 5. We calibrated YMCA Circle to TomTom speeds, to within about
3 km/h. We replayed a real flyover from Kolkata and got the same main lesson the researchers did. And we say what we
don't know: our traffic is lighter than TomTom's evening estimates, every result has about a minute of noise, and
rain adds about 5% that we can't be sure of."

---

### 7. Who buys it
**Key message:** Traffic police and consultancies first; municipal engineering and authorities next.

**On the slide:** Table with 5 buyers: traffic police, municipal engineering (GHMC), HMDA, metro and smart-city SPVs,
consultancies. One line each on what they use it for.

**Speaker notes:** "Traffic police own the cheapest fixes, signal timing, which is where the tool shines first.
Consultancies write the traffic studies cities pay for; they buy fastest. Municipal engineering and the metropolitan
authority are the bigger contracts once we have references." First 100 users: 1 design partner in Hyderabad, 2-3
universities, 5 consultancies, 2 more cities (see `docs/business-case.md`).

---

### 8. Business model
**Key message:** A simple subscription per corridor; the cost of one avoided wrong design pays for years of it.

**On the slide:** Junction study (one-off) · Corridor subscription (yearly) · City licence (yearly). Biggest cost:
traffic data licences. "Prices are assumptions; pilot will set them."

**Speaker notes:** "We'd sell a one-off junction study, a yearly subscription per corridor, and a city licence. Our
working assumption is Rs 15 to 25 lakh per corridor per year. The biggest cost is traffic data from TomTom; we need a
commercial quote, and we'd mix in the city's own counts. The value case is simple: if one test stops one wrong design,
or lets a signal change replace a structure, it pays for many years of the subscription."

---

### 9. Next 12 months and the ask
**Key message:** One design partner, one real decision tested and checked against the street.

**On the slide:** Q1 pilot-ready corridor + design partner · Q2 first real decision tested, prediction checked ·
Q3 new corridor in under 2 weeks, 3 consultancies · Q4 100 users. Risks we know: data cost, calibration trust,
liability. The ask: [[ASK]] (for example, an introduction to a city traffic team, or time to run the pilot).

**Speaker notes:** "The most important test is simple: predict the effect of a real signal change before it goes in,
then measure it with TomTom afterwards. If that works, cities will trust the tool for bigger decisions. On liability:
the tool recommends, people decide, and the sealed record shows what was known at the time. Thank you."

---

## Optional slide (if there is time or a question)

### 10. What we built in 24 hours
**Key message:** It is real, and it runs.

**On the slide:** OpenStreetMap network of a 22.4 km corridor with 11 junctions (main road over 5 existing flyovers,
signals at 5); calibrated to TomTom (55.4 vs 56.2 min); live TomTom data at 10 junctions; 5 kinds of fixes (flyover,
underpass, signal timing, widening, one-way); 3D view with simulated vehicles; AI planning assistant (Claude with
tool use, about 7 US cents a question); review and approval flow with SHA-256 fingerprints; YMCA Circle calibrated;
Gariahat backtest.

**Speaker notes:** Credit each workstream: Simulation, Scenarios, AI agent, Frontend and 3D, Data and proof, Business
and pitch. Mention that every number on screen is tagged real or simulated.

---

## Likely questions (prepare one-line answers)

| Question | Answer |
|---|---|
| How accurate is it? | On the corridor: 55.4 min simulated vs 56.2 min measured on the same roads (1.4%), every stretch within about 5%. At YMCA Circle, within about 3 km/h of TomTom speeds. Run to run, results move by about ±0.9 min. We show real and simulated side by side on every screen. |
| Is 2 minutes worth a flyover? | That is the city's call, with the cost in hand; we have no sourced cost yet. Our job is the honest number: 2.1 min, still 2.0 at 20% more traffic, for every trip on the corridor. |
| Why not a flyover at Tolichowki? | There already is one. The main road crosses Tolichowki on the Tolichowki Flyover; the tool says so and builds nothing. |
| Your traffic looks lighter than TomTom's. | Yes. The model carries 1,500 vehicles an hour each way through, plus half of TomTom's evening cross-road volumes: below TomTom's evening estimates. We calibrated to the all-day trip time. That is why the reviewer re-tests at 120%. |
| Why did the assistant's DLF flyover save less than the button? | It chose its own design (50 km/h, default length): −0.9 min against the button's −1.7 (600 m). Both are small and within about a minute of noise of each other; neither is a strong case. |
| Can a cheap fix make things worse? | Yes, and the tool shows it: giving DLF's side roads more green makes the trip 2.6 min slower, as the queue backs up towards Nallagandla. |
| Why not just use Google Maps or TomTom? | They tell you today's traffic. They can't tell you what happens if you build a flyover. We use their data as the starting point. |
| Is the AI making decisions? | No. It proposes and tests options from fixed templates and writes a brief. In our run it advised *against* a flyover at DLF. A reviewer re-tests; a commissioner approves with a reason. |
| What does the data cost? | We used TomTom trial accounts. A commercial price is the biggest unknown in our business case; we would also use the city's own counts. |
| What about two-wheelers and autos? | SUMO's sublane model lets two-wheelers share and filter between lanes; driver settings tuned to Hyderabad speeds. |
| What about rain? | On this corridor, light monsoon rain added about 5% while raining; not statistically certain from 15 days of data. |
| Who is liable if the prediction is wrong? | The tool supports the decision; the sealed record shows the evidence and assumptions at the time; humans sign off. |
