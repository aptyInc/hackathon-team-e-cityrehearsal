# Business case: CityRehearsal (Team E)

**In one sentence:** CityRehearsal lets a city test a road decision (a flyover, a signal change, a wider road) on a
simulated copy of its real roads before spending money, and keeps a sealed record of who decided what and why.

**How to read the numbers in this document.** We label every figure, the same way the product labels its inputs:
- **measured**: from our own data in this repo (TomTom, studies), with the file named.
- **sourced (to verify)**: a published figure we are fairly sure of, but have not re-checked against the original in
  the last 24 hours. Check before quoting it on stage.
- **assumption**: our working guess. It needs a customer conversation or a quote to confirm.

---

## 1. The problem

**Cities decide big road projects with little testing.** A flyover or an underpass takes years and large sums to
build. Once it is built, it cannot be undone. Traffic studies exist, but they are usually one-off reports for one
junction. They rarely show what happens at the next junction, and they are not re-run when traffic changes.

**What goes wrong:**
- **The jam moves instead of going away.** At Gariahat in Kolkata, a 2004 study (Maitra et al., in `data/gariahat/`)
  found the flyover cut average delay at Gariahat by 74.8% (35.3 s to 8.9 s), but delay on the road into the next
  junction, Phari, rose from 42.4 s to 110.3 s. Across both junctions, peak-hour delay went **up** by 29.8
  vehicle-hours. (measured, from the study; its after-flyover numbers are the study's own model)
- **Design problems show up after opening.** Our own corridor passes the Biodiversity junction flyover in Hyderabad
  (`j04`). It opened in late 2019 and was closed within weeks for a safety review after a fatal crash; speed limits
  and design changes followed. (sourced, to verify dates and details before quoting)
- **Cheap fixes get skipped.** Signal timing, a one-way side road or a turn ban cost almost nothing and can be tried in
  days, but there is no quick way to show a committee that they would work. So the expensive structure wins by default.
- **Decisions are hard to audit.** It is often unclear which data and which options were considered when a project
  was approved.

**How big the problem is**

| Figure | Value | Label |
|---|---|---|
| Our corridor, Lingampally to Lakdikapul (22.5 km) | **58.2 min** on an average July 2026 day (06:00-23:00), about 23 km/h | measured (`data/raw/corridor_legs_tomtom.csv`) |
| Same trip, weekday vs Sunday (1-15 July, 08:00-20:00) | about 62 min on a weekday vs about 48 min on a Sunday | measured (`data/rain/README.md`) |
| Slowest stretch | Nallagandla jn to ISB Rd / DLF jn, 13.8 min for 5.4 km | measured |
| Vehicles on the main road at corridor junctions | About 3,600 to 5,000 vehicles per hour on the busiest main-road approach at Tolichowki, Nanal Nagar, Rethibowli and NMDC (median, Fri 9 Oct 17:30-18:35) | estimated by TomTom (Junction Analytics live feed, `data/raw/tomtom_corridor_junction_live.csv`) |
| Cost of congestion in India's large cities | A 2018 Boston Consulting Group study (for Uber) put it at about US$22 billion a year for Delhi, Mumbai, Bengaluru and Kolkata together | sourced (to verify) |
| Indian cities in the TomTom Traffic Index | Several Indian cities (for example Bengaluru, Pune, Kolkata) rank among the slowest city centres in the world | sourced (to verify the year and ranks before quoting) |
| Cities in the national Smart Cities Mission | 100 cities, mission launched in 2015 | sourced |
| Cost of one urban flyover in Hyderabad | Typically tens to hundreds of crores of rupees, depending on length | assumption (verify with recent GHMC tenders before quoting a number) |

The point does not depend on the big national number. It is enough that **one** avoided wrong design, or one cheap fix
chosen instead of a structure, is worth many years of the subscription.

---

## 2. Use case and buyer

**The core use case.** A traffic engineer has a jam at a junction or along a corridor. They want to know:
*where does it really start, what is the cheapest fix that works, and if we must build, which design, and what
happens to the next junction?* They test options on the simulated copy, a reviewer re-tests them at more and less
traffic, and the decision-maker approves with a reason. The record is sealed.

| Buyer | Their pain | What they would use CityRehearsal for | Who pays, how | Sales cycle |
|---|---|---|---|---|
| **City traffic police** (for example Hyderabad and Cyberabad traffic police; our corridor crosses more than one jurisdiction, to verify) | Daily jams, pressure to act fast, small budgets | Try signal timing, one-way and turn changes before trying them on the street; show the effect to the public | Operating budget; small annual contract | Medium (months) |
| **Municipal engineering** (GHMC in Hyderabad; other city corporations) | Builds flyovers and junction redesigns; must justify spend | Compare structure designs and cheap fixes on one corridor; catch lane drops and ripple before tender | Project budget (part of the study / DPR phase) or annual licence | Long (6-12 months) |
| **Metropolitan development authority** (HMDA) | Plans new roads and growth areas | Test future traffic (120%, 150%) on planned roads | Planning budget | Long |
| **Metro rail and smart-city SPVs** | Stations and feeder roads change traffic around them | Test access roads, bus bays and diversions during construction | Project budget | Medium to long |
| **Engineering and traffic consultancies** | Write the traffic studies and detailed project reports cities commission | Do studies faster and with a stronger evidence trail; win more bids | Per-study or per-seat; private budget | **Short (weeks)** |

**First buyer to go after:** consultancies and traffic police. Consultancies buy fastest and need the tool in every
study. Traffic police own the cheapest fixes (signal timing), which is exactly where the product shines first.
Municipal engineering and HMDA are the large contracts, after we have references.

---

## 3. Go-to-market: the first 100 users

A "user" is a named person who runs, reviews or approves cases.

| Step | When | Who | Users | How we get them |
|---|---|---|---|---|
| 1. Design partner in Hyderabad | Months 1-3 | One traffic police unit or GHMC engineering team, on this corridor | 10 | Free pilot on Lingampally to Lakdikapul, which is already built. We bring the data; they bring local counts and one real decision to test. |
| 2. Academic partners | Months 2-6 | 2-3 transport engineering departments (for example an IIT or NIT) | 20 | Free academic licence. They validate the model on their own count data and publish; that builds trust with cities. |
| 3. Consultancies | Months 3-9 | 5 traffic or engineering consultancies | 25 | Paid per study. Reach through the design partner's references, industry events (for example the annual Urban Mobility India conference, to verify), and published backtests. |
| 4. Second and third city | Months 6-12 | Traffic police or SPV in 2 more cities | 30 | Referral from consultancies who already use it there; listing on the Government e-Marketplace (GeM) for direct purchase. |
| 5. Inside each buyer | Ongoing | Reviewers and approvers | 15 | Every case needs a reviewer and a decision-maker, so each engineer brings 1-2 more users. |
| **Total** | **12 months** | | **100** | |

**What we publish to earn trust:** the YMCA Circle calibration (model within about 3 km/h of TomTom speeds), the
Gariahat backtest, and the corridor run against TomTom trip times. Every number labelled real or simulated.

---

## 4. Unit economics (simple model)

All prices and costs below are **assumptions** for discussion. We have no quotes yet.

**What we sell**

| Product | What is included | Price (assumption) |
|---|---|---|
| **Junction study** | One junction: data, calibration, up to 10 options tested, decision brief | Rs 3-5 lakh, one-off |
| **Corridor subscription** | One corridor (about 10 junctions): calibrated model, live junction data, unlimited what-ifs, review and approval flow, re-calibration every quarter | Rs 15-25 lakh per year |
| **City licence** | Up to 10 corridors, training, priority support | Rs 1-1.5 crore per year |

**What one corridor costs us per year** (assumption)

| Cost | Per corridor per year | Note |
|---|---|---|
| TomTom data (Traffic Stats + Junction Analytics for ~5 junctions) | Rs 4-8 lakh | **Biggest unknown.** We used trial accounts. Needs a commercial quote. |
| Cloud compute for simulations | Rs 0.5-1 lakh | SUMO is free and open source; one corridor run takes 1-2 minutes on a laptop |
| AI assistant (Claude API) | under Rs 0.5 lakh | A case is a few dozen tool calls; usage-based |
| Calibration and support (people) | Rs 3-5 lakh | 2-3 engineer-weeks to set up the first time, 2-3 days per quarter after |
| **Total cost** | **Rs 8-15 lakh** | |

**Margin per corridor** at Rs 20 lakh: about Rs 5-12 lakh, or 25-60% gross margin. The model only works if
**data cost per corridor falls** (volume pricing with TomTom or a second data supplier, or the city's own counts and
cameras) and **calibration becomes mostly automatic** (days, not weeks). Both are on the 12-month plan.

**Value to the buyer** (how we will justify the price): if one test steers a city away from one wrong design, or
lets a signal retime replace a structure, the saving is a large multiple of the yearly fee. We will make this case
with real project numbers from the design partner, not with national averages.

---

## 5. Business model canvas

| Block | CityRehearsal |
|---|---|
| **Customer segments** | City traffic police; municipal engineering (GHMC and others); metropolitan authorities (HMDA); metro and smart-city SPVs; traffic and engineering consultancies |
| **Value proposition** | Test before you build: see where jams start, try cheap fixes first, test structures only when needed, catch ripple to the next junction, and keep a sealed, auditable record of every decision |
| **Channels** | Design-partner pilot; consultancies as resellers and power users; Government e-Marketplace (GeM); published backtests; urban mobility events |
| **Customer relationships** | Hands-on onboarding (we calibrate the first corridor with them); quarterly re-calibration; shared review workflow |
| **Revenue streams** | Junction studies (one-off); corridor subscriptions (yearly); city licences (yearly) |
| **Key resources** | Calibrated corridor models; templates for each fix; the review and evidence workflow; data contracts |
| **Key activities** | Data collection and calibration; building fix templates; validating against real outcomes (backtests); customer onboarding |
| **Key partners** | TomTom (traffic data); OpenStreetMap and Overture (maps, buildings); SUMO / Eclipse (simulator); Anthropic (AI assistant); universities (validation) |
| **Cost structure** | Traffic data licences (largest); calibration engineers; cloud compute; AI usage |

---

## 6. 12-month plan and what would have to be true

| Quarter | Goal | Done when |
|---|---|---|
| **Q1** (Oct-Dec 2026) | Turn the hackathon build into a pilot-ready product on one corridor | Corridor calibrated for morning and evening peaks; review flow used end to end by a real engineer; design partner signed |
| **Q2** (Jan-Mar 2027) | First real decision tested | Design partner tests a real proposal; we compare our prediction with what happens on the street after a cheap fix goes in; first paid consultancy study |
| **Q3** (Apr-Jun 2027) | Repeatable setup | New corridor set up in under 2 weeks; 3 consultancies paying; second city started |
| **Q4** (Jul-Sep 2027) | 100 users | 100 users, 5 paying organisations, first city licence in negotiation |

**What would have to be true** (and how we will check each)

| It must be true that... | How we check it, early |
|---|---|
| The model predicts real changes, not just today's traffic | Predict the effect of a real signal change before it happens; measure after with TomTom. This is the single most important test. |
| Data can be bought at a price that leaves a margin | Get a commercial TomTom quote in month 1; price a second supplier; ask partners for their own counts and camera data |
| Engineers trust a simulated answer enough to act on it | Design partner uses it in a real meeting; track whether the review step changes any decisions |
| A buyer has a budget line for this | Ask in the pilot: which budget, which approval, which procurement route (GeM, tender, consultancy sub-contract) |
| Setting up a new corridor gets fast | Measure set-up time per corridor; target 2 weeks by Q3 |
| The AI assistant helps rather than confuses | Count how often engineers accept, change or reject its proposals; it only uses fix templates and never decides |

---

## 7. Risks and mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Data cost** | TomTom licences may cost more than a corridor earns | Commercial quote early; buy only the junctions that matter; use the city's own counts and signal data; a second data supplier; share data costs across corridors in a city licence |
| **Data access limits** | Our trial only allowed July 2026 for route data, and one junction per trial account | Commercial licence; partner data; keep labelling which inputs are measured, estimated or assumed |
| **Calibration trust** | If the model is wrong, the advice is wrong | Every result shows real vs simulated side by side; publish backtests (Gariahat) and calibration errors (YMCA within about 3 km/h); reviewer must re-test at other traffic levels; re-calibrate every quarter |
| **Indian mixed traffic is hard to simulate** | Two-wheelers, autos and lane-free driving differ from Western defaults | Sublane model for two-wheelers; close-following settings tuned to Hyderabad data; validate per city |
| **Liability** | A city may blame the tool if a project fails | The product recommends, never decides; humans review and approve with a reason; every assumption labelled; contracts state it is decision support; the sealed record shows what was known at the time |
| **AI mistakes** | An AI could invent a number or a road change | The assistant can only build options from fixed templates and only report numbers that come from simulation runs; runs are append-only; the brief lists assumptions; a human reviews |
| **Slow government sales** | Public procurement can take a year | Start with consultancies (fast, private budgets) and police (small, operational budgets); GeM listing; free pilots that lead to paid studies |
| **Rain and special events** | Monsoon and events change traffic | Rain setting from data (about +5% while raining, low confidence); scenario runs at 80% and 120% traffic |
| **Privacy** | Traffic data could be personal | We use only aggregated, anonymous data (TomTom aggregates, counts); no personal data stored |

---

## Sources

- Maitra, Azmi, Kumar, Sarkar, "Modeling traffic impact of flyover at an urban intersection under mixed traffic
  environment", *European Transport / Trasporti Europei* 27 (2004). Copy and tables in `data/gariahat/`.
- Sohail, Faheem, Aquil, "Performance analysis of a roundabout using SIDRA Intersection software", IJRAR 7(2), 2020
  (YMCA Circle counts). Copy in `data/raw/`.
- TomTom Traffic Stats and Junction Analytics exports in `data/raw/` and `data/tomtom/` (trial licence).
- Open-Meteo historical weather archive (rain), see `data/rain/README.md`.
- To verify before quoting: BCG (2018) congestion cost study for Uber; TomTom Traffic Index city ranks; Biodiversity
  flyover closure (Hyderabad, 2019); recent GHMC flyover tender values; Urban Mobility India conference.
