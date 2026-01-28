#!/usr/bin/env python3
"""
Set up DigitalOcean Spaces bucket and test connection.
This script helps you create a bucket and generate access keys.
"""

import sys
import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

def main():
    bucket_name = sys.argv[1] if len(sys.argv) > 1 else "sailarchive-dev"
    region = sys.argv[2] if len(sys.argv) > 2 else "sfo3"
    endpoint = f"https://{region}.digitaloceanspaces.com"
    
    print("=" * 50)
    print("DigitalOcean Spaces Setup")
    print("=" * 50)
    print(f"Bucket: {bucket_name}")
    print(f"Region: {region}")
    print(f"Endpoint: {endpoint}")
    print()
    
    # Check for credentials
    key = os.getenv('DO_SPACES_KEY')
    secret = os.getenv('DO_SPACES_SECRET')
    
    if not key or not secret:
        print("❌ DO_SPACES_KEY and DO_SPACES_SECRET not set")
        print()
        print("To set up Spaces:")
        print("1. Create a bucket: https://cloud.digitalocean.com/spaces")
        print("2. Create access keys: https://cloud.digitalocean.com/account/api/spaces")
        print("3. Add to your .env file:")
        print()
        print(f"   DO_SPACES_KEY=your-access-key")
        print(f"   DO_SPACES_SECRET=your-secret-key")
        print(f"   DO_SPACES_NAME={bucket_name}")
        print(f"   DO_SPACES_ENDPOINT={endpoint}")
        print(f"   DO_SPACES_REGION={region}")
        print()
        return 1
    
    try:
        # Create S3 client
        s3 = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=key,
            aws_secret_access_key=secret,
            region_name=region
        )
        
        # Check if bucket exists
        try:
            s3.head_bucket(Bucket=bucket_name)
            print(f"✓ Bucket '{bucket_name}' exists")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket doesn't exist, try to create it
                print(f"Creating bucket '{bucket_name}'...")
                try:
                    # Note: DO Spaces requires location constraint
                    s3.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={'LocationConstraint': region}
                    )
                    print(f"✓ Bucket '{bucket_name}' created successfully")
                except ClientError as create_error:
                    print(f"⚠️  Could not create bucket: {create_error}")
                    print("   You may need to create it via web interface:")
                    print("   https://cloud.digitalocean.com/spaces")
                    return 1
            else:
                print(f"❌ Error accessing bucket: {e}")
                return 1
        
        # Test upload/download
        print("Testing upload...")
        test_key = "test-connection.txt"
        test_content = b"test connection"
        
        s3.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_content,
            ContentType='text/plain'
        )
        print("✓ Upload successful")
        
        # Test download
        response = s3.get_object(Bucket=bucket_name, Key=test_key)
        if response['Body'].read() == test_content:
            print("✓ Download successful")
        
        # Cleanup
        s3.delete_object(Bucket=bucket_name, Key=test_key)
        print("✓ Cleanup successful")
        
        print()
        print("=" * 50)
        print("✅ Spaces is configured correctly!")
        print("=" * 50)
        print()
        print("Your .env should have:")
        print(f"DO_SPACES_KEY={key}")
        print(f"DO_SPACES_SECRET={secret}")
        print(f"DO_SPACES_NAME={bucket_name}")
        print(f"DO_SPACES_ENDPOINT={endpoint}")
        print(f"DO_SPACES_REGION={region}")
        print()
        
        return 0
        
    except NoCredentialsError:
        print("❌ Invalid credentials")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
