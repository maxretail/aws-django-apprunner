#!/bin/bash
set -e

# Require APP_NAME environment variable
if [ -z "$APP_NAME" ]; then
    echo "Error: APP_NAME environment variable is required"
    exit 1
fi

REPO_NAME=${APP_NAME}
STACK_NAME="${REPO_NAME}Stack"
TIMESTAMP=$(date +%Y%m%d%H%M%S)

# Setup ECR repository
echo "Setting up ECR repository..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

# Check if repository exists, create if it doesn't
aws ecr describe-repositories --repository-names ${REPO_NAME} > /dev/null 2>&1 || \
    aws ecr create-repository --repository-name ${REPO_NAME} --image-scanning-configuration scanOnPush=true > /dev/null 2>&1
echo "Using ECR repository: $ECR_REPO"

# Login to ECR
echo "Logging in to ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPO}

# Build the Docker image for AMD64
echo "Building Docker image..."
docker build --platform linux/amd64 -t ${REPO_NAME}:latest .

# Tag the image with both latest and timestamp
echo "Tagging images..."
docker tag ${REPO_NAME}:latest ${ECR_REPO}:latest
docker tag ${REPO_NAME}:latest ${ECR_REPO}:${TIMESTAMP}

# Push both tags to ECR
echo "Pushing images to ECR..."
docker push ${ECR_REPO}:latest
docker push ${ECR_REPO}:${TIMESTAMP}

# Now deploy the full stack with the timestamped image
echo "Deploying stack ${STACK_NAME}..."
cd cdk
APP_NAME=${REPO_NAME} IMAGE_TAG=${TIMESTAMP} cdk deploy ${STACK_NAME} \
  --require-approval never \
  --outputs-file ../cdk-outputs.json \
  --progress events

echo "Deployment complete! The new image has been pushed to ${ECR_REPO} with tag ${TIMESTAMP}" 