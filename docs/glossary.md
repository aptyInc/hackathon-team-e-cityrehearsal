# Glossary (plain language)

Words we use in the demo, the deck and the code, explained for someone who is not a traffic engineer.

## Roads and places

| Word | What it means here |
|---|---|
| **Corridor** | One long route that many people drive every day. Ours is **Lingampally to Lakdikapul** in Hyderabad: about 22.5 km, about an hour by car. We study the whole route, not one crossing at a time, because a fix at one junction can move the jam to the next one. |
| **Junction** | A place where roads meet: a crossroads, a T-junction or a circle (roundabout). Our corridor has 11 junctions, named `j01` to `j11` (for example `j07` = Tolichowki). |
| **Leg** | The stretch of road between two junctions next to each other, for example "Tolichowki to Nanal Nagar". The trip is the sum of 12 legs. |
| **Approach** | One road coming into a junction. A crossroads has four approaches. TomTom reports delay and queue per approach. |
| **Trip strip** | The coloured bar at the bottom of the corridor screen. Each block is one leg; its width is the time it takes. One bar is measured (TomTom), the other is simulated, so you can compare them. |
| **Ripple** | When fixing one junction makes another one worse. Example: a flyover lets traffic arrive faster at the next junction, which then jams. |

## Fixes (interventions)

| Word | What it means here |
|---|---|
| **Intervention** | A change we try in the simulation: a flyover, an underpass, a new signal timing, a wider road or a one-way side road. |
| **Flyover** | A raised road (a bridge) that carries through traffic over a junction. Turning traffic stays on the ground. Costly and slow to build. |
| **Underpass** | The same idea, but the through road goes under the junction in a cut or tunnel. Also costly; the choice between the two depends on space, drainage and utilities, not only on traffic. |
| **Signal retime** | Changing how long each direction gets a green light. Almost free and can be done in a day. That is why we always try it first. |
| **Signal cycle** | One full round of the traffic light, until it comes back to the same direction. A 120-second cycle means every direction gets its turn once every 2 minutes. |
| **Green share** | The part of the cycle's green time given to the main road. "70% main road" means the corridor gets 70% of the green time and the side roads share the other 30%. |
| **Widening** | Adding a lane on the main road near a junction. |
| **One-way side road** | Making one side road one-way so the signal has fewer movements to serve. |
| **Lane drop** | A place where, for example, three lanes squeeze into two. Cars must merge and a queue forms. Our design check warns about this at flyover ends. |

## Data

| Word | What it means here |
|---|---|
| **TomTom** | A company that makes maps and collects traffic data from millions of phones, cars and navigation devices. We use two of its products (below). |
| **Probe car** | Any vehicle that sends its anonymous GPS position to a company like TomTom. TomTom only sees a sample of all traffic, not every vehicle. Speeds from probes are reliable; vehicle counts from probes are TomTom's **estimate**. |
| **TomTom Traffic Stats** | Historic travel times and speeds on a route we choose, averaged over many days. We used it for July 2026: the corridor took **58.2 minutes** on an average July day (06:00 to 23:00). This tells us **how long the trip takes**. |
| **TomTom Junction Analytics** | Minute-by-minute data for one junction: delay, queue length, vehicles per hour and turning shares, per approach. We have it live for 5 corridor junctions (Gachibowli, Tolichowki, Nanal Nagar, Rethibowli, NMDC) and for YMCA Circle. This tells us **what is happening at a junction right now**. |
| **Turn shares (turn ratios)** | Of the cars arriving on one road, what share goes left, straight or right. A simulation needs these to send cars the right way. |
| **OpenStreetMap (OSM)** | A free world map made by volunteers. Our road network (lanes, speed limits, junction shapes) starts from it. |
| **Overture buildings** | Free building outlines (from Overture Maps). Used only to draw the 3D city. Heights are mostly guessed from the footprint size. |
| **Open-Meteo** | A free weather archive. We used its rainfall for July 2026 to check whether rain slows the trip. Answer: about 5% slower while it rains, but not certain. |
| **REAL vs SIMULATED** | Every number on screen carries one of these tags. REAL = measured by someone (TomTom, a study). SIMULATED = produced by our model. We never mix them without saying so. |
| **counted / estimated / assumed** | How much to trust an input. **Counted**: someone measured it (a traffic count, a study, a probe speed). **Estimated**: worked out from measured data (TomTom's vehicle-per-hour figure, our 2.0x growth factor). **Assumed**: a reasonable guess with no data behind it yet (the car/auto split). Every input in a result carries one of these labels. Note: the data files also use **measured** for TomTom probe speeds and times; read it as "counted". |

## Model

| Word | What it means here |
|---|---|
| **Simulation** | A computer copy of the roads where thousands of virtual vehicles drive, stop at signals and queue. We change the roads in the copy and watch what happens, instead of changing the real roads. |
| **SUMO** | The free, open-source traffic simulator we use (from the German Aerospace Center, DLR). It is used by universities and cities worldwide. |
| **Sublane model** | A SUMO setting that lets two-wheelers squeeze between cars and share a lane, as they do in Indian traffic. |
| **Baseline** | The simulation of today's roads with no changes. Every option is compared against it. |
| **Variant** | A copy of the baseline with one or more interventions built in. |
| **Template** | A ready-made recipe for one kind of intervention (flyover, signal retime and so on). The AI assistant may only build variants through templates; it can never edit the road map freely. |
| **Calibration** | Tuning the simulation until it behaves like the real roads: we adjust traffic volume and driver behaviour until simulated speeds match TomTom's measured speeds. At YMCA Circle the model's speeds are within about 3 km/h of TomTom's. Calibration is what makes the "what if" answers worth trusting. |
| **Volume scale (80% / 120%)** | Running the same option with less or more traffic than today. 1.2 = 20% more traffic, a common test for future growth. The reviewer must do at least one such re-test before recommending an option. |
| **Backtest** | Testing the model on a past case where we already know the answer. Ours is the **Gariahat flyover in Kolkata**: a 2004 study found it eased Gariahat but made the next junction (Phari) worse. Our job is to show the simulator reproduces that. |
| **Mock mode (`MOCK_SIM=1`)** | The app returns saved sample results instead of running the simulator. Used for building the screens and as a demo fallback. Results from mock mode are tagged SAMPLE DATA. |

## Decisions

| Word | What it means here |
|---|---|
| **Case** | One problem being worked on, for example "Tolichowki jams every evening". All runs, options, reviews and the decision for it are kept together. |
| **AI planning assistant** | Claude (an AI model from Anthropic) connected to our tools. It runs the baseline, proposes options cheapest first, runs them, compares them and writes a one-page decision brief. It recommends; it never decides. |
| **Decision brief** | A one-page summary: the problem, the options tried, their results, the warnings, the assumptions and the recommendation. |
| **Reviewer** | A second engineer who checks the proposal and re-runs it at different traffic levels before recommending it. |
| **Commissioner** | The person with authority to approve, reject or defer. They must write a reason. |
| **Fingerprint (SHA-256)** | A 64-character code computed from all the evidence in a case (every option and every run). If anyone later changes even one number, the code no longer matches. It is like a tamper seal on the file. |
| **Append-only** | Runs can be added but never deleted or edited, so the record of what was tried stays complete. |
