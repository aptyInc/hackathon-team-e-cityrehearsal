#!/usr/bin/env bash
# Terascope AI demo on AWS, step 1: the private S3 bucket and the EC2 role (idempotent: re-running is harmless).
# Usage: AWS_PROFILE=terascope bash deploy/aws/01_bucket_and_role.sh
set -euo pipefail
export AWS_PAGER=""
REGION="${AWS_REGION:-ap-southeast-2}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="terascope-demo-${ACCOUNT}"
ROLE="terascope-ec2-role"
TAG="Key=Project,Value=terascope-demo"

echo "== S3 bucket s3://${BUCKET} (${REGION})"
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration "LocationConstraint=${REGION}" --output text --query Location
fi
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging "TagSet=[{${TAG}}]"
echo "bucket ok"

echo "== IAM role ${ROLE} + instance profile"
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document "$TRUST" --tags "$TAG" \
    --query Role.Arn --output text
fi
aws iam attach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
cat > /tmp/terascope-s3-policy.json <<EOF
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::${BUCKET}"},
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject"],"Resource":"arn:aws:s3:::${BUCKET}/*"}]}
EOF
aws iam put-role-policy --role-name "$ROLE" --policy-name terascope-s3-bucket --policy-document file:///tmp/terascope-s3-policy.json
if ! aws iam get-instance-profile --instance-profile-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$ROLE" --tags "$TAG" --query InstanceProfile.Arn --output text
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
fi
aws iam get-role --role-name "$ROLE" --query Role.Arn --output text
aws iam get-instance-profile --instance-profile-name "$ROLE" --query InstanceProfile.Arn --output text
echo "iam ok"
