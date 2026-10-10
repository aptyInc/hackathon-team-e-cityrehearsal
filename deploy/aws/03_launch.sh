#!/usr/bin/env bash
# Terascope AI demo on AWS, step 3: security group (80/443 in, no SSH), one Ubuntu 24.04 instance with the role and
# the user-data, an Elastic IP. Falls back through TYPES when a type is unavailable or a quota blocks it.
# Usage: AWS_PROFILE=terascope bash deploy/aws/03_launch.sh        (prints the instance id and the public IP)
set -euo pipefail
export AWS_PAGER=""
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${OUT:-${TMPDIR:-/tmp}/terascope-release}"; mkdir -p "$OUT"
REGION="${AWS_REGION:-ap-southeast-2}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="terascope-demo-${ACCOUNT}"
TYPES="${TYPES:-c7i.2xlarge c6i.2xlarge m6i.2xlarge c6a.2xlarge t3.2xlarge c7i.xlarge c6i.xlarge m6i.xlarge t3.xlarge}"
DISK_GB="${DISK_GB:-60}"

AMI="$(aws ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
       --query Parameter.Value --output text)"
VPC="$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)"
SUBNET="$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC}" Name=default-for-az,Values=true \
          --query 'Subnets[0].SubnetId' --output text)"
echo "ami=${AMI} vpc=${VPC} subnet=${SUBNET}"

echo "== security group terascope-web"
SG="$(aws ec2 describe-security-groups --filters Name=group-name,Values=terascope-web "Name=vpc-id,Values=${VPC}" \
      --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"
if [ -z "$SG" ] || [ "$SG" = "None" ]; then
  SG="$(aws ec2 create-security-group --group-name terascope-web --vpc-id "$VPC" \
        --description "Terascope demo: HTTP and HTTPS from anywhere, no SSH (Session Manager only)" \
        --tag-specifications 'ResourceType=security-group,Tags=[{Key=Project,Value=terascope-demo}]' \
        --query GroupId --output text)"
  aws ec2 authorize-security-group-ingress --group-id "$SG" --ip-permissions \
    'IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0,Description=http}]' \
    'IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0,Description=https}]' >/dev/null
fi
echo "sg=${SG}"

sed -e "s/__BUCKET__/${BUCKET}/" -e "s/__REGION__/${REGION}/" "$HERE/deploy/aws/user-data.sh" > "$OUT/user-data.sh"

echo "== instance"
ID=""
for t in $TYPES; do
  if ID="$(aws ec2 run-instances --image-id "$AMI" --instance-type "$t" --subnet-id "$SUBNET" --security-group-ids "$SG" \
        --iam-instance-profile Name=terascope-ec2-role --user-data "file://${OUT}/user-data.sh" \
        --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2 \
        --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=${DISK_GB},VolumeType=gp3,DeleteOnTermination=true,Encrypted=true}" \
        --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=terascope-demo},{Key=Project,Value=terascope-demo}]' \
                             'ResourceType=volume,Tags=[{Key=Project,Value=terascope-demo}]' \
        --query 'Instances[0].InstanceId' --output text 2>"$OUT/launch.err")"; then
    echo "launched ${ID} as ${t}"; break
  else
    echo "${t}: $(tr -d '\n' < "$OUT/launch.err" | cut -c1-160)"; ID=""
  fi
done
[ -n "$ID" ] || { echo "no instance type could be launched"; exit 1; }

echo "== elastic ip"
aws ec2 wait instance-running --instance-ids "$ID"
ALLOC="$(aws ec2 describe-addresses --filters Name=tag:Project,Values=terascope-demo \
         --query 'Addresses[?AssociationId==null].AllocationId | [0]' --output text 2>/dev/null || true)"
if [ -z "$ALLOC" ] || [ "$ALLOC" = "None" ]; then
  ALLOC="$(aws ec2 allocate-address --domain vpc \
           --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Project,Value=terascope-demo}]' \
           --query AllocationId --output text)"
fi
aws ec2 associate-address --instance-id "$ID" --allocation-id "$ALLOC" >/dev/null
IP="$(aws ec2 describe-addresses --allocation-ids "$ALLOC" --query 'Addresses[0].PublicIp' --output text)"
printf 'instance=%s\nallocation=%s\nsg=%s\nip=%s\nurl=http://%s/\n' "$ID" "$ALLOC" "$SG" "$IP" "$IP" | tee "$OUT/instance.txt"
