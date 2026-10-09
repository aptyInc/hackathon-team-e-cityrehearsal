# Rain and the Lingampally → Lakdikapul trip

**Question:** does rain make the 22.5 km trip from Lingampally to Lakdikapul slower, by how much, and on which stretches?
We want a "Rainy day" option in the demo that is backed by real numbers.

## Hour by hour, all of July 2026 (current answer)

**Short answer:** in an hour when it rained, the trip was **about 3 % slower** than the same hour on a dry day of the
same weekday: **+1.6 min on a 57-minute trip** (95 % range 0 % to +5 %). When it had **already been raining for an
hour**, the slowdown was larger: **+4 %** for light rain (95 % range +0.5 % to +7 %, about +2.3 min) and **+8 %** for the
wettest hours July had (1 mm/h or more; 95 % range −4 % to +16 %, about +4.5 min). That is real but small, and the data
cannot pin the size down. One check pulls the other way: **within the same day, rainy hours were no slower than dry
hours** (+0.1 %, range −1.6 % to +1.6 %). So at least part of what we see is "rainy days are slower days", not
"the rainy hour itself is slower". **Confidence: low to moderate.**

What we can say in the demo: *"In July 2026, hours with rain were about 3 % slower on this corridor, and about 4–8 %
slower once it had been raining for an hour (TomTom hourly data × Open-Meteo rain, 31 days; not statistically certain).
The slowdown is spread over the whole route. July had no real downpours in the weather data, so we cannot say what a
cloudburst or waterlogging does."*

### What we did (plain language)

1. **Traffic (measured).** TomTom Traffic Stats gave the average trip time and 12 stretch times for **every hour of
   every day, 1–31 July 2026** (jobs 10053357 and 10053399 in `data/raw/corridor_legs_tomtom.csv`). We used 06:00–24:00:
   31 days × 18 hours = **558 hour slots**.
2. **Weather (measured, but modelled).** Open-Meteo's archive gave hourly rain, temperature, humidity, wind, cloud cover
   and weather code at three points (Lingampally, Khajaguda/Gachibowli, Lakdikapul); we use the mean of the three.
   Open-Meteo stamps an hour by its end, so TomTom's 08:00–09:00 slot gets the rain that fell from 08:00 to 09:00
   (`data/raw/weather_july_hourly.csv`, label `measured (Open-Meteo reanalysis)`).
3. **Rain classes per hour:** dry (< 0.1 mm), light (0.1–1 mm), moderate (1–5 mm), heavy (> 5 mm).
   July had **323 dry, 201 light, 34 moderate and 0 heavy** slots. The wettest hour was 4.5 mm (26 July, 23:00).
4. **Compare like with like.** A model of trip time with an effect for each hour of the day (rush hours), each day of
   the week (Sundays are much faster), the rain class in that hour and the rain in the previous hour. Effects are in
   percent (we model the logarithm of trip time).
5. **How sure are we?** Three ways, because one hour's traffic is not independent of the next:
   - standard errors that treat each day as one block;
   - a **bootstrap**: re-draw the 31 days at random 2000 times and refit (the 95 % ranges quoted here);
   - a **permutation test**: give each day another day's whole rain pattern 2000 times; how often is the effect as
     large by chance? (the p-values quoted here).
6. **Stretches.** The same model on each of the 12 stretches. Twelve noisy estimates scatter by chance, so for the
   simulation each stretch's estimate is pulled towards the corridor-wide one in proportion to how noisy it is
   ("empirical Bayes"; a stretch with a precise, different estimate keeps more of its own).

Script: `data/weather/analyse_weather_hourly.py`. Re-run with `.venv/bin/python -I data/weather/analyse_weather_hourly.py`
(downloads with `curl`; `--offline` reuses `data/weather/_cache/`). It creates no TomTom jobs. Every number below is in
`data/weather/results.json`.

### The numbers

Trip-level effects (95 % range from the bootstrap; p from the permutation test; minutes on the 56.9-minute mean trip):

| What | Effect on trip time | 95 % range | p | Minutes |
|---|---|---|---|---|
| **Any rain in the hour** (≥ 0.1 mm) | **+2.7 %** | +0.1 % to +5.0 % | 0.08 | +1.6 |
| Light rain in the hour (0.1–1 mm, 201 slots) | +2.8 % | 0.0 % to +5.2 % | 0.08 | +1.6 |
| Moderate rain in the hour (1–5 mm, 34 slots) | +1.8 % | −4.6 % to +6.6 % | 0.43 | +1.0 |
| Rain in the **previous** hour, per mm | **+3.5 %** | −0.5 % to +6.8 % | **0.02** | |
| **Light rain for an hour or more** (0.34 mm/h now and before) | **+4.0 %** | **+0.5 % to +6.9 %** | | **+2.3** |
| **Moderate rain for an hour or more** (1.7 mm/h now and before) | **+7.9 %** | −3.9 % to +16.1 % | | **+4.5** |
| Rain per mm in the hour (straight line instead of classes) | +2.0 % | −1.5 % to +4.2 % | 0.11 | |
| Check: rainy vs dry hours **of the same day** (light / moderate) | +0.1 % / −2.0 % | −1.6 to +1.6 / −6.8 to +3.7 | 0.95 / 0.25 | |

Reading it: rain slows the trip a little, and the slowdown builds up when rain continues (the previous hour's rain
counts more than the current hour's). The heaviest July hours (34 slots) are too few to measure precisely. The
same-day check shows no difference between rainy and dry hours of one day: rainy days were slower **all day**, which
could be rain after-effects (wet roads, waterlogged lanes, people setting off later) or something else that happened to
come with the rainy days. One month of data cannot separate the two.

### Stretches

Per stretch, while light rain or moderate rain has been falling for an hour (raw estimate with its 95 % range, then the
value the simulation uses after pulling noisy estimates towards the corridor-wide one).

| Stretch | Mean min | Light rain, raw | Moderate rain, raw | Simulation (light / moderate) |
|---|---|---|---|---|
| Lingampally → Nallagandla jn (A-j01) | 6.7 | +7.0 % (0 to +13) | +13 % (−4 to +24) | +4.1 % / +6.9 % |
| **Nallagandla jn → ISB Rd (j01-j02)** | 13.5 | **+6.3 % (+1 to +11)** | +14 % (−7 to +34) | +4.3 % / +9.5 % |
| ISB Rd → Gachibowli Circle (j02-j03) | 3.8 | +1.7 % (−2 to +5) | +9 % (−8 to +22) | +3.6 % / +8.7 % |
| **Gachibowli Circle → Biodiversity jn (j03-j04)** | 3.0 | **+6.7 % (+1 to +10)** | +10 % (−5 to +23) | +4.2 % / +5.8 % |
| Biodiversity jn → Khajaguda (j04-j05) | 2.4 | +0.8 % (−3 to +4) | +4 % (−8 to +17) | +3.7 % / +10.0 % |
| **Khajaguda → Shaikpet (j05-j06)** | 2.8 | **+4.3 % (+1 to +6)** | +9 % (−1 to +17) | +4.3 % / +11.0 % |
| Shaikpet → Tolichowki (j06-j07) | 4.6 | +1.6 % (0 to +4) | +2.5 % (−3 to +8) | +3.0 % / +5.3 % |
| Tolichowki → Nanal Nagar (j07-j08) | 4.0 | −0.7 % (−6 to +4) | −10 % (−19 to −1) | +3.7 % / +1.7 % |
| Nanal Nagar → Rethibowli (j08-j09) | 1.2 | −0.2 % (−7 to +9) | +1 % (−18 to +22) | +3.8 % / +5.6 % |
| Rethibowli → NMDC (j09-j10) | 7.4 | +2.4 % (−2 to +6) | +8 % (−4 to +19) | +3.8 % / +8.0 % |
| NMDC → Masab Tank (j10-j11) | 2.5 | +0.5 % (−2 to +3) | +1 % (−5 to +7) | +3.2 % / +5.4 % |
| Masab Tank → Lakdikapul (j11-B) | 5.2 | +3.6 % (−1 to +7) | +5 % (−3 to +12) | +4.0 % / +8.5 % |

- The western half (Lingampally → Shaikpet) carries most of the rain signal. Three stretches are slower in light rain
  with ranges above zero: **Nallagandla → ISB Rd, Gachibowli Circle → Biodiversity jn** (the same stretch the first
  look flagged) and **Khajaguda → Shaikpet**.
- **Tolichowki → Nanal Nagar** came out *faster* in the wettest hours. With 24 stretch-and-class tests, one or two such
  results are expected by chance; we do not believe rain speeds traffic up, and the simulation never makes a stretch
  faster in rain (assumed).
- The spread between stretches beyond noise is small for light rain (about 0.7 %), so the simulation treats light rain
  as nearly uniform (3–4 % per stretch). For moderate rain the stretches differ more (about 3.5 %).

### What the simulation uses (`data/rain/rain_factors.json`, label **estimated**)

`POST /corridor/runs` takes `"weather": "dry" | "light_rain" | "heavy_rain"` (leave it out for the calibrated run).
Only the speed caps change; demand and signals do not (no evidence either way on demand: **assumed** unchanged).

| Setting | Means | Expected trip effect vs dry (95 % range) |
|---|---|---|
| `dry` | no rain this hour or the hour before | 0 % |
| `light_rain` | 0.1–1 mm/h (typically 0.34) this hour and the hour before | +4.0 % (+0.5 to +6.9) |
| `heavy_rain` | the wettest July hours: 1+ mm/h (typically 1.7) this hour and the hour before | +7.9 % (−3.9 to +16.1) |

- **"Heavy" is July's heaviest, not a cloudburst.** No hour in July 2026 reached 5 mm/h in the weather data, so
  `heavy_rain` is the 1–5 mm/h class. A rain gauge would usually record more in the same downpour.
- **Relative to what the simulation was calibrated to.** The simulation is calibrated to TomTom averages that already
  include rainy hours (in a typical July hour it rained on about 40 % of days). So `dry` raises the calibrated speed caps by about
  2 %, and `heavy_rain` lowers them by about 6 % (0–8 % by stretch). For a single day and hour (`day` + `hour`), the factor is relative to
  that hour's own rain.
- **Flyover/underpass decks** in a what-if get the same factor as the road under them (the template sets their speed
  itself), so a structure does not look better in rain just because its deck stays dry.
- The pessimistic end (`stress_test`): +16 % travel time for sustained moderate rain.

#### What the simulation does with it (real SUMO runs, 9 Oct 2026)

Trip Lingampally → Lakdikapul, simulated minutes ± noise (the probe cars' standard error; a difference between two runs
is beyond noise when it exceeds about 1 minute). Flyover at Nanal Nagar (j08): 2 lanes each way, 1,200 m.

| Run | Typical July day (06–23) | Typical July 18:00–19:00 |
|---|---|---|
| As calibrated (no `weather`) | 55.4 ± 0.3 | 62.3 ± 0.4 |
| `dry` | 54.6 ± 0.3 (−0.8) | 62.7 ± 0.4 (+0.4, within noise) |
| `light_rain` | 57.2 ± 0.4 (+1.8) | |
| **`heavy_rain`** | **58.9 ± 0.3 (+3.5)** | **66.0 ± 0.4 (+3.7)** |
| Flyover j08, as calibrated | 53.4 ± 0.3 (−2.1) | |
| **`heavy_rain` + flyover j08** | **56.5 ± 0.3** (−2.4 vs `heavy_rain`) | **63.8 ± 0.4** (−2.2 vs `heavy_rain`) |

- Heavy rain against dry, all-day: 58.9 / 54.6 = **+7.9 %**, the same as the measured estimate (+7.9 %). Light rain:
  +4.8 % (measured +4.0 %).
- At 18:00 the dry run is not faster than the calibrated one: at rush hour the trip is set by the queues at the
  signals more than by road speeds, so slightly higher speeds do not help. Heavy rain still adds 3.7 minutes.
- The flyover saves about the same in rain as in dry weather (2.2–2.4 min vs 2.1 min): rain does not change the case
  for or against it.

### Caveats

- **The rain data is a weather model, not a rain gauge.** Open-Meteo's archive is ERA5-based reanalysis on a grid of
  about 9 km. It gets "did it rain around here that hour" roughly right, but spreads showers out: it reports light
  rain far too often (42 % of July hours had ≥ 0.1 mm) and almost never a downpour. Some "light rain" hours are only
  overcast drizzle, which dilutes the light-rain effect; and short heavy showers are smeared into moderate hours.
  A rain gauge (IMD, or the Telangana State Development Planning Society AWS network) would sharpen this.
- **One month, one monsoon.** 31 days, 34 moderate hours, no heavy hours. The 95 % ranges are wide for anything but
  light rain.
- **Rainy days vs rainy hours.** Within a day, rainy and dry hours did not differ. The effect we report could partly be
  something else that came with the rainy days.
- **TomTom hourly times are averages over the hour's probe vehicles**, not trips that started in that hour; a slowdown
  late in an hour shows up partly in the next hour (one reason the previous hour matters).
- **Many tests.** 12 stretches × 2 classes: a few "significant" stretch results are expected by chance. The simulation
  uses the noise-pulled values.
- **The simulation applies the factors to speed caps.** A stretch's time in the simulation is partly waiting at
  signals, which a speed cap does not change, so the simulated slowdown can be smaller than the measured one.

### Files

| File | What | Label |
|---|---|---|
| `data/raw/weather_july_hourly.csv` | Every July hour slot: rain, precipitation, temperature, humidity, wind, weather code and cloud cover at the 3 points and their mean, rain class, plain-text weather | measured (Open-Meteo reanalysis) |
| `data/weather/results.json` | Every model, the per-stretch table, uncertainty, share of days with rain per hour | estimated |
| `data/rain/rain_factors.json` | Factors per rain class and stretch, the simulation's what-if settings, the first look's numbers under `first_look` | estimated |
| `data/weather/analyse_weather_hourly.py` | Re-creates all of the above | |
| API | `GET /weather?day=july\|2026-07-DD&hour=H`, `GET /weather/now`, `GET /weather/factors` (backend/app/weather.py) | |

---

## First look: daily totals, 1–15 July 2026 (superseded)

*Kept for the record. This used one 08:00–20:00 average per day for 15 days; the hourly analysis above replaces it.
Its factors are kept in `rain_factors.json` under `first_look`.*

**Short answer (first look):** in the first half of July 2026 the light-to-moderate monsoon showers did **not measurably slow the trip**.
On rainy weekdays the trip took **61.0 min** against **62.0 min** on dry weekdays (**−1.6 %**). Our best estimate is that
traffic runs about **5 % slower while it is actually raining**, but the data cannot rule out anything from 11 % faster to
21 % slower. One stretch, **Gachibowli Circle → Biodiversity junction**, was slower on the rainy day in every one of 7
same-weekday comparisons. That is the only stretch-level signal we found.

![Trip time vs rain, 1–15 July 2026](rain_vs_trip.png)

### What we did (plain language)

1. **Traffic (measured).** TomTom gave us the average trip time for each day from 1 to 15 July 2026, 08:00–20:00, split
   into 12 stretches between junctions (`data/raw/corridor_legs_tomtom.csv`). These are real GPS-probe travel times.
2. **Rain (measured, but modelled).** We downloaded hourly rainfall for July 2026 from the free Open-Meteo archive at
   three points along the route: Lingampally, Gachibowli and Lakdikapul. We averaged the three, because a shower that
   only hits one end of the route still affects part of the trip. The three points fall in three different ~9 km grid
   cells (centres 17.47,78.27 / 17.40,78.37 / 17.40,78.46). Daily totals at the three points were close to each other.
3. **Compare like with like.** Sundays are about 14 minutes faster than weekdays and Saturdays about 3 minutes faster,
   so comparing a rainy Sunday with a dry Tuesday would be unfair. We used three checks:
   - **Weekdays only:** rainy (≥ 2 mm between 08:00 and 20:00) against dry (< 0.5 mm).
   - **Same weekday, one week apart:** 1–7 July was a rainy week and 8–14 July was a dry week, so we compared each day
     with the same weekday in the next week (Wed with Wed, Thu with Thu, and so on).
   - **A regression on all 15 days:** trip minutes against rain, with Saturday and Sunday taken into account.

Script: `data/rain/analyse_rain.py`. Re-run it with `.venv/bin/python -I data/rain/analyse_rain.py`; it downloads with
`curl` and creates no TomTom jobs.

### The numbers

Rain for each day is the 08:00–20:00 total, averaged over the three points.

| Day | Rain (mm) | Wet hours | Trip (min) | | Day | Rain (mm) | Wet hours | Trip (min) |
|---|---|---|---|---|---|---|---|---|
| Wed 1 | 1.6 | 1 | 62.0 | | Wed 8 | 0.3 | 0 | 65.1 |
| Thu 2 | 3.4 | 2 | 63.4 | | Thu 9 | 0.4 | 0 | 63.7 |
| Fri 3 | 4.3 | 2 | 58.6 | | Fri 10 | 0.0 | 0 | 58.2 |
| Sat 4 | 7.3 | 7 | 61.2 | | Sat 11 | 0.3 | 0 | 58.6 |
| Sun 5 | 1.9 | 2 | 48.6 | | Sun 12 | 0.0 | 0 | 47.5 |
| Mon 6 | 1.3 | 1 | 63.8 | | Mon 13 | 0.3 | 0 | 62.1 |
| Tue 7 | 1.8 | 0 | 62.7 | | Tue 14 | 0.0 | 0 | 60.9 |
| | | | | | Wed 15 | 1.4 | 1 | 64.4 |

A "wet hour" is an hour with at least 0.5 mm of rain.

| Check | Result | Is it bigger than normal day-to-day noise? |
|---|---|---|
| Rainy weekdays (n = 2) vs dry weekdays (n = 5) | 61.0 vs 62.0 min, **−1.0 min (−1.6 %)** | No. Dry weekdays alone ranged from 58.2 to 65.1 min (sd 2.6). Permutation p = 0.72 |
| Any-rain weekdays (n = 6) vs dry weekdays (n = 5) | 62.5 vs 62.0 min, +0.5 min (+0.8 %) | No (p = 0.73) |
| Same weekday, rainy week vs dry week (7 pairs) | **+0.6 min (+1.1 %)**, 5 of 7 slower | No (exact sign-flip p = 0.34) |
| Rainiest day, Sat 4 July (7.3 mm, 7 wet hours) vs Sat 11 | +2.6 min (+4.4 %) | A single pair, so we cannot tell |
| Regression, all 15 days | +0.10 min per mm (95 % range −0.61 to +0.82); +0.26 min per wet hour (−0.58 to +1.09) | No. Saturday −3 min and Sunday −14 min are clear |
| **While it is raining** (from the wet-hour regression) | **+5 % travel time** (95 % range −11 % to +21 %) | No |

How we got the "while raining" figure: TomTom's number is an average over 12 hours (08:00–20:00). If rain slows
traffic by X % during one hour, the 12-hour average rises by only about X/12 %. So +0.26 min per wet hour on a
62-minute trip works out to about +5 % during that hour. This assumes trips are spread evenly over the day.

#### Stretches

These are weekday minutes. "Rainy week vs dry week" is the average change across the 7 same-weekday pairs.

| Stretch | Dry weekdays | Rainy weekdays | Rainy week vs dry week | Verdict |
|---|---|---|---|---|
| **Gachibowli Circle → Biodiversity jn (j03-j04)** | 2.9 | 4.4 | **+20 % mean, +8 % median, 7 of 7 slower (p = 0.016)** | **Only consistent signal** |
| Masab Tank → Lakdikapul (j11-B) | 5.4 | 5.1 | +6 %, 4 of 7 slower | Mixed. Sat 4 July was +32 % |
| Lingampally → Nallagandla jn (A-j01) | 8.4 | 8.8 | +8 %, 6 of 7 slower | Not real: the next stretch moves the opposite way (see below) |
| Nallagandla jn → ISB Rd (j01-j02) | 14.4 | 13.1 | −4 % | Lingampally → ISB Rd as a whole: +0.3 % |
| All other stretches | | | −5 % to +2 % | No effect |

The Lingampally stretch looks rain-sensitive on its own, but the next stretch (Nallagandla → ISB Rd) gets faster by about
the same amount. Where the time is split between the two depends on where the Nallagandla junction sits on TomTom's
road segments. Taken together, the two stretches show no change.

Gachibowli Circle → Biodiversity junction is a 1.6 km stretch that includes the flyover approach. It was slower in all
7 rainy-week pairs, including +70 % on Thu 2 July. With 12 stretches tested, one hit like this could still be chance,
so treat it as "worth watching", not proven.

### Recommended rain setting for the simulation

`data/rain/rain_factors.json` (label: **estimated**):

| Setting | Value | Meaning |
|---|---|---|
| `overall_speed_factor` | **0.95** | Multiply road speeds by 0.95 while it rains, so trips take about 5 % longer. This is our best estimate |
| `per_leg["j03-j04"]` | **0.83** | Gachibowli Circle → Biodiversity jn runs about 20 % slower. Every other stretch uses 0.95 |
| `stress_test.overall_speed_factor` | **0.83** | A pessimistic "heavy rain" what-if (+21 %, the top of the 95 % range). Do not use it as the expected case |
| `demand_factor` | **1.0** | We have no evidence that rain changes how many vehicles travel, so we keep demand unchanged (assumed) |

**Confidence: low.** The "Rainy day" option in the demo should say something like *"Based on 15 days of TomTom data for
July 2026, light monsoon showers added about 5 % to this trip (not statistically certain). The Gachibowli → Biodiversity
stretch was the most rain-sensitive."* We should not claim that rain causes big delays on this corridor. The data we have
does not show that.

### Caveats

- **Small sample.** There are 15 days, and only 2 weekdays had ≥ 2 mm of rain. Normal day-to-day variation (±2.6 min) is
  bigger than any rain effect we could see.
- **Daily averages vs hourly rain.** TomTom gives one average for 08:00–20:00, while rain usually falls for one or two
  hours. A strong but short slowdown gets diluted in a 12-hour average. The "+5 % while raining" figure is derived, not
  measured hour by hour.
- **Light rain only.** The rainiest day in our window had 7.3 mm in 12 hours. The really wet days in July (17th: 13 mm,
  29th: 10 mm, 30th: 13 mm in 08:00–20:00) are outside the period TomTom covered day by day, so we cannot say anything
  about heavy rain or waterlogging.
- **The rain data is a weather model, not a rain gauge.** Open-Meteo's archive is ERA5-based reanalysis on a grid of
  about 9 km. It gets total rainfall roughly right but often misplaces the timing and location of short convective
  showers. Data from a rain gauge (IMD, or the Telangana State Development Planning Society AWS network) would be
  better.
- **Week-to-week effects.** The same-weekday comparison assumes nothing else changed between the first and second week
  of July, such as events or roadworks.
- **TomTom average vs median.** We used the average trip time. The median trip time gives the same picture
  (rainy weekdays 48.5 vs dry 49.2 min).

### How to firm this up (done since: the hourly TomTom jobs 10053357/10053399 cover every hour of July)

One Traffic Stats job on the same route, with date ranges for 17, 21–22, 29 and 30 July (wet) and 10, 13–14, 24 July
(dry), and one-hour time sets from 08:00 to 20:00. That would let us compare rainy hours with dry hours directly, and
include the heavy-rain days.

### Files

| File | What | Label |
|---|---|---|
| `data/raw/rain_july_hyderabad.csv` | Hourly precipitation and rain at the 3 points plus their mean, 1–31 July 2026 (IST) | measured (ERA5-based reanalysis) |
| `data/raw/corridor_rain_vs_trip.csv` | One row per day, 1–15 July: weekday, rain 08:00–20:00 (mean and per point), wet hours, 24 h rain, trip minutes (average and median), minutes per stretch | trip measured; rain measured (modelled) |
| `data/rain/rain_factors.json` | Recommended simulation setting | estimated |
| `data/rain/rain_vs_trip.png` | The chart above | |
| `data/rain/analyse_rain.py` | Re-creates all of the above | |
