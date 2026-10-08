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
