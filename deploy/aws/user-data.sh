#!/bin/bash
# cloud-init user-data for the Terascope AI demo instance (Ubuntu 24.04 x86_64). 03_launch.sh fills in __BUCKET__ and
# __REGION__. Progress: /var/log/cloud-init-output.log on the instance (Session Manager, no SSH).
# What it does: packages, AWS CLI v2, 4 GB swap, the release bundles and .env from S3 into /opt/terascope, then
# deploy/aws/server_setup.sh from the unpacked app (venv, systemd units, nginx).
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
BUCKET="__BUCKET__"
REGION="__REGION__"
APP=/opt/terascope

apt-get update -y
apt-get install -y python3.12 python3.12-venv python3-pip nginx git curl unzip sqlite3

cd /tmp && curl -sS https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip && unzip -q -o awscliv2.zip \
  && ./aws/install --update && rm -rf /tmp/aws /tmp/awscliv2.zip
export AWS_DEFAULT_REGION="$REGION"

if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

mkdir -p "$APP" /var/tmp/terascope
aws s3 cp "s3://${BUCKET}/release/terascope-app.tar.gz"  /var/tmp/terascope/app.tar.gz  --only-show-errors
aws s3 cp "s3://${BUCKET}/release/terascope-data.tar.gz" /var/tmp/terascope/data.tar.gz --only-show-errors
tar -xzf /var/tmp/terascope/app.tar.gz  -C "$APP" --strip-components=1
tar -xzf /var/tmp/terascope/data.tar.gz -C "$APP"
aws s3 cp "s3://${BUCKET}/release/.env" "$APP/.env" --only-show-errors && chmod 600 "$APP/.env"
rm -f /var/tmp/terascope/app.tar.gz /var/tmp/terascope/data.tar.gz
chown -R ubuntu:ubuntu "$APP" /var/tmp/terascope

BUCKET="$BUCKET" REGION="$REGION" bash "$APP/deploy/aws/server_setup.sh"
echo "TERASCOPE_USER_DATA_DONE"
