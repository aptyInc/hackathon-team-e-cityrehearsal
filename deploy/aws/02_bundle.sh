#!/usr/bin/env bash
# Terascope AI demo on AWS, step 2: build the two release bundles and upload them to S3.
#   terascope-app.tar.gz   the git tree of REF (default: HEAD of the checkout this script runs in)
#   terascope-data.tar.gz  the gitignored runtime data from SRC (default: the repo root): TomTom CSVs, the decision
#                          log (SQLite), the cached corridor runs under sim/out/corridor/rc_*, the junction archive,
#                          data/live/*.json
# The secrets file (.env) is NOT bundled: upload it once, by hand, see docs/deploy-aws.md.
# Usage (repo root, any checkout):
#   AWS_PROFILE=terascope bash deploy/aws/02_bundle.sh [--no-upload]   # SRC=/path/to/checkout REF=integrate/round2
set -euo pipefail
export AWS_PAGER=""
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${SRC:-$HERE}"
REF="${REF:-HEAD}"
OUT="${OUT:-${TMPDIR:-/tmp}/terascope-release}"
MAX_RUNS_MB="${MAX_RUNS_MB:-1500}"
mkdir -p "$OUT"

echo "== app bundle from git ref ${REF} (checkout ${HERE})"
git -C "$HERE" archive --format=tar.gz --prefix=terascope/ -o "$OUT/terascope-app.tar.gz" "$REF"
ls -l "$OUT/terascope-app.tar.gz"

echo "== data bundle from ${SRC}"
LIST="$OUT/data-files.txt"; : > "$LIST"
add() { for f in "$@"; do [ -e "$SRC/$f" ] && echo "$f" >> "$LIST"; done; return 0; }
add data/raw/tomtom_corridor_junction_live.csv data/raw/tomtom_corridor_turn_ratios.csv
add $(cd "$SRC" && ls data/raw/tomtom_ymca_*.csv 2>/dev/null)
add backend/cityrehearsal.db
add data/tomtom/junction/archive
add $(cd "$SRC" && ls data/live/*.json data/live/*.jsonl 2>/dev/null)
add $(cd "$SRC" && ls sim/out/corridor/calibration_*.json 2>/dev/null)
add $(cd "$SRC" && ls data/tomtom/corridor/*.json 2>/dev/null)          # the two gitignored TomTom jobs that only have .gz in git
add $(cd "$SRC" && ls data/tomtom/junction/corridor/*.json 2>/dev/null) # junction definitions fetched by the collector
# cached corridor runs: only rc_* folders the DB's runs table references, newest first, under MAX_RUNS_MB in total
if [ -f "$SRC/backend/cityrehearsal.db" ]; then
  total=0
  for r in $(sqlite3 "$SRC/backend/cityrehearsal.db" "select id from runs where id like 'rc_%' order by created desc"); do
    d="$SRC/sim/out/corridor/$r"
    [ -d "$d" ] || continue
    mb=$(du -sm "$d" | cut -f1)
    if [ $((total + mb)) -gt "$MAX_RUNS_MB" ]; then echo "skip $r (${mb} MB, over budget)"; continue; fi
    total=$((total + mb)); echo "sim/out/corridor/$r" >> "$LIST"
  done
  echo "cached runs: $(grep -c 'sim/out/corridor/rc_' "$LIST") folders, ${total} MB"
fi
export COPYFILE_DISABLE=1     # macOS: no AppleDouble ._* files or xattr headers in the archive
tar -czf "$OUT/terascope-data.tar.gz" -C "$SRC" -T "$LIST"
ls -l "$OUT/terascope-data.tar.gz"

if [ "${1:-}" != "--no-upload" ]; then
  ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
  BUCKET="terascope-demo-${ACCOUNT}"
  echo "== upload to s3://${BUCKET}/release/"
  aws s3 cp "$OUT/terascope-app.tar.gz"  "s3://${BUCKET}/release/terascope-app.tar.gz"  --only-show-errors
  aws s3 cp "$OUT/terascope-data.tar.gz" "s3://${BUCKET}/release/terascope-data.tar.gz" --only-show-errors
  aws s3 ls "s3://${BUCKET}/release/"
fi
echo "bundle ok: $OUT"
