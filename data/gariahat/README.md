# Gariahat backtest (demo step 1, "Proof")

Source: B. Maitra, M. Azmi, N. Kumar, J. R. Sarkar, "Modeling traffic impact of flyover at an urban intersection
under mixed traffic environment", *European Transport / Trasporti Europei* 27 (2004), pp. 57-68. Open access:
[University of Trieste repository](https://www.openstarts.units.it/handle/10077/5846). Copy: `Maitra_et_al_2004_ET27.pdf`.

| File | Contents | Label |
|---|---|---|
| `volumes.csv` | Peak-hour vehicles per approach by class, approach widths (Table 3) | counted |
| `turns.csv` | Left / straight / right shares per approach (Table 4) | counted |
| `study_results.csv` | Delays before and after the flyover, vehicles on the flyover | study model |

**What the study found.** The flyover cuts average delay at Gariahat by 74.8% (35.3 s to 8.9 s), but delay on Phari's
approach from Gariahat more than doubles (42.4 s to 110.3 s) because traffic now arrives uninterrupted. Across both
junctions, peak-hour delay rises by 29.8 vehicle-hours: the flyover moves the problem rather than solving it.

**Honest framing for the pitch.** The "after" numbers are the authors' model predictions (their model was validated
at Deshpriya Park, within ~10% of field delays; the flyover was under construction). We say "our simulator reproduces
the study's finding", not "matches field data after the flyover".

**Study context.** Gariahat: 4-arm, two-phase signal before the flyover; straight traffic on approaches A and C uses
the flyover afterwards. Phari: 5-arm, three-phase signal; approach C is the road arriving from Gariahat.
Approach letters (A-E) still need matching to the roads in `sim/networks/gariahat_*.net.xml` (Figure 1 of the paper).
