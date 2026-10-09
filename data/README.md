# /data — Data and proof workstream
| File | Source | Label |
|---|---|---|
| `raw/ymca_counts.csv` | Sohail, Faheem, Aquil, "Performance analysis of a roundabout using SIDRA Intersection software", IJRAR 7(2), June 2020, Table 2 — vehicles/hour per approach by class (copy: `raw/IJRAR19W1176_ymca_circle_study.pdf`, [link](https://www.ijrar.org/papers/IJRAR19W1176.pdf)) | counted (study) |
| `raw/ymca_geometry.csv` | Same study, Table 1 — entry and circulating widths, 17 m central island | counted (study) |
| `raw/tomtom_ymca_speeds.csv` | TomTom Traffic Stats route analysis, job 10048164 — 8 road stretches in/out of YMCA Circle, weekdays 1–31 Jul 2026, 24 one-hour slots | measured |
| `raw/tomtom_hitec_kondapur_speeds.csv` | TomTom Traffic Stats route analysis, job 10048181 — Cyber Towers junction (HITEC City, 8 stretches) and Kothaguda junction (Kondapur, 6 stretches), weekdays 1–31 Jul 2026, 24 one-hour slots | measured |
| `raw/tomtom_ymca_junction_live.csv`, `raw/tomtom_ymca_turn_ratios.csv` | TomTom Junction Analytics archive, junction 6ac7d6870b461bdaf5cd8158 — per minute from 8 Oct 23:17 IST: delay, queue, volume per road; turn ratios over rolling 30-minute windows (`python3 data/tomtom/fetch_junction_archive.py 2026-10-08`) | measured; volume and queue estimated (TomTom model) |
| `raw/rain_july_hyderabad.csv` | Open-Meteo historical archive (ERA5-based reanalysis), hourly precipitation July 2026 at Lingampally, Gachibowli, Lakdikapul (`data/rain/analyse_rain.py`) | measured (modelled rain, not a gauge) |
| `raw/corridor_rain_vs_trip.csv`, `rain/` | Rain vs Lingampally → Lakdikapul trip, 1–15 July 2026; rain setting for the simulation in `rain/rain_factors.json`. See `rain/README.md` | trip measured; factors estimated |
| `tomtom/` | Request files, fetch script and raw TomTom results (JSON, Excel, GeoJSON, Shapefile) | measured |
| `raw/ymca_buildings.geojson` | Overture Maps building footprints around YMCA Circle (3,370), downloaded 9 Oct 2026. No heights in Overture here: `render_height_m` = floors × 3.2 m, floors assumed from footprint area | footprints counted, heights assumed |
| `gariahat/` | Maitra et al. 2004 (open access): peak-hour volumes, turns and widths for Gariahat and Phari, plus the study's before/after delays. See `gariahat/README.md` | counted (volumes, turns); study model (after-flyover delays) |

Rules: label every value counted / estimated / assumed. No personal data. Keep API keys in `.env`, never here.

## Known gaps and caveats
- **Turns** are not in the study; they now come from TomTom Junction Analytics (`raw/tomtom_ymca_turn_ratios.csv`, `measured`). Overnight ratios are used until rush-hour data is collected.
- **Autos and buses** are grouped into the study's light and heavy classes: any split is `assumed`.
- **Study age:** counts were collected before 2020; any growth factor applied is `estimated`.
- **TomTom dates:** the trial only allows 1–31 Jul 2026 (monsoon month), not the last four weeks.
- **TomTom stretch "NE Narayanaguda Road - in"** in job 10048164 detoured through side streets (1,167 m instead of ~420 m); replaced in the CSV by a shorter clean re-run (job 10048193, 240 m). The same fix was applied to "Cyber Towers | NE Kukatpally Road - in".
- **Approach names:** the study's compass labels (S/W/N/E) do not obviously match the map; check each against OpenStreetMap before building routes.
- **Gariahat study:** found open access at the University of Trieste repository; tables saved in `gariahat/`. Approach letters A-E still need matching to the network roads.
