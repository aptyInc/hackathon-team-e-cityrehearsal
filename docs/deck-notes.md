# Deck notes: 9 slides

One key message per slide. Few words on the slide, the rest in the speaker notes. The live demo sits in the middle
(slide 5); if the demo fails, slide 5 has screenshots as backup (see `docs/demo-script.md`, fallback plan).

Numbers in `[[double brackets]]` are filled after the corridor calibration run. Figures marked *(to verify)* must be
checked before they go on a slide, or dropped.

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

**On the slide:** Map of Lingampally to Lakdikapul. "22.5 km · 11 junctions · 58 minutes (TomTom, July 2026 average)."
Trip strip: slowest stretch Nallagandla to ISB Rd, 13.8 min.

**Speaker notes:** "This is a commute thousands of people make every day, from Lingampally to Lakdikapul. TomTom
measured it at 58 minutes on an average July day; about 62 on a weekday, 48 on a Sunday. We split it into 12
stretches between junctions, so we can see exactly where the time goes. And five of the junctions send us live data
every minute."

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

**On the slide:** Just the URL and the word "Demo". Backup: 4 screenshots (trip strip, live panel, flyover in 3D,
fingerprint).

**Speaker notes:** Follow `docs/demo-script.md`, beats 0:20 to 3:35 (about 3 minutes). Wow moments: live TomTom panel;
58 minutes measured vs [[SIM_BASE_MIN]] simulated; flyover at Tolichowki saves [[X]] min; cars driving over the
flyover in 3D; assistant tries signal retime first; reviewer re-test at 120%; commissioner approves; fingerprint.

---

### 6. Why you can trust it
**Key message:** We check the model against reality, and we say how far off it is.

**On the slide:** Three proof points:
- YMCA Circle, Hyderabad: model speeds within about 3 km/h of TomTom.
- Gariahat, Kolkata: our replay cuts delay at Gariahat by 59% (study: 75%); Phari slows in the same direction, and its approach delay doubles if the flyover draws ~15% more traffic (the study expected the inflow to "increase substantially" but gave no number).
- Corridor: simulated trip [[SIM_BASE_MIN]] min vs 58.2 min measured.
Small print: rain adds about 5% while it rains (not statistically certain).

**Speaker notes:** "A simulator is only useful if it matches reality. We calibrated YMCA Circle to TomTom speeds, to
within about 3 km/h. We replayed a real flyover from Kolkata and got the same lesson the researchers did. And we say
what we don't know: for example, rain only adds about 5% on this trip, and we can't be sure even of that."

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

**On the slide:** OpenStreetMap network of a 22.5 km corridor with 11 junctions (10 with signals); 5 live TomTom junctions;
5 kinds of fixes (flyover, underpass, signal timing, widening, one-way); 3D view with simulated vehicles; review and
approval flow with SHA-256 fingerprints; YMCA Circle calibrated; Gariahat backtest.

**Speaker notes:** Credit each workstream: Simulation, Scenarios, AI agent, Frontend and 3D, Data and proof, Business
and pitch. Mention that every number on screen is tagged real or simulated.

---

## Likely questions (prepare one-line answers)

| Question | Answer |
|---|---|
| How accurate is it? | At YMCA Circle, within about 3 km/h of TomTom speeds. On the corridor, [[CAL_GAP_PCT]]% of the measured trip time. We show both side by side on every screen. |
| Why not just use Google Maps or TomTom? | They tell you today's traffic. They can't tell you what happens if you build a flyover. We use their data as the starting point. |
| Is the AI making decisions? | No. It proposes and tests options from fixed templates and writes a brief. A reviewer re-tests; a commissioner approves with a reason. |
| What does the data cost? | We used TomTom trial accounts. A commercial price is the biggest unknown in our business case; we would also use the city's own counts. |
| What about two-wheelers and autos? | SUMO's sublane model lets two-wheelers share and filter between lanes; driver settings tuned to Hyderabad speeds. |
| What about rain? | On this corridor, light monsoon rain added about 5% while raining; not statistically certain from 15 days of data. |
| Who is liable if the prediction is wrong? | The tool supports the decision; the sealed record shows the evidence and assumptions at the time; humans sign off. |
