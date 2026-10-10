#!/usr/bin/env bash
# Terascope AI demo on AWS, step 4: redeploy the running instance from the bundles in S3 (after 02_bundle.sh), through
# Session Manager Run Command (no SSH). The app tree is replaced; the data bundle is unpacked over it only with --data
# (it would overwrite the CSVs the collector has appended to since launch).
# Usage: AWS_PROFILE=terascope bash deploy/aws/04_redeploy.sh [--data] [--restart-only]
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-ap-southeast-2}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="terascope-demo-${ACCOUNT}"
ID="${INSTANCE_ID:-$(aws ec2 describe-instances --filters Name=tag:Name,Values=terascope-demo Name=instance-state-name,Values=running \
      --query 'Reservations[0].Instances[0].InstanceId' --output text)}"
[ -n "$ID" ] && [ "$ID" != "None" ] || { echo "no running terascope-demo instance"; exit 1; }

if [ "${1:-}" = "--restart-only" ]; then
  CMDS='["systemctl restart terascope-api terascope-collector","sleep 5","systemctl is-active terascope-api terascope-collector nginx","curl -s http://127.0.0.1:8000/health"]'
else
  DATA=""; [ "${1:-}" = "--data" ] && DATA="aws s3 cp s3://${BUCKET}/release/terascope-data.tar.gz /var/tmp/terascope/data.tar.gz --only-show-errors && tar -xzf /var/tmp/terascope/data.tar.gz -C /opt/terascope && rm -f /var/tmp/terascope/data.tar.gz"
  CMDS=$(python3 - "$BUCKET" "$REGION" "$DATA" <<'EOF'
import json, sys
bucket, region, data = sys.argv[1:4]
cmds = [
  "set -e", f"export AWS_DEFAULT_REGION={region}",
  f"aws s3 cp s3://{bucket}/release/terascope-app.tar.gz /var/tmp/terascope/app.tar.gz --only-show-errors",
  "mkdir -p /opt/terascope.new && tar -xzf /var/tmp/terascope/app.tar.gz -C /opt/terascope.new --strip-components=1",
  # keep what the instance produced: runtime data, the decision log, the venv and the keys
  "for p in .env .venv backend/cityrehearsal.db backend/.cache sim/out data/raw data/live data/tomtom/junction data/tomtom/corridor; do"
  "  [ -e /opt/terascope/$p ] && rm -rf /opt/terascope.new/$p && mkdir -p $(dirname /opt/terascope.new/$p) && mv /opt/terascope/$p /opt/terascope.new/$p; done; true",
  "rm -rf /opt/terascope.old && mv /opt/terascope /opt/terascope.old && mv /opt/terascope.new /opt/terascope && rm -f /var/tmp/terascope/app.tar.gz",
  f"aws s3 cp s3://{bucket}/release/.env /opt/terascope/.env --only-show-errors && chmod 600 /opt/terascope/.env",
  data or "true",
  "chown -R ubuntu:ubuntu /opt/terascope",
  f"BUCKET={bucket} REGION={region} bash /opt/terascope/deploy/aws/server_setup.sh",
]
print(json.dumps(cmds))
EOF
)
fi

PARAMS="${TMPDIR:-/tmp}/terascope-ssm-params.json"
printf '{"commands": %s}' "$CMDS" > "$PARAMS"       # a JSON file: the CLI's shorthand syntax mangles quotes and newlines
CMD="$(aws ssm send-command --instance-ids "$ID" --document-name AWS-RunShellScript --comment "terascope redeploy" \
       --timeout-seconds 1800 --parameters "file://${PARAMS}" --query Command.CommandId --output text)"
echo "command ${CMD} on ${ID}; waiting"
for i in $(seq 1 180); do
  S="$(aws ssm get-command-invocation --command-id "$CMD" --instance-id "$ID" --query Status --output text 2>/dev/null || echo Pending)"
  case "$S" in Success|Failed|Cancelled|TimedOut) break;; esac
  sleep 10
done
aws ssm get-command-invocation --command-id "$CMD" --instance-id "$ID" --query '[Status,StandardOutputContent,StandardErrorContent]' --output text | tail -40
[ "$S" = "Success" ]
