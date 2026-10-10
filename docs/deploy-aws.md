# Terascope AI on AWS: the public demo server

**URL: http://13.237.4.166/** (the corridor page is `/corridor.html`; `/health` says `{"status":"ok","mock":false}`;
`/files/` lists the data files). One EC2 instance in **ap-southeast-2** (Sydney), AWS account `034456343762`
(the hackathon project, free plan with USD 100 credit), CLI profile `terascope`. Everything is tagged
`Project=terascope-demo`. Deployed Sat 10 Oct 2026 from branch `deploy/aws` (= `integrate/round2` plus the
`/files/` endpoint and the files in `deploy/aws/`).

## What was created

| Resource | Id / name | Notes |
|---|---|---|
| S3 bucket | `terascope-demo-034456343762` | private (public access blocked), SSE-S3 encryption, no versioning. `release/`: `terascope-app.tar.gz`, `terascope-data.tar.gz`, `.env`. `data/`: what the server syncs back every 5 min |
| IAM role + instance profile | `terascope-ec2-role` (`arn:aws:iam::034456343762:role/terascope-ec2-role`, `arn:aws:iam::034456343762:instance-profile/terascope-ec2-role`) | `AmazonSSMManagedInstanceCore` + inline `terascope-s3-bucket` (Get/Put/List on that bucket only) |
| Security group | `terascope-web` = `sg-0d75c110764521a06` (default VPC `vpc-05807667f88c7955c`) | inbound 80 and 443 from anywhere; **no port 22** (Session Manager instead) |
| EC2 instance | `i-0e6acd00597a93c29`, **m7i-flex.large** (2 vCPU, 8 GB), Ubuntu 24.04 `ami-0f5e1e0151e5b95ed`, 60 GB gp3 (encrypted), IMDSv2 required | subnet `subnet-04b0599e6b8cadbfc` (ap-southeast-2a) |
| Elastic IP | `13.237.4.166` (`eipalloc-043709a2ce80b115a`) | stays the same across stop/start |
| Service-quota request | `L-1216C47A` (on-demand standard vCPUs) 5 -> 8, pending | only matters on the paid plan, see below |

**Why not c7i.2xlarge.** The account is on the free plan: `RunInstances` refuses every instance type that is not
free-tier eligible (`InvalidParameterCombination: The specified instance type is not eligible for Free Tier`), so
c7i.2xlarge and all the fallbacks (c6i/m6i/c6a/t3 .2xlarge and .xlarge) were refused. The largest eligible type is
m7i-flex.large (Sapphire Rapids 3.2 GHz, 2 vCPU, 8 GB, 4 GB swap added). The server therefore runs **2 simulations in
parallel, not 4** (`CR_SIM_PARALLEL` = core count). A fresh corridor run takes about the same wall time as on a laptop
(one run per core); the demo's runs are all cached, see "Warm-up" below. To get c7i.2xlarge: upgrade the project to
the paid plan in AWS Settings > Billing, wait for the vCPU quota request (8 vCPUs; the free plan's limit is 5), then
`TYPES=c7i.2xlarge bash deploy/aws/03_launch.sh` and move the Elastic IP (`aws ec2 associate-address`), or just
`04_redeploy.sh` is not needed: the new instance sets itself up from the same bundles.

## How it runs on the instance

- `/opt/terascope`: the app tree (git archive) with the data bundle unpacked over it, `.env` (mode 600) and `.venv`
  (backend + sim requirements + matplotlib; SUMO 1.28 from the `eclipse-sumo` wheel, which needs the X11/OpenGL
  libraries the setup installs).
- `/etc/terascope/env` (read by the units): `MOCK_SIM=0`, `CR_SIM_PARALLEL=<cores, max 4>`, `CR_KEEP_RUNS=60`,
  `CR_KEEP_RUNS_MB=8000` (so the shipped cached runs are not pruned), `SUMO_HOME`, `PATH` with the venv,
  `TERASCOPE_BUCKET`.
- systemd units (`deploy/aws/*.service|timer`), all as user `ubuntu`:
  - `terascope-api`: `uvicorn app.main:app --host 127.0.0.1 --port 8000` in `backend/`, restart always.
  - `terascope-collector`: `python3 data/tomtom/collect_corridor_junctions.py` (one TomTom snapshot per minute into
    `data/raw/tomtom_corridor_*.csv`; log `data/tomtom/junction/corridor_collector.log`).
  - `terascope-sync.timer` -> `terascope-sync.service` every 5 min: `aws s3 sync` of `data/raw`, `data/live`,
    `sim/out/corridor` and a consistent `.backup` of `backend/cityrehearsal.db` to `s3://terascope-demo-034456343762/data/`.
- nginx (`deploy/aws/nginx-terascope.conf`): port 80 -> 127.0.0.1:8000, `proxy_read_timeout 600`, WebSocket upgrade
  (`/stream/<run_id>`), `client_max_body_size 50m`. The frontend files hardcode `http://localhost:8000` as the API
  address; nginx rewrites that string to the server's own address in HTML/JS responses (`sub_filter`), so nothing in
  `frontend/` changed. Port 443 is open in the security group but there is no certificate (no domain name): use http.
- `/files/` (new in `backend/app/main.py`): an allow-listed index of the data behind the screens (TomTom CSVs,
  corridor/weather/rain definitions, each cached run's `result.json` and `frames.jsonl`). Never the SQLite log or `.env`.

## Day-to-day

Everything below uses the CLI profile: `export PATH="$HOME/.local/bin:$PATH" AWS_PROFILE=terascope AWS_REGION=ap-southeast-2`.

**Logs and a shell (no SSH):**
```bash
aws ssm start-session --target i-0e6acd00597a93c29          # interactive shell (needs the session-manager-plugin)
# or one-off commands:
aws ssm send-command --instance-ids i-0e6acd00597a93c29 --document-name AWS-RunShellScript \
  --parameters 'commands=["systemctl status terascope-api --no-pager | head -20","journalctl -u terascope-api -n 50 --no-pager"]' \
  --query Command.CommandId --output text        # then: aws ssm get-command-invocation --command-id <id> --instance-id i-0e6acd00597a93c29
```

**Redeploy a new build** (about 3 minutes; the instance keeps its data, decision log, venv and keys):
```bash
git checkout deploy/aws && git merge integrate/round2       # or whatever branch is the build to ship
make smoke
SRC=/path/to/checkout/with/the/runtime/data REF=HEAD bash deploy/aws/02_bundle.sh   # app + data bundles -> S3 release/
bash deploy/aws/04_redeploy.sh                 # app tree replaced, server_setup.sh re-run, services restarted
bash deploy/aws/04_redeploy.sh --data          # also unpack the data bundle (overwrites the CSVs the collector appended to)
bash deploy/aws/04_redeploy.sh --restart-only  # just: sudo systemctl restart terascope-api terascope-collector
```
The secrets file is not in the bundles: `aws s3 cp .env s3://terascope-demo-034456343762/release/.env` once (done), and
the redeploy fetches it. After any change to `sim/corridor/calibration.json`, `corridor_runner.py`, `corridor_net.py`
or `sim/templates/corridor.py`, run the warm-up again (the cache key includes them).

**Warm-up** (docs/demo-script.md, pre-flight step 3) against the server: the same `warm()` block with
`http://13.237.4.166` in place of `http://localhost:8000`. Every line must say `cached`.

**Stop to save credit** (the Elastic IP and the disk stay; the URL is the same after start):
```bash
aws ec2 stop-instances --instance-ids i-0e6acd00597a93c29
aws ec2 start-instances --instance-ids i-0e6acd00597a93c29     # ~2 min; the units start on boot
```
**Terminate** (after the demo; the bucket keeps the synced data):
```bash
aws ec2 terminate-instances --instance-ids i-0e6acd00597a93c29
aws ec2 release-address --allocation-id eipalloc-043709a2ce80b115a
aws ec2 delete-security-group --group-id sg-0d75c110764521a06        # once the instance is gone
# optional, to remove everything:
aws s3 rb s3://terascope-demo-034456343762 --force
aws iam remove-role-from-instance-profile --instance-profile-name terascope-ec2-role --role-name terascope-ec2-role
aws iam delete-instance-profile --instance-profile-name terascope-ec2-role
aws iam detach-role-policy --role-name terascope-ec2-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role-policy --role-name terascope-ec2-role --policy-name terascope-s3-bucket
aws iam delete-role --role-name terascope-ec2-role
```

## Costs (on-demand, Sydney, from the AWS price list)

| Item | Rate | Per day |
|---|---|---|
| m7i-flex.large, running | USD 0.1197 / h | USD 2.87 |
| 60 GB gp3 disk | ~USD 0.096 / GB-month (~USD 0.008 / h) | USD 0.19 |
| Elastic IP (public IPv4, in use or idle) | USD 0.005 / h | USD 0.12 |
| S3 (~0.2 GB release + synced data) and requests | < USD 0.05 / day | |
| **Total while running** | **~USD 0.13 / h** | **~USD 3.2 / day** |
| Stopped instance | disk + IP only | ~USD 0.31 / day |

For comparison c7i.2xlarge (paid plan) is USD 0.4662 / h (~USD 11.4 / day running). The USD 100 credit covers the
m7i-flex.large demo server for about a month; stop it when nobody is demoing.

## Verification (Sat 10 Oct 2026, 06:15-06:40 IST)

- `/health` answered 156 s after launch with `{"status":"ok","mock":false}` (first boot needed the X11 libraries
  and the cached-run path fix, both now in `server_setup.sh`). `04_redeploy.sh` tested end to end at 06:36 IST (~4 min).
- `GET /corridor` 200 (183 kB, 2.5 s), `/corridor/junctions/live` 200 (94 kB, live rows at 06:18 IST from the
  server's own collector), `/weather/now` 200 ("Clear sky, 23 C"), `/agent/suggestions` 200, `/agent/advice` 200,
  `/files/` 200 (index), `/files/sim/out/corridor/<run>/result.json` 200, `frames.jsonl` 200 (28 MB in 31 s).
- `/corridor.html` in headless Chromium (Playwright, 1440x900): loaded in 17 s, **0 JS errors, 0 failed requests**;
  map, live trip (33.5 min, confidence high), live junctions, weather chip, quick actions, "API: ok (real SUMO runs)".
  The API address in the served HTML/JS is `http://13.237.4.166` (nginx rewrite), no `localhost` left.
- WebSocket `ws://13.237.4.166/stream/<run_id>` through nginx: frames of ~3,760 vehicles every 4 s of sim time.
- Services: `terascope-api`, `terascope-collector`, `terascope-sync.timer`, `nginx` all active; the first sync put
  1,496 objects (741 MB) under `s3://terascope-demo-034456343762/data/`.
- Warm-up (the demo-script block against the server; `cached` = served from the shipped decision log + run folders,
  `NEW RUN` = simulated on the server, 2 in parallel):

  | Request | Result | Time |
  |---|---|---|
  | today 100% | cached 56.6 min | 1.4 s |
  | today 80% | NEW RUN 55.2 min | 80 s |
  | today 110% | cached 59.0 min | 1.3 s |
  | flyover Nallagandla | cached 54.5 min | 1.1 s |
  | flyover ISB Rd / DLF | NEW RUN 54.6 min | 106 s |
  | one flyover Nanal Nagar + Rethibowli | cached 53.5 min | 1.3 s |
  | DLF side roads signal retime | NEW RUN 57.3 min | 115 s |
  | heavy rain, today | NEW RUN 65.3 min | 125 s |
  | heavy rain + the Nanal Nagar flyover | NEW RUN 61.9 min | 117 s |
  | 110% + the Nanal Nagar flyover | NEW RUN 54.1 min | 121 s |

  A second pass answers every line `cached` in 1.2-1.7 s, also after a redeploy. Note: the two heavy-rain numbers
  (65.3, 61.9) differ from the demo script's laptop values (63.8, 61.2): the laptop's rain runs were not in the
  shipped decision log, so the server simulated them fresh. Read the numbers off the server on stage, or update the cue card.
- Known gaps: the decision log was copied at 06:01 IST while the laptop's `advise_all` was still running, so
  `GET /agent/advice` shows j05 `running` and j03-j11 `stale` on the server exactly as on the laptop at that moment.
  Fix before the demo: once the laptop's advice is fresh, `bash deploy/aws/02_bundle.sh` then
  `bash deploy/aws/04_redeploy.sh --data` (copies the laptop's DB and run folders over; the server's own new runs
  stay on disk but their cache rows are replaced), then run the warm-up block against the server again. Or run
  `cd backend && CR_DB=$PWD/cityrehearsal.db python -m app.agent.advise_all` on the server (2 cores: slow).
- The live trip spends the TomTom Flow key's daily budget on both machines (laptop cap 2000, server cap 1200,
  TomTom free tier 2500/day): if judges keep the public page open for hours, lower `CR_LIVE_DAILY_CAP` in
  `/etc/terascope/env` and `systemctl restart terascope-api`.
