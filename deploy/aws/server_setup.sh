#!/usr/bin/env bash
# Terascope AI on the EC2 instance: venv, systemd units, nginx. Run as root, after the bundles are unpacked in
# /opt/terascope (user-data does that on first boot). Idempotent: a redeploy re-runs it (see docs/deploy-aws.md).
#   BUCKET=terascope-demo-<account> REGION=ap-southeast-2 bash /opt/terascope/deploy/aws/server_setup.sh
set -euo pipefail
APP=/opt/terascope
mkdir -p /etc/terascope /var/tmp/terascope
BUCKET="${BUCKET:-$(cat /etc/terascope/bucket 2>/dev/null || true)}"
REGION="${REGION:-ap-southeast-2}"
echo "$BUCKET" > /etc/terascope/bucket

echo "== system libraries the eclipse-sumo wheel links (X11, OpenGL), nginx, sqlite3"
DEBIAN_FRONTEND=noninteractive apt-get install -y -q nginx sqlite3 curl python3.12-venv \
  libxrender1 libxext6 libxft2 libfontconfig1 libgl1 libglu1-mesa libxrandr2 libxcursor1 libxinerama1 libxi6 \
  libxfixes3 libxcomposite1 libxdamage1 libxkbcommon0 libx11-6 libice6 libsm6 libxcb1 >/dev/null

echo "== venv + backend and sim dependencies"
[ -x "$APP/.venv/bin/python" ] || sudo -u ubuntu python3.12 -m venv "$APP/.venv"
sudo -u ubuntu "$APP/.venv/bin/pip" install -q --upgrade pip
sudo -u ubuntu "$APP/.venv/bin/pip" install -q -r "$APP/backend/requirements.txt" -r "$APP/sim/requirements.txt" matplotlib
SUMO_HOME="$("$APP/.venv/bin/python" -c 'import sumo; print(sumo.SUMO_HOME)')"
"$APP/.venv/bin/sumo" --version | head -1

PARALLEL="$(nproc)"; [ "$PARALLEL" -gt 4 ] && PARALLEL=4     # one SUMO per core, at most 4 (the demo's warm-up size)
cat > /etc/terascope/env <<EOF
MOCK_SIM=0
CR_SIM_PARALLEL=${CR_SIM_PARALLEL:-$PARALLEL}
CR_KEEP_RUNS=60
CR_KEEP_RUNS_MB=8000
SUMO_HOME=$SUMO_HOME
PATH=$APP/.venv/bin:/usr/local/bin:/usr/bin:/bin
PYTHONUNBUFFERED=1
TERASCOPE_BUCKET=$BUCKET
AWS_DEFAULT_REGION=$REGION
EOF

echo "== cached runs: point the decision log's run files at $APP (see fix_run_paths.py)"
sudo -u ubuntu python3 "$APP/deploy/aws/fix_run_paths.py" "$APP/backend/cityrehearsal.db" "$APP"

echo "== services"
install -m 644 "$APP/deploy/aws/terascope-api.service" "$APP/deploy/aws/terascope-collector.service" \
  "$APP/deploy/aws/terascope-sync.service" "$APP/deploy/aws/terascope-sync.timer" /etc/systemd/system/
install -m 755 "$APP/deploy/aws/terascope-sync.sh" /usr/local/bin/terascope-sync
install -m 644 "$APP/deploy/aws/nginx-terascope.conf" /etc/nginx/sites-available/terascope
ln -sf /etc/nginx/sites-available/terascope /etc/nginx/sites-enabled/terascope
rm -f /etc/nginx/sites-enabled/default
nginx -t
chown -R ubuntu:ubuntu "$APP" /var/tmp/terascope
systemctl daemon-reload
systemctl enable terascope-api terascope-collector terascope-sync.timer >/dev/null
systemctl restart terascope-api terascope-collector
systemctl start terascope-sync.timer
systemctl reload nginx || systemctl restart nginx

echo "== waiting for /health"
for i in $(seq 1 90); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null; then curl -s http://127.0.0.1:8000/health; echo; echo "api up"; exit 0; fi
  sleep 2
done
echo "api did not answer in 3 minutes: journalctl -u terascope-api -n 100"; exit 1
