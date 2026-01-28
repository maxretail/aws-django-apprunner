#!/usr/bin/env python3
"""
List DigitalOcean Spaces buckets using the DO API and/or S3 API.
"""

import sys
import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

def list_spaces_via_s3(access_key, secret_key, region='sfo3'):
    """List Spaces buckets using S3-compatible API."""
    endpoint = f"https://{region}.digitaloceanspaces.com"
    
    try:
        s3 = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        # List all buckets
        response = s3.list_buckets()
        return response.get('Buckets', [])
    except (NoCredentialsError, ClientError) as e:
        return None

def main():
    print("=" * 60)
    print("DigitalOcean Spaces - List Buckets")
    print("=" * 60)
    print()
    
    # Try to get credentials from environment
    access_key = os.getenv('DO_SPACES_KEY')
    secret_key = os.getenv('DO_SPACES_SECRET')
    region = os.getenv('DO_SPACES_REGION', 'sfo3')
    
    # Try S3 API if credentials are available
    if access_key and secret_key:
        print("Using S3-compatible API to list buckets...")
        print()
        s3_buckets = list_spaces_via_s3(access_key, secret_key, region)
        if s3_buckets:
            print(f"Found {len(s3_buckets)} bucket(s):")
            print()
            for bucket in s3_buckets:
                print(f"  • {bucket['Name']}")
                if 'CreationDate' in bucket:
                    print(f"    Created: {bucket['CreationDate']}")
            print()
            return 0
        else:
            print("⚠️  No buckets found or error accessing Spaces")
            print()
    
    # If neither worked, provide instructions
    print("❌ Could not list Spaces buckets")
    print()
    print("To list your Spaces, you need either:")
    print()
    print("1. Set DO_SPACES_KEY and DO_SPACES_SECRET in your environment:")
    print("   export DO_SPACES_KEY=your-key")
    print("   export DO_SPACES_SECRET=your-secret")
    print()
    print("2. Or add them to your .env file and source it")
    print()
    print("3. Then run this script again")
    print()
    print("Alternatively, view your Spaces in the web interface:")
    print("  https://cloud.digitalocean.com/spaces")
    print()
    
    return 1

if __name__ == '__main__':
    sys.exit(main())
