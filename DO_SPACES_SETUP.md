# DigitalOcean Spaces Setup Guide

## Quick Setup Steps

1. **Create a Spaces Bucket:**
   - Go to [DigitalOcean Control Panel](https://cloud.digitalocean.com/spaces)
   - Click "Create a Spaces Bucket"
   - Choose a name (e.g., `sailarchive-dev` or `sailarchive-tracks`)
   - Select a region (e.g., `sfo3` for San Francisco)
   - Choose "File Listing: Private" (we use signed URLs for tracks)
   - Click "Create a Spaces Bucket"

2. **Create Spaces Access Keys:**
   - Go to [API → Spaces Keys](https://cloud.digitalocean.com/account/api/spaces)
   - Click "Generate New Key"
   - Give it a name (e.g., "sailarchive-dev")
   - Copy the **Access Key** and **Secret Key** (you'll only see the secret once!)

3. **Add to your `.env` file:**
   ```bash
   DO_SPACES_KEY=your-access-key-here
   DO_SPACES_SECRET=your-secret-key-here
   DO_SPACES_NAME=your-bucket-name
   DO_SPACES_ENDPOINT=https://sfo3.digitaloceanspaces.com
   DO_SPACES_REGION=sfo3
   ```

4. **Restart your containers:**
   ```bash
   docker compose down
   docker compose up -d
   ```

## Bucket Structure

The app will create the following structure in your Spaces bucket:

```
your-bucket-name/
├── media/                    # Vessel icons and other media (public-read)
│   └── vessel_icons/
└── tracks/                   # Track JSON files (private, signed URLs)
    └── {recording-id}/
        ├── raw.json
        ├── z6.json
        ├── z10.json
        ├── z14.json
        └── z18.json
```

## Testing Without DO Spaces

If you don't want to set up DO Spaces for local development, the app will:
- ✅ Still process GPX files
- ✅ Store metadata in the database
- ❌ But fail when trying to upload track files to S3

To test the full pipeline, you'll need DO Spaces configured.

## Cost Estimate

- **Spaces Storage:** $5/month for 250GB
- **Bandwidth:** $0.01/GB (first 1TB free per month)
- **Estimated monthly cost for testing:** ~$5-10
