#!/bin/bash
# Get Spaces access keys using doctl API token

set -e

CONFIG_FILE="$HOME/.config/doctl/config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ doctl config not found"
    exit 1
fi

# Extract API token from config (it's at the top level)
TOKEN=$(grep "^access-token:" "$CONFIG_FILE" | awk '{print $2}' | tr -d '"')

if [ -z "$TOKEN" ]; then
    echo "❌ Could not extract API token from doctl config"
    exit 1
fi

echo "Fetching Spaces access keys from DigitalOcean API..."
echo ""

# List Spaces keys via API
KEYS_JSON=$(curl -s -X GET \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    "https://api.digitalocean.com/v2/spaces_keys")

if echo "$KEYS_JSON" | grep -q "access_key"; then
    echo "Found Spaces keys:"
    echo ""
    echo "$KEYS_JSON" | python3 -m json.tool 2>/dev/null || echo "$KEYS_JSON"
    echo ""
    echo "⚠️  Note: Secret keys are only shown when first created."
    echo "   If you need new keys, create them at:"
    echo "   https://cloud.digitalocean.com/account/api/spaces"
else
    echo "Response: $KEYS_JSON"
    echo ""
    echo "If no keys found, create them at:"
    echo "  https://cloud.digitalocean.com/account/api/spaces"
fi
