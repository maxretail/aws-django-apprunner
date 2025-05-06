#!/bin/bash
set -e

# Require APP_NAME environment variable
if [ -z "$APP_NAME" ]; then
    echo "Error: APP_NAME environment variable is required"
    exit 1
fi

# Require AWS_REGION environment variable
if [ -z "$AWS_REGION" ]; then
    echo "Error: AWS_REGION environment variable is required"
    exit 1
fi

# Set verbose logging if debug is enabled
if [ "$CDK_DEBUG" = "true" ]; then
    set -x  # Enable command echo
    export PYTHONVERBOSE=1
fi

REPO_NAME=${APP_NAME}
STACK_NAME="${REPO_NAME}Stack"
TIMESTAMP=$(date +%Y%m%d%H%M%S)

# Setup ECR repository
echo "Setting up ECR repository..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

echo "Checking ECR repository status..."
# Check if repository exists
if ! aws ecr describe-repositories --repository-names ${REPO_NAME} --region ${AWS_REGION} > /dev/null 2>&1; then
    echo "Creating ECR repository ${REPO_NAME}..."
    aws ecr create-repository \
        --repository-name ${REPO_NAME} \
        --image-scanning-configuration scanOnPush=true \
        --region ${AWS_REGION}
    
    if [ $? -ne 0 ]; then
        echo "Failed to create ECR repository"
        exit 1
    fi
    echo "ECR repository created successfully"
else
    echo "ECR repository already exists"
fi

# Verify repository exists
echo "Verifying ECR repository..."
if ! aws ecr describe-repositories --repository-names ${REPO_NAME} --region ${AWS_REGION} > /dev/null 2>&1; then
    echo "Error: ECR repository verification failed"
    exit 1
fi

echo "Using ECR repository: $ECR_REPO"

# Login to ECR
echo "Logging in to ECR..."
if ! aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPO}; then
    echo "Error: Failed to login to ECR"
    exit 1
fi

# Build the Docker image for AMD64
echo "Building Docker image..."
if ! docker build --platform linux/amd64 -t ${REPO_NAME}:latest .; then
    echo "Error: Docker build failed"
    exit 1
fi

# Tag the image with both latest and timestamp
echo "Tagging images..."
if ! docker tag ${REPO_NAME}:latest ${ECR_REPO}:latest; then
    echo "Error: Failed to tag image as latest"
    exit 1
fi
if ! docker tag ${REPO_NAME}:latest ${ECR_REPO}:${TIMESTAMP}; then
    echo "Error: Failed to tag image with timestamp"
    exit 1
fi

# Push both tags to ECR
echo "Pushing images to ECR..."
if ! docker push ${ECR_REPO}:latest; then
    echo "Error: Failed to push latest image"
    exit 1
fi
if ! docker push ${ECR_REPO}:${TIMESTAMP}; then
    echo "Error: Failed to push timestamped image"
    exit 1
fi

# Verify AWS Secrets Manager access before deployment
echo "Verifying secrets access before deployment..."
SECRETS_PATTERN="${APP_NAME}_"
echo "Looking for secrets matching pattern: $SECRETS_PATTERN"

SECRETS=$(aws secretsmanager list-secrets --filters Key=name,Values="$SECRETS_PATTERN" --query "SecretList[].Name" --output text)
if [ -z "$SECRETS" ]; then
    echo "⚠️ WARNING: No secrets found matching pattern $SECRETS_PATTERN"
    echo "Make sure you have pushed secrets using the push_secrets.py script."
    echo "Continuing with deployment, but your application may not have required secrets."
else
    echo "✅ Found the following secrets that will be available to the application:"
    for SECRET in $SECRETS; do
        # Get secret keys without exposing values
        SECRET_KEYS=$(aws secretsmanager get-secret-value --secret-id "$SECRET" --query "SecretString" --output text | jq -r 'keys | join(", ")')
        echo "  - $SECRET (Keys: $SECRET_KEYS)"
    done
fi

# Now deploy the full stack with the timestamped image
echo "Deploying stack ${STACK_NAME}..."
cd cdk
if ! APP_NAME=${REPO_NAME} IMAGE_TAG=${TIMESTAMP} cdk deploy ${STACK_NAME} \
  --require-approval never \
  --outputs-file ../cdk-outputs.json \
  --progress events \
  --verbose; then
    echo "Error: CDK deployment failed"
    exit 1
fi

# After deployment, verify the environment variables that will be available
echo "Deployment successful! Checking environment variables configuration..."
# List environment variables that were configured (not values, just names)
ENV_VARS=$(aws apprunner describe-service --service-arn $(cat ../cdk-outputs.json | jq -r '."'${STACK_NAME}'".AppRunnerServiceArn') --query "Service.SourceConfiguration.ImageConfiguration.RuntimeEnvironmentVariables[*].Name" --output text 2>/dev/null || echo "Unable to retrieve environment variables")

if [ -n "$ENV_VARS" ]; then
    echo "✅ The following environment variables are configured in App Runner:"
    for VAR in $ENV_VARS; do
        echo "  - $VAR"
    done
else
    echo "⚠️ Unable to retrieve environment variables configuration."
fi

echo "Deployment complete! The new image has been pushed to ${ECR_REPO} with tag ${TIMESTAMP}" 