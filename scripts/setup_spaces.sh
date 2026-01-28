#!/bin/bash
# Script to help set up DigitalOcean Spaces bucket

set -e

BUCKET_NAME=${1:-sailarchive-dev}
REGION=${2:-sfo3}

echo "=========================================="
echo "DigitalOcean Spaces Setup"
echo "=========================================="
echo ""
echo "Bucket name: $BUCKET_NAME"
echo "Region: $REGION"
echo ""

# Check if doctl is authenticated
if ! doctl auth list &>/dev/null; then
    echo "❌ doctl is not authenticated."
    echo ""
    echo "Please authenticate first:"
    echo "  doctl auth init"
    echo ""
    echo "This will prompt you for a DigitalOcean API token."
    echo "Get one from: https://cloud.digitalocean.com/account/api/tokens"
    exit 1
fi

echo "✓ doctl is authenticated"
echo ""

# Get API token from doctl config file
CONFIG_FILE="$HOME/.config/doctl/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    API_TOKEN=$(grep -A 5 "default:" "$CONFIG_FILE" | grep "access-token:" | awk '{print $2}' | head -1)
fi

if [ -z "$API_TOKEN" ]; then
    echo "⚠️  Could not retrieve API token from doctl config"
    echo "   You'll need to create the bucket and keys manually"
    MANUAL_SETUP=true
else
    echo "✓ API token retrieved"
    echo ""
    MANUAL_SETUP=false
fi

if [ "$MANUAL_SETUP" = true ]; then
    echo ""
    echo "=========================================="
    echo "Manual Setup Required"
    echo "=========================================="
    echo ""
    echo "1. Create Spaces bucket:"
    echo "   https://cloud.digitalocean.com/spaces"
    echo "   - Name: $BUCKET_NAME"
    echo "   - Region: $REGION"
    echo "   - File listing: Private"
    echo ""
    echo "2. Create Spaces access keys:"
    echo "   https://cloud.digitalocean.com/account/api/spaces"
    echo "   - Click 'Generate New Key'"
    echo "   - Name: sailarchive-dev"
    echo ""
    echo "3. Update your .env file with the keys"
    echo ""
    exit 0
fi

# Create Spaces access keys via API
echo "Creating Spaces access keys..."
KEY_NAME="sailarchive-$(date +%s)"
KEY_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"$KEY_NAME\"}" \
    "https://api.digitalocean.com/v2/spaces_keys" 2>/dev/null)

ACCESS_KEY=$(echo "$KEY_RESPONSE" | grep -o '"access_key":"[^"]*' | cut -d'"' -f4 || echo "")
SECRET_KEY=$(echo "$KEY_RESPONSE" | grep -o '"secret_key":"[^"]*' | cut -d'"' -f4 || echo "")

# If API doesn't work, try getting from existing keys
if [ -z "$ACCESS_KEY" ]; then
    echo "⚠️  Could not create keys via API. Listing existing keys..."
    EXISTING_KEYS=$(curl -s -X GET \
        -H "Authorization: Bearer $API_TOKEN" \
        "https://api.digitalocean.com/v2/spaces_keys" 2>/dev/null)
    
    if echo "$EXISTING_KEYS" | grep -q "access_key"; then
        echo "✓ Found existing keys (use one of these or create new via web interface)"
    fi
fi

if [ -n "$ACCESS_KEY" ] && [ -n "$SECRET_KEY" ]; then
    echo "✓ Spaces keys created"
    echo ""
    echo "⚠️  IMPORTANT: Save these keys now (secret key won't be shown again):"
    echo ""
    echo "DO_SPACES_KEY=$ACCESS_KEY"
    echo "DO_SPACES_SECRET=$SECRET_KEY"
    echo "DO_SPACES_NAME=$BUCKET_NAME"
    echo "DO_SPACES_ENDPOINT=https://$REGION.digitaloceanspaces.com"
    echo "DO_SPACES_REGION=$REGION"
    echo ""
    
    # Update .env file if it exists
    if [ -f .env ]; then
        read -p "Update .env file with these values? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Remove old DO_SPACES lines
            sed -i '/^DO_SPACES/d' .env
            
            # Add new values
            echo "" >> .env
            echo "# DigitalOcean Spaces" >> .env
            echo "DO_SPACES_KEY=$ACCESS_KEY" >> .env
            echo "DO_SPACES_SECRET=$SECRET_KEY" >> .env
            echo "DO_SPACES_NAME=$BUCKET_NAME" >> .env
            echo "DO_SPACES_ENDPOINT=https://$REGION.digitaloceanspaces.com" >> .env
            echo "DO_SPACES_REGION=$REGION" >> .env
            echo ""
            echo "✓ .env file updated"
        fi
    fi
else
    echo "⚠️  Could not create keys via API. Please create them manually:"
    echo "   https://cloud.digitalocean.com/account/api/spaces"
    echo ""
    echo "Then update your .env file with:"
    echo "DO_SPACES_KEY=your-access-key"
    echo "DO_SPACES_SECRET=your-secret-key"
    echo "DO_SPACES_NAME=$BUCKET_NAME"
    echo "DO_SPACES_ENDPOINT=https://$REGION.digitaloceanspaces.com"
    echo "DO_SPACES_REGION=$REGION"
fi

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Restart your containers: docker compose restart app"
echo "2. Test by uploading a GPX file"
echo ""
