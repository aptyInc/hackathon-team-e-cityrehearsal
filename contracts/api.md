# C4 Workflow API (frontend -> backend)

Base URL: `http://localhost:8000`

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /health | – | `{status, mock}` |
| POST | /cases | `{junction_id, title, raised_by}` | case |
| GET | /cases/{case_id} | – | case with variants, runs, decisions |
| POST | /variants | C3 variant spec + `case_id` | variant |
| POST | /runs | `{case_id, variant_id, volume_scale, run_by}` | C2 run result |
| GET | /runs/{run_id} | – | C2 run result |
| WS | /stream/{run_id} | – | stream of C1 frames |
| POST | /cases/{case_id}/submit | `{chosen_variant_id}` | case with evidence fingerprint (SHA-256) |
| POST | /cases/{case_id}/review | `{reviewer, recommendation, comments}` | case (recommend needs a reviewer re-run first) |
| POST | /cases/{case_id}/decide | `{decision: approve/reject/defer, reason}` | case |

Stages: `exploring → proposed → in_review → decided`. Runs are append-only; there is no delete endpoint.

## Corridor (added 9 Oct 2026, C5)
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /corridor | – | corridor definition (`data/corridor/corridor.json`): points A, j01..j11, B with names and coordinates |
| POST | /corridor/runs | `{window?, minutes?, volume_scale?, interventions: [{junction_id, kind, params}]}` | C5 corridor result (`corridor_result.schema.json`) |
| GET | /runs/{run_id} | – | C2 or C5 result |
| WS | /stream/{run_id} | – | C1 frames of the run |
| GET | /runs/{run_id}/roads | – | per-road simulated speeds (GeoJSON) |
| POST | /corridor/runs?async=1 | same body as POST /corridor/runs | 202 `{run_id, status}`; poll GET /corridor/runs/{run_id} |
| GET | /corridor/runs/{run_id} | – | `{run_id, status: queued/running/done/failed, elapsed_s, result? (C5), error?, http_status?}` |
| GET | /corridor/junctions/live | `?window_minutes=60` | `{source, labels, window_minutes, junctions: [{id, name, tomtom_id, time, age_s, approaches: [{approach_id, name, time, delay_s, usual_delay_s, queue_m, volume_per_hour, travel_time_s, free_flow_travel_time_s, closed, stale, last_60min: {samples, from, to, delay_s, usual_delay_s, queue_m, volume_per_hour}}]}]}` (delay measured; queue, volume estimated) |
| GET | /corridor/buildings | – | `data/corridor/buildings/index.json` (404 until present) |
| GET | /corridor/buildings/{point_id} | – | GeoJSON building footprints around a corridor point (A_lingampally, j01..j11, B_lakdikapul) |

With `MOCK_SIM=1`, POST /corridor/runs returns `contracts/samples/corridor_results.sample.json` (baseline, or `flyover_j07` when any intervention is given).

Added 9 Oct 17:50 (fields added only):
- GET /corridor also returns `tomtom.periods[]` (measured leg times: July average first, then each day; `label` e.g. "Typical July day (06-23)", "Wed 1 Jul, 08-20"), `route` (GeoJSON: `kind:"route"` per direction A->B / B->A, `kind:"leg"` per leg with from_id/to_id) and `labels`.
- POST /corridor/runs also accepts `run_by` and `case_id` (optional). Errors: 400 for an unknown junction/kind, a duplicate kind at one junction, volume_scale outside 0.1-3, or params a template rejects; 500 with a plain-language `detail` when the simulation cannot finish (e.g. gridlock).
- C5 results from the API add `fingerprint` (SHA-256 of the result) and, on a cache hit, `cached: true`; mock results add `sample: true` and `requested`. Identical requests (same sorted interventions, volume_scale, window, minutes, calibration and sim code) return the stored result instantly.

## Planning assistant and corridor cases (added 9 Oct 2026, fields added only)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /agent/chat | `{session_id?, message}` | `{session_id, turn_id, reply (markdown), steps: [{tool, input, summary, run_id?, brief_id?}], run_ids, brief_id, usage: {input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens, cost_usd, model}}`; 503 `{detail}` when ANTHROPIC_API_KEY is missing or the Claude API fails; 409 while the session is still answering |
| POST | /agent/chat?async=1 | same body | 202 `{session_id, turn_id, status: "running"}` |
| GET | /agent/turns/{turn_id} | – | `{turn_id, session_id, status: running/done/failed, message, steps, run_ids, reply?, brief_id?, error?, http_status?, usage?}` |
| GET | /agent/sessions/{session_id} | – | `{session_id, model, created, turns: [turn], brief_ids}` |
| GET | /briefs/{brief_id} | – | `{brief_id, session_id, markdown, run_ids, fingerprints: {run_id: sha256}, fingerprint, recommendation, created_at}` |
| POST | /corridor/cases | `{title, run_ids, brief_id?, created_by?}` | corridor case, stage `proposed` |
| GET | /corridor/cases | – | `[{case_id, title, stage, brief_id, created_by, created, runs}]` |
| GET | /corridor/cases/{case_id} | – | `{case_id, title, stage, brief_id, created_by, created, runs: [{run_id, role: option/review, added_by, option, interventions, volume_scale, total_min, inputs, warnings, sample, fingerprint}], fingerprints: {run_id or "brief:<id>": sha256}, events: [{seq, kind: proposed/review/decision, actor, body, fingerprint, prev, created}], decision, fingerprint}` |
| POST | /corridor/cases/{case_id}/review | `{reviewer, volume_scale? (default 1.0), note?}` | case; re-runs every option and the baseline at that volume, stage `in_review`; 409 when decided |
| POST | /corridor/cases/{case_id}/decide | `{decider, decision: approve/reject/revise, reason}` | case, stage `decided` (`revise` allows another review); 409 before a review; 400 for a bad decision |

Corridor case stages: `proposed → in_review → decided`. Append-only; each event's fingerprint = SHA-256 over its body, the evidence fingerprints and the previous event's fingerprint.
Optional mock: `CR_MOCK_SYNTH=1` makes POST /corridor/runs (MOCK_SIM=1) return illustrative numbers shaped like the request (`variant_id` e.g. `signal_retime_j07`, `inputs.label: "assumed"`, a `MOCK_SIM` warning) instead of the fixed sample when the request differs from it.
