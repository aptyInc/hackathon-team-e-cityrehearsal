# /data — Data and proof workstream
| File | Source | Label |
|---|---|---|
| `raw/ymca_counts.csv` | Sohail, Faheem, Aquil, "Performance analysis of a roundabout using SIDRA Intersection software", IJRAR 7(2), June 2020, Table 2 — vehicles/hour per approach by class (copy: `raw/IJRAR19W1176_ymca_circle_study.pdf`, [link](https://www.ijrar.org/papers/IJRAR19W1176.pdf)) | counted (study) |
| `raw/ymca_geometry.csv` | Same study, Table 1 — entry and circulating widths, 17 m central island | counted (study) |
| `raw/tomtom_ymca_speeds.csv` | TomTom Traffic Stats route analysis, job 10048164 — 8 road stretches in/out of YMCA Circle, weekdays 1–31 Jul 2026, 24 one-hour slots | measured |
| `raw/tomtom_hitec_kondapur_speeds.csv` | TomTom Traffic Stats route analysis, job 10048181 — Cyber Towers junction (HITEC City, 8 stretches) and Kothaguda junction (Kondapur, 6 stretches), weekdays 1–31 Jul 2026, 24 one-hour slots | measured |
| `tomtom/` | Request files, fetch script and raw TomTom results (JSON, Excel, GeoJSON, Shapefile) | measured |
| `raw/ymca_buildings.geojson` | Overture Maps building footprints around YMCA Circle (3,370), downloaded 9 Oct 2026. No heights in Overture here: `render_height_m` = floors × 3.2 m, floors assumed from footprint area | footprints counted, heights assumed |
| `gariahat/` | Gariahat and Phari junctions from OpenStreetMap + published before/after study | study results |

Rules: label every value counted / estimated / assumed. No personal data. Keep API keys in `.env`, never here.

## Known gaps and caveats
- **Turns** are not in the study; they now come from TomTom Junction Analytics (`raw/tomtom_ymca_turn_ratios.csv`, `measured`). Overnight ratios are used until rush-hour data is collected.
- **Autos and buses** are grouped into the study's light and heavy classes: any split is `assumed`.
- **Study age:** counts were collected before 2020; any growth factor applied is `estimated`.
- **TomTom dates:** the trial only allows 1–31 Jul 2026 (monsoon month), not the last four weeks.
- **TomTom stretch "NE Narayanaguda Road - in"** in job 10048164 detoured through side streets (1,167 m instead of ~420 m); replaced in the CSV by a shorter clean re-run (job 10048193, 240 m). The same fix was applied to "Cyber Towers | NE Kukatpally Road - in".
- **Approach names:** the study's compass labels (S/W/N/E) do not obviously match the map; check each against OpenStreetMap before building routes.
- **Gariahat study numbers:** Maitra et al. (IIT Kharagpur, 2004) could not be downloaded (ResearchGate, Academia and Semantic Scholar refuse automated access). Request the PDF on ResearchGate; the backtest networks are ready in `sim/networks/`.
