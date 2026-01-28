#!/bin/bash
# Configure CORS on DigitalOcean Spaces bucket

set -e

BUCKET_NAME=${1:-damon-testbucket}
REGION=${2:-sfo3}
ENDPOINT="https://${REGION}.digitaloceanspaces.com"

echo "Configuring CORS for Spaces bucket: $BUCKET_NAME"
echo ""

# Check for credentials
if [ -z "$DO_SPACES_KEY" ] || [ -z "$DO_SPACES_SECRET" ]; then
    echo "❌ DO_SPACES_KEY and DO_SPACES_SECRET must be set"
    echo ""
    echo "Export them or source from APPCONFIG.env:"
    echo "  source APPCONFIG.env"
    exit 1
fi

# Create CORS configuration JSON
CORS_CONFIG=$(cat <<EOF
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag", "Content-Length"],
      "MaxAgeSeconds": 3600
    }
  ]
}
EOF
)

echo "CORS Configuration:"
echo "$CORS_CONFIG" | python3 -m json.tool
echo ""

# Configure CORS using boto3
python3 <<PYTHON_SCRIPT
import boto3
import json
import sys
import os

bucket_name = "$BUCKET_NAME"
region = "$REGION"
endpoint = "$ENDPOINT"
access_key = os.getenv('DO_SPACES_KEY')
secret_key = os.getenv('DO_SPACES_SECRET')

if not access_key or not secret_key:
    print("❌ DO_SPACES_KEY and DO_SPACES_SECRET must be set")
    sys.exit(1)

cors_config = {
    "CORSRules": [
        {
            "AllowedOrigins": ["*"],
            "AllowedMethods": ["GET", "HEAD"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag", "Content-Length"],
            "MaxAgeSeconds": 3600
        }
    ]
}

try:
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )
    
    s3.put_bucket_cors(
        Bucket=bucket_name,
        CORSConfiguration=cors_config
    )
    
    print("✅ CORS configured successfully!")
    print("")
    print("The bucket now allows cross-origin requests from any origin.")
    print("For production, you may want to restrict AllowedOrigins to your domain.")
    
except Exception as e:
    print(f"❌ Error configuring CORS: {e}")
    sys.exit(1)
PYTHON_SCRIPT
