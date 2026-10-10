# Deck notes: 9 slides

One key message per slide. Few words on the slide, the rest in the speaker notes. The live demo sits in the middle
(slide 5); if the demo fails, slide 5 has screenshots as backup (see `docs/demo-script.md`, fallback plan).

All corridor numbers come from the final calibrated runs (Sat 10 Oct, early morning; table in `docs/demo-script.md`,
"The numbers"). The only open placeholder is `[[ASK]]`. Figures marked *(to verify)* must be checked before they go on
a slide, or dropped.

**Words:** the product is **Terascope AI**. On slides say **real data** / **measured** and **simulated**; never a data
vendor or a month (the About-the-data page in the app names every source). Never the old project name.

---

### 1. Title
**Key message:** Test before you build.

**On the slide:** Terascope AI. "Rehearse a road decision on a copy of the city before spending public money."
Team E. Photo or 3D view of the corridor.

**Speaker notes:** "We are Team E. Terascope AI lets a city test a road decision on a simulated copy of its real
roads, with real traffic data and Indian drivers, before it builds anything."

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

**On the slide:** Map of Lingampally to Lakdikapul. "22.4 km · 11 junctions · 58 minutes on a typical day (real data,
measured from vehicles)." "5 flyovers already on the route · signals at 5 junctions · live data at 10 · weather live."
Trip strip: slowest stretch Nallagandla to ISB Rd / DLF, 13.8 min; next, Rethibowli to NMDC, 7.5 min.

**Speaker notes:** "This is a commute thousands of people make every day, from Lingampally to Lakdikapul. Real data
puts it at 58 minutes on a typical day. We split it into 12 stretches between junctions, so we can see exactly where
the time goes. The main road already crosses five flyovers; it stops at signals at five junctions: Nallagandla, ISB
Road / DLF, Khajaguda, Nanal Nagar and Rethibowli. Ten of the eleven junctions send us live data every minute, and
the weather on the corridor is live too."

---

### 4. How it works: Predict, Mitigate, Build
**Key message:** Real data in, a calibrated copy, cheap fixes first, structures only when tested, humans decide.

**On the slide:** A simple left-to-right flow:
Real data (traffic, live junctions, weather, OpenStreetMap, counts) → Simulated copy with Indian drivers (checked
against real data) → Options, cheapest first (signal timing, one-way, widening, underpass, flyover) → Terascope AI
advises and writes a brief → Reviewer re-tests at 80% / 110% traffic → Commissioner approves with a reason → Sealed
record.

**Speaker notes:** "Predict: where do jams form today, and right now? Mitigate: what is the cheapest fix that works,
like signal timing? Build: only if needed, and only a design we have tested, in dry weather and in heavy rain. Every
number on screen says whether it is real data or simulated. Every input says whether it was counted, estimated or
assumed. The AI advises; it never decides."

---

### 5. Live demo
**Key message:** See it work on the real corridor.

**On the slide:** Just the URL (http://localhost:8000/) and the word "Demo". Backup: 7 screenshots (trip strip with
the live junctions and the weather chip, "Tolichowki already has a flyover", the advisor's answer for Nanal Nagar, the
new flyover over Nanal Nagar + Rethibowli in 3D, heavy rain with the water-logging droplets, Simulate now, the case at
110% with its fingerprint).

**Speaker notes:** Follow `docs/demo-script.md`, beats 0:15 to 3:40 (about 3.5 minutes). Storyline: Predict (58 min
measured, where it goes, live junctions, weather now) → Trust (56.6 simulated vs 56.2 measured on the same roads;
"Tolichowki already has a flyover"; YMCA; Gariahat) → Advise ("What should we do at Nanal Nagar?": cheap fix first,
inside the noise, build the underpass; one flyover over Nanal Nagar + Rethibowli −3.1 min; cars on the deck; follow a
car) → Rain (heavy rain +7.2 min with the reported water-logging points; the flyover still wins 2.6) → Live (Simulate
now, about 20 s) → Review at 110% (still saves) → Decide (commissioner approves with a reason; fingerprint; the
Decisions log).

---

### 6. Why you can trust it
**Key message:** We check the model against reality, and we say how far off it is.

**On the slide:** Three proof points:
- Corridor: simulated trip 56.6 min vs 56.2 min measured on the same 21.6 km; every hour from 06:00 to 23:00 within
  3%. Traffic on all 42 junction arms, seven vehicle types, Indian driver behaviour (amber and red running, box
  blocking, free left, protected right, U-turns, fast riders). It drives over the five flyovers that already exist,
  and refuses to "build" a sixth at Tolichowki ("already has a flyover").
- YMCA Circle, Hyderabad: model speeds within about 3 km/h of real data.
- Gariahat, Kolkata: our replay cuts delay at Gariahat by 59% (study: 75%); Phari slows in the same direction, and its
  approach delay doubles if the flyover draws ~15% more traffic (the study expected the inflow to "increase
  substantially" but gave no number).
Visual: `sim/gariahat/chart.png` (study vs simulator, before and after).
Small print: run-to-run noise about ±0.5 min for a change at one junction, ±1.5 min corridor-wide. Simulated traffic
is lighter than the evening estimates (calibrated to the trip time, hour by hour). Rain: light rain +1.5 min, heavy
rain +7.2 min, estimated from a month of measured hourly trips and hourly rain (low to moderate confidence);
water-logging points are reported, not measured by us.

**Speaker notes:** "A simulator is only useful if it matches reality. On our corridor it is within one percent of the
measured trip time, and every hour of the day within three. The drivers behave like Hyderabad drivers: riders filter
to the front, the box gets blocked, the amber gets run. We calibrated YMCA Circle to measured speeds, to within about
3 km/h. We replayed a real flyover from Kolkata and got the same main lesson the researchers did. And we say what we
don't know: our traffic is lighter than the evening estimates, every one-junction result has half a minute of noise,
and the rain effect is an estimate."

---

### 7. Who buys it
**Key message:** Traffic police and consultancies first; municipal engineering and authorities next.

**On the slide:** Table with 5 buyers: traffic police, municipal engineering (GHMC), HMDA, metro and smart-city SPVs,
consultancies. One line each on what they use it for.

**Speaker notes:** "Traffic police own the cheapest fixes, signal timing, which is where the tool shines first, and
'Simulate now' gives them the corridor as it is this minute. Consultancies write the traffic studies cities pay for;
they buy fastest. Municipal engineering and the metropolitan authority are the bigger contracts once we have
references." First 100 users: 1 design partner in Hyderabad, 2-3 universities, 5 consultancies, 2 more cities (see
`docs/business-case.md`).

---

### 8. Business model
**Key message:** A simple subscription per corridor; the cost of one avoided wrong design pays for years of it.

**On the slide:** Junction study (one-off) · Corridor subscription (yearly) · City licence (yearly). Biggest cost:
traffic data licences. "Prices are assumptions; pilot will set them."

**Speaker notes:** "We'd sell a one-off junction study, a yearly subscription per corridor, and a city licence. Our
working assumption is Rs 15 to 25 lakh per corridor per year. The biggest cost is commercial traffic data; we need a
quote, and we'd mix in the city's own counts. The value case is simple: if one test stops one wrong design, or lets a
signal change replace a structure, it pays for many years of the subscription."

---

### 9. Next 12 months and the ask
**Key message:** One design partner, one real decision tested and checked against the street.

**On the slide:** Q1 pilot-ready corridor + design partner · Q2 first real decision tested, prediction checked ·
Q3 new corridor in under 2 weeks, 3 consultancies · Q4 100 users. Risks we know: data cost, calibration trust,
liability. The ask: [[ASK]] (for example, an introduction to a city traffic team, or time to run the pilot).

**Speaker notes:** "The most important test is simple: predict the effect of a real signal change before it goes in,
then measure it afterwards. If that works, cities will trust the tool for bigger decisions. On liability: the tool
recommends, people decide, and the sealed record shows what was known at the time. Thank you."

---

## Optional slide (if there is time or a question)

### 10. What we built in 24 hours
**Key message:** It is real, and it runs.

**On the slide:** OpenStreetMap network of a 22.4 km corridor with 11 junctions (main road over 5 existing flyovers,
signals at 5, traffic on all 42 arms); Indian driver behaviour (`docs/driver-behaviour.md`); calibrated to real data
(56.6 vs 56.2 min, every hour within 3%); live data at 10 junctions and a live trip estimate; "Simulate now"
now-cast tuned to live traffic; weather now and a rain what-if with reported water-logging points; 5 kinds of fixes
(flyover, underpass, signal timing, widening, one-way); 3D view with simulated vehicles and follow-a-car; Terascope
AI advisor (Claude with tool use; cheapest first; pre-computed verdict for every junction; writes a brief); review at
80% / 110% and approval with SHA-256 fingerprints; YMCA Circle calibrated; Gariahat backtest.

**Speaker notes:** Credit each workstream: Simulation, Scenarios, AI agent, Frontend and 3D, Data and proof, Business
and pitch. Mention that every number on screen is tagged real data or simulated.

---

## Likely questions (prepare one-line answers)

| Question | Answer |
|---|---|
| How accurate is it? | On the corridor: 56.6 min simulated vs 56.2 min measured on the same roads (under 1%), every hour 06:00–23:00 within 3%. At YMCA Circle, within about 3 km/h of measured speeds. Run to run, a one-junction result moves by about ±0.5 min, a corridor-wide one by ±1.5. We show real and simulated side by side on every screen. |
| Is 3 minutes worth a flyover? | That is the city's call, with the cost in hand; we have no sourced cost yet. Our job is the honest number: 3.1 min, 2.6 in heavy rain, still saving at 10% more traffic, for every trip on the corridor. |
| Why not a flyover at Tolichowki? | There already is one. The main road crosses Tolichowki on the Tolichowki Flyover; the tool says so and builds nothing. Same at Gachibowli, Biodiversity, Shaikpet, NMDC and Masab Tank. |
| Why does the advisor say underpass at Nanal Nagar, but you showed a flyover? | Both are structures that clear the signal; the advisor ranks by minutes saved beyond the noise, ripple, robustness in rain and at 110%, and an assumed cost ladder, and picks the underpass at that junction. The quick action is one 1.2 km flyover over two signals, Nanal Nagar and Rethibowli, which is why it saves more. Either way: the signal retime alone (−0.3) is inside the noise. |
| What about ISB Rd / DLF? | The advisor's verdict there is to build the flyover (−1.9 min as a quick action). Giving DLF's side roads more green makes the trip 0.7 min slower and moves the queue back towards Nallagandla: cheap is not automatically good. |
| Your traffic looks lighter than the evening estimates. | Yes. The model carries 1,215 vehicles an hour each way end to end, plus 40% of the measured junction volumes on every arm. It is calibrated to the measured trip time, hour by hour. That is why the reviewer re-tests at 110%. |
| What about rain? | Heavy rain adds 7.2 min to the trip, about 2.7 of it at reported water-logging points (Shaikpet, Tolichowki, Lakdikapul and others); light rain adds 1.5. The rain factor is estimated from a month of measured hourly trips and hourly rain, low to moderate confidence. The flyover still saves 2.6 min in heavy rain. |
| What is "Simulate now"? | A now-cast: the typical-day model for this hour, tuned so its trip matches the live trip from live speeds, then run with the roads as they are (about 20 s once warm). A traffic engineer can test a change against today, not an average. |
| Why not just use Google Maps or a traffic-data vendor? | They tell you today's traffic. They can't tell you what happens if you build a flyover. We use their data as the starting point. |
| Is the AI making decisions? | No. It tests options from fixed templates, cheapest first, and writes a brief marked "a recommendation for review, not a decision". A reviewer re-tests at 80% or 110%; a commissioner approves with a reason; every step is fingerprinted. |
| What does the data cost? | We used trial accounts of a commercial traffic-data vendor (TomTom). A commercial price is the biggest unknown in our business case; we would also use the city's own counts. |
| What about two-wheelers and autos? | Seven vehicle types in SUMO's sublane model: two-wheelers and autos filter between lanes and gather at the front of the queue; fast riders speed, weave and run the amber. Each behaviour is labelled measured, estimated or assumed (`docs/driver-behaviour.md`). |
| Who is liable if the prediction is wrong? | The tool supports the decision; the sealed record shows the evidence and assumptions at the time; humans sign off. |
