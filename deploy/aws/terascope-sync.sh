#!/usr/bin/env bash
# Copy what the demo produces on the instance to s3://<bucket>/data/ (same paths as in the repo). Run by
# terascope-sync.timer every 5 minutes; harmless to run by hand: sudo -u ubuntu terascope-sync
set -uo pipefail
APP=/opt/terascope
DEST="s3://${TERASCOPE_BUCKET:?set TERASCOPE_BUCKET}/data"
aws s3 sync "$APP/data/raw"          "$DEST/data/raw"          --only-show-errors
aws s3 sync "$APP/data/live"         "$DEST/data/live"         --only-show-errors
aws s3 sync "$APP/sim/out/corridor"  "$DEST/sim/out/corridor"  --only-show-errors --exclude "*.tmp"
# the SQLite decision log: a consistent snapshot, not the live file
sqlite3 "$APP/backend/cityrehearsal.db" ".backup /var/tmp/terascope/cityrehearsal.db" \
  && aws s3 cp /var/tmp/terascope/cityrehearsal.db "$DEST/backend/cityrehearsal.db" --only-show-errors
echo "$(date -u +%FT%TZ) synced to $DEST"
