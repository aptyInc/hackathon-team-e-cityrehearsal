# Water-logging points on the corridor (rain what-if, junction by junction)

**What this answers:** "When it rains hard, *where* on the Lingampally -> Lakdikapul road will the queues get longer?"
The July analysis (`data/rain/rain_factors.json`) says how much rain slows each stretch *on average*. This file adds the
*places* where water collects, so the simulation and the screen can say "heavy rain: expect longer queues at Tolichowki,
Shaikpet, Nanal Nagar and Masab Tank" instead of "everything is 8% slower".

**Label on everything here: `reported (public sources), not measured by us`.** We did not survey a single junction. The
points come from GHMC / HYDRAA statements, traffic-police rain advisories and newspaper reports (Deccan Chronicle, The News
Minute, Siasat, The Hans India, South First, PTI). Every point in `waterlogging_points.json` carries the URLs we read.

## The points (10 found; 3 junctions with nothing reported)

| Junction | Place | Severity | Why (one line) | Years |
|---|---|---|---|---|
| A_lingampally | RUB Lingampally (station underpasses) | low* | underpasses flood after 15-20 min of rain; NGT summoned GHMC; police report slow traffic both sides | 2023-2025 |
| j01 | Lingampally flyover - Nallagandla road | low | one side of the road under water in front of the supermarket (one old report) | 2017 |
| j03 | Gachibowli junction | medium | water pooled at the junction, blocked box drain (HYDRAA 2026); IIIT jn diverted (2019); on GHMC's 2019 list | 2017-2026 |
| j04 | Biodiversity junction | medium | 5-6 lanes cut to one by water towards Khajaguda lake (2024); traffic diverted (2020) | 2019-2024 |
| j05 | Khajaguda - Biodiversity stretch | low | water at Orion Villa slowed Khajaguda -> Biodiversity (one report) | 2019 |
| j06 | Shaikpet nala / flyover (Narne Rd) | **high** | waist-deep water, cars submerged, police broke the divider to drain (2020); "worst hit", avoid the flyover (2024); CS ordered it cleared (2025) | 2020-2025 |
| j07 | Tolichowki | **high** | chronic: vehicles submerged (2020, 2024), HYDRAA flash-flood visit, "worst affected" road (2026), on GHMC's 2019 list | 2019-2026 |
| j08 | Nanal Nagar X Road / Mehdipatnam | medium | police: water-logging "particularly at Nanal Nagar" (2025); snail's pace from water clogging (2024) | 2020-2025 |
| j11 | Masab Tank | medium | "worst affected" road (2026); water at Ayodhya jn slowed vehicles from Masab Tank (2025); water clogging (2024) | 2018-2026 |
| B_lakdikapul | Lakdikapul (under the railway bridge) | **high** | on GHMC's 30-point list, drain rebuilt (2024-25), still flooded and diverted (Jul 2025), crawl (Aug 2025) | 2017-2026 |

\* The RUB is at the station, 400 m off the modelled route start, so it is counted as low even though the reports are chronic.

**Nothing reported:** j02 ISB Rd / DLF jn, j09 Rethibowli, j10 NMDC. A Sept 2025 advisory lists Rethibowli and NMDC as slow
on a rain day "due to peak hours", not as flooded, so they are not counted.

**Severity is our reading of the reports:** high = repeated deep water / stranded vehicles / road closed or an official hotspot
list; medium = water-logging that slows traffic, in more than one report; low = a single report.

## What the simulation does with it

`POST /corridor/runs {"weather": "heavy_rain"}` (or `light_rain`):

1. **Stretch factor (measured average).** Every leg's speed cap is multiplied by the July factor for that leg
   (`rain_factors.json`: e.g. heavy rain x0.90-0.98 per leg). This is what TomTom saw on average over whole legs on wet hours.
2. **Junction factor (reported hotspot extra), on top.** Every lane within **300 m** of a reported junction (the corridor
   coming in and going out, the cross arms, the junction itself) gets an extra cap: **heavy rain** high x0.75, medium x0.85,
   low x0.93; **light rain** only the high points, x0.875; dry: nothing. A flyover deck above the junction is *not* slowed
   (it is above the water), which is why a flyover at a hotspot helps in the rain.

**No double counting.** The stretch factor is an average over a 1-3 km leg; a flooded 300 m at one end is diluted in it.
The junction factor adds back that local extra. Both are labelled: the stretch factor `estimated` (TomTom x Open-Meteo),
the junction factor `assumed, scaled by reported severity`. Nobody has measured 0.75 / 0.85 / 0.93; they are a reading of
"vehicles submerged" vs "traffic slowed".

Same seed, same traffic, same signals for baseline and every variant: only lane speed caps change, so comparisons stay
deterministic.

## Where it shows up (for the screen)

- `GET /weather/factors` -> `waterlogging`: the table above with sources, `extra_speed_factor`, `by_what_if` (names per setting).
- `GET /weather/now` and `GET /weather?day&hour` -> `expected_waterlogging`: `{rain_class, what_if, names, junctions:
  [{junction_id, name, short, severity, extra_speed_factor, what_reported, label}], text}`. `text` is the sentence to show,
  e.g. "Heavy rain: expect longer queues at Gachibowli, Biodiversity jn, Shaikpet, Tolichowki, Nanal Nagar, Masab Tank and
  Lakdikapul (reported water-logging points, and 3 minor ones)". Heavy / moderate: every point; light: chronic (high) only.
- Run result (C5) `inputs.weather.waterlogging`: `[{junction_id, name, junction_name, severity, extra_speed_factor,
  lanes_slowed, label, what_reported, sources}]`, `inputs.weather.affected_junctions` (corridor junction names) and
  `inputs.weather.waterlogging_note`. The per-junction effect is in `junctions[].avg_delay_s` / `max_queue_m` as always.

## Files

- `waterlogging_points.json` - the points, sources, factor table, what was not found, the lists we checked.
- `../rain/rain_factors.json` - the per-stretch rain factors (measured average) this sits on top of.
- `../../sim/corridor/corridor_runner.py` `rain_at_hotspots()` - applies the junction factor to the network.
- `../../backend/app/weather.py` `expected_waterlogging()` - the API side.

## Limits

No machine-readable GHMC / HYDRAA list with named points was found (the 2026 reviews give counts: 523 points in GHMC,
913 across the city). The 2019 GHMC list of 123 points is an image. A few items came from search snippets rather than the
fetched page (noted per point in the JSON). Reports older than 2020 may describe roads rebuilt since.
