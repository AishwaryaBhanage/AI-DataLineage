# DataLineage AI — AWS Deployment Guide

This guide takes you from local code to a running production API on AWS in about 1-2 hours.

## What we're deploying

- **AWS App Runner** — runs your container, auto-scales 1-25 instances
- **AWS ECR** — private Docker registry for your image
- **AWS Secrets Manager** — stores API keys safely
- **AWS CloudWatch** — collects logs

Estimated cost for a beta with 5 friends: **$5-15/month** (App Runner free tier covers most of it).

---

## Prerequisites

1. **AWS account** — sign up at aws.amazon.com if you don't have one
2. **AWS CLI** — `brew install awscli` then `aws configure`
3. **Docker Desktop** — running locally
4. **Anthropic API key** — fresh one (rotate if you suspect leakage)

---

## Step 1: Build and test the image locally

```bash
# Build it
docker build -t datalineage-ai:latest .

# Run it locally to verify
docker run --rm -p 8000:8000 \
  -e API_KEYS="dl_test_local_$(openssl rand -hex 8)" \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e CORS_ORIGINS="*" \
  -e ENVIRONMENT=development \
  datalineage-ai:latest

# In another terminal, smoke test
curl http://localhost:8000/api/v1/health
```

If you see `{"status":"ok",...}`, the image is good. **Stop the container before continuing.**

---

## Step 2: Create the ECR repository

ECR is AWS's private Docker registry. App Runner pulls images from here.

```bash
# Set your region
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create the repo
aws ecr create-repository \
  --repository-name datalineage-ai \
  --region $AWS_REGION \
  --image-scanning-configuration scanOnPush=true

# Authenticate Docker to ECR (token is valid for 12 hours)
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

---

## Step 3: Push the image

```bash
# Tag for ECR
docker tag datalineage-ai:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/datalineage-ai:latest

# Push (this takes 2-5 minutes for the first push, ~30s for incremental)
docker push \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/datalineage-ai:latest
```

---

## Step 4: Store secrets in AWS Secrets Manager

Never put your Anthropic key or API keys in environment variables in the AWS Console — anyone with read access to the App Runner config can see them. Use Secrets Manager instead.

```bash
# Generate beta tester keys
KEY1="dl_$(openssl rand -hex 12)"
KEY2="dl_$(openssl rand -hex 12)"
KEY3="dl_$(openssl rand -hex 12)"
KEY4="dl_$(openssl rand -hex 12)"
KEY5="dl_$(openssl rand -hex 12)"
echo "Friend 1: $KEY1"
echo "Friend 2: $KEY2"
echo "Friend 3: $KEY3"
echo "Friend 4: $KEY4"
echo "Friend 5: $KEY5"
echo ">>> SAVE THESE SOMEWHERE SAFE — you'll send them to your friends"

# Store all secrets in one Secrets Manager entry
aws secretsmanager create-secret \
  --name datalineage/prod \
  --secret-string "{
    \"ANTHROPIC_API_KEY\": \"$ANTHROPIC_API_KEY\",
    \"API_KEYS\": \"$KEY1,$KEY2,$KEY3,$KEY4,$KEY5\"
  }"
```

---

## Step 5: Create the IAM role for App Runner

App Runner needs permission to read from Secrets Manager and ECR.

```bash
# Trust policy that lets App Runner assume this role
cat > apprunner-trust-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "build.apprunner.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }, {
    "Effect": "Allow",
    "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

# Create the role
aws iam create-role \
  --role-name DataLineageAppRunnerRole \
  --assume-role-policy-document file://apprunner-trust-policy.json

# Attach AWS managed policies
aws iam attach-role-policy \
  --role-name DataLineageAppRunnerRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess

# Inline policy for Secrets Manager
cat > secrets-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["secretsmanager:GetSecretValue"],
    "Resource": "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT_ID:secret:datalineage/prod-*"
  }]
}
EOF

aws iam put-role-policy \
  --role-name DataLineageAppRunnerRole \
  --policy-name SecretsAccess \
  --policy-document file://secrets-policy.json
```

---

## Step 6: Create the App Runner service

This is the moment of truth.

```bash
# Get the role ARN
ROLE_ARN=$(aws iam get-role --role-name DataLineageAppRunnerRole \
  --query Role.Arn --output text)

# Get the secret ARN
SECRET_ARN=$(aws secretsmanager describe-secret \
  --secret-id datalineage/prod --query ARN --output text)

# Create the service config file
cat > apprunner-config.json <<EOF
{
  "ServiceName": "datalineage-ai",
  "SourceConfiguration": {
    "ImageRepository": {
      "ImageIdentifier": "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/datalineage-ai:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8000",
        "RuntimeEnvironmentVariables": {
          "ENVIRONMENT": "production",
          "LOG_LEVEL": "INFO",
          "REQUIRE_API_KEY": "true",
          "CORS_ORIGINS": "*",
          "RATE_LIMIT_FAST": "10/minute",
          "RATE_LIMIT_AGENTIC": "3/minute"
        },
        "RuntimeEnvironmentSecrets": {
          "ANTHROPIC_API_KEY": "$SECRET_ARN:ANTHROPIC_API_KEY::",
          "API_KEYS": "$SECRET_ARN:API_KEYS::"
        }
      },
      "AuthenticationConfiguration": {
        "AccessRoleArn": "$ROLE_ARN"
      }
    },
    "AutoDeploymentsEnabled": false
  },
  "InstanceConfiguration": {
    "Cpu": "1024",
    "Memory": "2048",
    "InstanceRoleArn": "$ROLE_ARN"
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP",
    "Path": "/api/v1/health",
    "Interval": 20,
    "Timeout": 10,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 3
  }
}
EOF

# Create the service
aws apprunner create-service --cli-input-json file://apprunner-config.json
```

App Runner will spend ~5 minutes provisioning, building, and starting your service. Watch progress in the AWS Console under App Runner → Services → datalineage-ai.

When it shows **"Running"**, get your URL:

```bash
aws apprunner list-services --query "ServiceSummaryList[?ServiceName=='datalineage-ai'].ServiceUrl" --output text
```

You'll get something like `https://abc123xyz.us-east-1.awsapprunner.com`.

---

## Step 7: Smoke test production

```bash
# Replace with your real URL and one of your API keys
export PROD_URL="https://abc123xyz.us-east-1.awsapprunner.com"
export PROD_KEY="dl_..."  # one of the keys from step 4

# Health check (no auth needed)
curl $PROD_URL/api/v1/health

# Models list (auth required)
curl -H "Authorization: Bearer $PROD_KEY" \
  "$PROD_URL/api/v1/models"

# Note: /debug needs a manifest file inside the container, so it'll work
# only with the bundled dbt_demo or with dbt Cloud source
```

---

## Step 8: Check the logs

```bash
# Get the log group name (created automatically by App Runner)
aws logs describe-log-groups --log-group-name-prefix /aws/apprunner/datalineage-ai

# Tail logs in real-time (replace with the actual log stream)
aws logs tail /aws/apprunner/datalineage-ai/<service-id>/application --follow
```

You'll see your structlog JSON output streaming through CloudWatch.

---

## Step 9: Send keys to your 5 friends

Email or DM template:

```
Hey! I built an AI debugger for dbt pipelines and want your honest feedback.

API URL: https://abc123xyz.us-east-1.awsapprunner.com
Your API key: dl_xxxxxxxxxxxxxx (don't share)
Docs: https://abc123xyz.us-east-1.awsapprunner.com/docs

Quick test:
  curl https://abc123xyz.us-east-1.awsapprunner.com/api/v1/health

Try the debug endpoint:
  curl -X POST https://abc123xyz.us-east-1.awsapprunner.com/api/v1/debug \
    -H "Authorization: Bearer dl_xxxxxxxxxxxxxx" \
    -H "Content-Type: application/json" \
    -d '{
      "source": "local",
      "manifest_path": "dbt_demo/target/manifest.json",
      "run_results_path": "dbt_demo/target/run_results.json",
      "mode": "fast"
    }'

What I want to know:
  1. Did anything break or feel slow?
  2. Was the diagnosis useful?
  3. What would you want it to do that it doesn't?

Thanks!
```

---

## Updating the service later

When you make code changes:

```bash
# Rebuild and push
docker build -t datalineage-ai:latest .
docker tag datalineage-ai:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/datalineage-ai:latest
docker push \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/datalineage-ai:latest

# Trigger a new deployment
aws apprunner start-deployment \
  --service-arn $(aws apprunner list-services \
    --query "ServiceSummaryList[?ServiceName=='datalineage-ai'].ServiceArn" \
    --output text)
```

---

## Common problems

**Build fails with "no space left on device"**
Run `docker system prune -af` to clean up old images.

**App Runner shows "CREATE_FAILED"**
Check the deployment logs in the App Runner console. Usually means:
- ECR image isn't there yet (push first)
- IAM role missing permissions
- Health check failing (test `/api/v1/health` locally first)

**Requests time out**
Default App Runner timeout is 120s. Agentic mode can take 30s — that's fine. If you see >120s, raise the issue or switch to async jobs (Phase 3).

**Anthropic API key not working in prod**
Verify the secret is in the right format:
```bash
aws secretsmanager get-secret-value --secret-id datalineage/prod \
  --query SecretString --output text
```

---

## Cost estimates

App Runner pricing (us-east-1):
- **Provisioned compute**: $0.064/vCPU-hour, $0.007/GB-hour while idle
- **Active compute**: $0.064/vCPU-hour, $0.007/GB-hour while serving
- **Free tier**: 50 hours/month (lifetime, not monthly free tier)

For your beta (5 friends, ~50 requests/day total):
- 1 vCPU + 2 GB instance, mostly idle: **~$10-15/month**
- ECR storage: **~$0.10/month** (your image is ~300MB)
- Secrets Manager: **$0.40/month per secret**
- CloudWatch logs: **~$0.50/month** at low volume

**Total: ~$15-20/month** for the beta. If usage spikes, App Runner auto-scales but you pay per second so a quiet day is essentially free.

---

## Next steps after beta

When you have feedback and want to improve:
1. Add a real database (RDS Postgres) for job history
2. Move agentic mode to async jobs via SQS
3. Add custom domain via Route 53 + ACM cert
4. Add WAF for DDoS protection
5. Wire up GitHub Actions for CI/CD
