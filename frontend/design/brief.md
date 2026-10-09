# CityRehearsal UI refresh: design brief

**Chosen direction: A, "Control room".** Direction B, "Civic clarity", was explored as the alternative and stays in this folder for reference.

| File | What it is |
|---|---|
| `a-home.html`, `a-corridor.html`, `a-kit.html` | Direction A: home, corridor (main demo) and the component kit |
| `b-home.html`, `b-corridor.html` | Direction B (not chosen) |
| `a.css` / `b.css` | Token and component CSS for each direction |
| `kit.js`, `data.js` | Mockup helpers. `data.js` is a snapshot of the real API taken Fri 9 Oct 22:00 |
| `shots/*.png` | Screenshots at 1440×900 and 390 px wide (full page) |

**About the numbers.** TomTom legs, hourly trip times, live junction delays and queues are **real** (API snapshot). The run totals match the team's real runs: TomTom 56.2 min, model 55.4 min, Nanal Nagar + Rethibowli flyover −2.1 ± 0.9 min, Nallagandla flyover −1.9, DLF flyover −1.7, DLF side-road green +2.6. The **per-leg split of the simulated rows, the junction queue figures for the model and the flyover (96 m, 18 m), and the decision-timeline hashes are illustrative**. The real app fills all of these from the API.

---

## 1. Design principles

1. **Measured and simulated must never be confused.** Measured is always cyan (`--real`) and simulated is always violet (`--sim`). A simulated change is magenta (`--chg`) with a hatch pattern. Each of these also carries a word tag (REAL, LIVE, EST, SIM), so colour is never the only signal.
2. **The number is the hero.** Trip minutes, deltas and delays are set in Geist Mono with tabular figures, and they are the largest type on each card. Every delta shows its noise (± 0.9), and a delta inside the noise is grey, not green.
3. **The map is the stage.** It runs full-bleed. Panels float over it as frosted glass, so the city stays visible behind the controls.
4. **Calm by default, loud on exceptions.** Neutral greys carry most of the screen. Colour is kept for what matters: the speed ramp, rose for "8.8× worse than usual", green for a saving beyond noise.
5. **Every step is legible to a non-engineer.** Panels are numbered (01 When, 02 Quick demos, 03 Change a junction), labels use plain words, and the AI answer quotes the same numbers as the strip.
6. **Offline-safe and built without a build step.** All libraries are vendored under `frontend/vendor/` and fonts have system fallbacks.

## 2. Direction A: "Control room"

A dark mission-control screen: a full-bleed dark map, frosted-glass panels and neon data accents. It looks good on a projector and in a dim boardroom, and it makes the 3D vehicles and the speed-coloured route pop.

### Palette (tokens in `a.css`)
| Token | Value | Use |
|---|---|---|
| `--bg` / `--bg-2` | `#07090d` / `#0c1017` | page and map fallback |
| `--glass` / `--glass-strong` | `rgba(14,18,26,.72)` / `.86` + `blur(18px) saturate(150%)` | floating panels, dialogs |
| `--line` / `--line-2` | white 8% / 14% | hairlines, control borders |
| `--tx` / `--tx-2` / `--tx-3` | `#e8edf5` / `#a3adbd` / `#6b7587` | text levels (AA on glass) |
| `--brand` | `#ff7a45` | logo and eyebrow only |
| **`--real`** | `#22d3ee` (bg 12%, line 35%) | TomTom measured or live: tags, measured row, hour bars |
| **`--sim`** | `#a78bfa` | model output: tags, simulated row, primary button |
| **`--chg`** | `#e879f9` | simulated *with changes*: hatched row, selected junction, AI accents |
| `--warn` | `#fbbf24` | *estimated* inputs (queue, volume), mid-speed |
| `--good` / `--bad` / `--neutral` | `#34d399` / `#fb7185` / `#94a3b8` | delta faster / slower / within noise |
| Map speed ramp | `#2dd4a7` ≥ 25 km/h · `#fbbf24` 15–25 · `#f43f5e` < 15 | route line plus a 16 px blurred glow |
| Vehicles | 2W `#fb923c` · car `#60a5fa` · auto `#facc15` · bus `#34d399` | deck.gl layer (always SIM) |

### Typography
**Geist** for UI (400/500/600) and **Geist Mono** for numbers, labels and tags. Load them from Google Fonts with a fallback to the vendored woff2 files, then `system-ui` / `ui-monospace`.
Scale: display 54/600 at −4.5% tracking · metric 44/600 mono · card title 16/600 · body 13/1.45 · label 11/600 mono uppercase at +10% tracking · tag 10/600 mono.

### Spacing, radius, shadow
4-pt grid (4, 8, 12, 16, 24, 32). The window gutter is 12 px, panel padding 14–16 px, and the gap between panels 10–12 px.
Radius: `--r-sm` 8 (fields, small buttons) · `--r` 12 (tiles, demo cards) · `--r-lg` 16 (panels) · `--r-xl` 20 (dialogs).
Shadow: `0 10px 40px -10px rgba(0,0,0,.7)` plus a 1 px inner top highlight (`--hi`) that gives the glass its edge.

### Components (all in `a-kit.html`)
- **Nav:** a floating glass bar with logo mark, crumb, tabs (active tab is a raised pill), the mode switch, and an "Ask CityRehearsal… ⌘K" field that opens chat.
- **Mode switch** "● Live now | July typical day": a segmented control with a pulsing cyan dot on Live.
- **Cards and panels:** glass, 16 px radius. Sections inside a panel are split by hairlines and get numbered mono headers.
- **Stat tiles:** three tiles in a row with 1 px gaps. Label on top, a 22 px mono value, and a tag underneath for provenance.
- **Junction card:** junction badge and name, a 44 px delay in rose with a glow, a meter with a white tick at the usual delay, and stat tiles for queue now (EST), model queue (SIM) and with-change (CHG).
- **Data table:** mono numbers aligned right, units in `--tx-3`, severity colours (rose ≥ 3× usual, amber ≥ 1.4×), the selected row tinted violet.
- **Trip strip:** three rows on one shared minutes axis, so a longer trip draws a longer bar. Each row has a REAL, SIM or CHG tag, a name, a segmented bar (one block per leg, width = minutes) and the total with its delta and noise. Legs in the with-changes row that changed beyond noise get a green or red underline and show their delta. Junction numbers sit on the axis under the bars.
- **Chips and tags:** chips are pill toggles for variant kind and layers. Tags are 19 px mono uppercase with a dot, for provenance only.
- **Buttons:** primary uses a violet gradient (running the model is the main action), secondary is outline glass, ghost has no border. Heights are 34 and 28 (small), plus a 40 px primary for the main CTA.
- **Day + hour picker:** a day select plus a **24-bar histogram of real trip minutes by hour**. You pick the hour by clicking its bar, so you can see the rush hour before you choose it. A minute slider and the follow-car toggle sit under it.
- **Playback:** a glass pill with play/pause, mono clock, SIM tag, speed and a follow-car switch.
- **Chat:** the AI bubble has a magenta-to-violet tint and the user bubble is neutral. The input has a send button. Answers quote numbers in mono with good/bad colours.
- **Timeline:** a vertical rail with icon nodes (done = green glow, current = magenta), and actor, time and a short SHA-256 chip on each step.
- **Dialog:** strong glass over a blurred scrim, with header icon, body, textarea and a footer (ghost Cancel, primary Send).
- **Toast and progress:** "Running SUMO…" with an indeterminate violet sweep.

### Map styling
- Basemap: **TomTom `basic_night`** when `/config` returns a key (already licensed). Otherwise **CARTO dark-matter**, which is keyless and needs attribution (the mockups use this one).
- A vignette (radial gradient, CSS overlay) darkens the edges so the panels read well.
- Route: a speed-coloured line of 5 px over a 16 px glow at 55% opacity. Junction markers are 22 px round mono badges. The selected junction is magenta with a pulsing ring, and a junction that already has a flyover gets a magenta halo. End points are white A and B.
- deck.gl vehicles keep the vehicle palette above. 3D buildings use a dark extrusion (`#1b2230`, 0.8 opacity).
- The live callout is a small glass card anchored under the selected junction.

### Motion
120–180 ms ease-out on hover and press. Panels fade and rise 4 px when they appear. The Live dot pulses every 2 s. The selected junction ring pulses every 2.2 s. The progress bar sweeps while a run is in flight. Map moves use `flyTo` at 1.2 s. All of this is off under `prefers-reduced-motion`.

### Iconography
**Lucide**, 16 px at 1.75 stroke: git-merge (flyover), timer (retime), move-horizontal (widen), traffic-cone (signals), flask-conical (simulate with changes), sparkles (AI), radio (live), shield-check (decisions).

### Responsive
- **≥ 1200 px:** left panel 344, right column 340, trip dock between them, all floating over the map.
- **760–1200 px:** the right column collapses into a tab in the left panel and the dock goes full width.
- **< 760 px (phone):** a sticky glass top bar with logo, mode switch and AI button; the map at 380 px; then the trip strip, junction card, live table, chat and controls stacked as cards. The strip rows stack (label, bar, total) and drop the in-block numbers. There is no sideways scroll.

## 3. Libraries (no build step, vendored under `frontend/vendor/`)
| Library | How | Why |
|---|---|---|
| **Hand-written token CSS** (`frontend/tokens.css` + `frontend/app.css`) | static files, CSS variables | A design system in about 400 lines. No toolchain, and four people can edit it during a hackathon. |
| **Lucide** (UMD `lucide.min.js`, pinned) | `<i data-lucide="…">` + `lucide.createIcons()` | Clean, consistent icons. Works offline once vendored. |
| **Geist / Geist Mono** | Google Fonts, plus woff2 vendored in `vendor/fonts/` with `@font-face` fallback | Modern grotesk and a mono with tabular figures. |
| MapLibre GL + deck.gl | already vendored | Unchanged. The glass panels are plain DOM above the map canvas (z-index), which needs no integration work. |
| Shoelace | **not adopted** (optional later for dialog/tooltip) | See trade-offs. |

**Trade-offs, in 5 lines:**
1. Tailwind (standalone CLI) would make styling faster for new pages, but it adds a compile step and long class strings to 3,000 lines of existing markup. A token file keeps the diff small and reviewable.
2. Shoelace gives polished switch, slider and dialog components, but they live in shadow DOM: Playwright's `select_option('#hour-sel')` and similar calls on native controls would break. Native `<select>`, `<input type=range>` and `<dialog>`, styled with tokens, keep every test green.
3. Glass (`backdrop-filter`) costs GPU over a WebGL map. It is limited to about six panels, and older laptops fall back to the solid `--glass-strong`.
4. CARTO dark-matter is the nicest free dark basemap, but production should use TomTom `basic_night`, which is already keyed and licensed, so CARTO is the fallback only.
5. No React: every page keeps its IDs and vanilla JS, so the restyle is CSS plus small markup edits, not a rewrite.

## 4. Direction B: "Civic clarity" (not chosen)
A light, editorial look: Instrument Serif headlines, Inter UI, warm paper background (`#f6f5f2`), crisp white cards and ink-black buttons. The map is a hero card (CARTO Positron) with a clean right rail. It uses the same teal/violet REAL/SIM hue pair, darkened for a light background. It reads beautifully in print and daylight, but it is less dramatic for a 3D traffic demo on a projector.

## 5. Implementation plan (direction A on the real app)

**Shared (wave 1, done):** `frontend/tokens.css` holds the tokens and the Geist `@font-face` rules. Content pages get it through `frontend/app.css`, which keeps the existing class names; map pages link it directly. `vendor/lucide.min.js` and `vendor/fonts/*.woff2` are vendored. `nav.js` is restyled as a 48 px glass bar with the same IDs (`#cr-nav`, links, pill) and a two-row bar on phones.

| Page | Change | Time |
|---|---|---|
| `index.html` (home) | hero, live ticker, KPI tiles, cards, How it works; keep the IDs the home test reads | 45 min |
| `decisions.html` | glass list, stage filter chips, case detail with timeline, runs table, evidence chips, dialog | 45 min |
| `data.html` | sources with REAL/SIM tags, tables in mono, calibration knobs as stat tiles | 30 min |
| `ymca.html` | full-bleed dark map, glass panels, same playback and chips | 40 min |
| `corridor.html` + `planner.js` (wave 2, after `frontend/two-modes` merges) | dark map style (TomTom `basic_night` → CARTO dark), left panel sections 01–03 + hour histogram over the existing `#hour-sel`, right junction card, trip dock restyle of `#strips`, chat restyle, step 4 review | 1.5–2 h |

**Keeping tests green.**
- Never rename or remove an `id` used in `scripts/ui_test*.py`. Restyle by adding classes and wrapping elements.
- Selectors the tests use that are *not* IDs must keep their class names, for example `.tag.real`, `.stages li[aria-current=step]`, `.stages li.done`, `#timeline .tl > li`, `.case-row`, `.fp`, `.chain-ok`/`.chain-bad`, `.strip[data-strip]`, `tr[data-leg]`, `tr[data-run]`, `.knob`, `.lab.assumed`, `.md-h`, `#tags + .legend`.
- Native `<select>` and `<input>` stay underneath any custom visual (the hour histogram drives `#hour-sel`, not the other way round).
- Run `ui_test_app.py`, `ui_test.py`, `ui_test_corridor.py` and `ui_test_review.py` one at a time after each page.
