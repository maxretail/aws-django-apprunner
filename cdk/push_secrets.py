#!/usr/bin/env python3
import argparse
import os
import sys
import boto3
import re
from botocore.exceptions import NoCredentialsError, ClientError
from secrets_manager import SecretManager, DEFAULT_SECRETS_DIR, PROJECT_ROOT

def get_app_name_from_appconfig():
    """
    Read APP_NAME from APPCONFIG.env file.
    
    Returns:
        The APP_NAME value or None if not found
    """
    appconfig_path = os.path.join(PROJECT_ROOT, "APPCONFIG.env")
    if not os.path.exists(appconfig_path):
        return None
        
    try:
        with open(appconfig_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    match = re.match(r'^APP_NAME=(.+)$', line)
                    if match:
                        return match.group(1)
    except Exception as e:
        print(f"Error reading APPCONFIG.env: {str(e)}")
    
    return None

def main():
    """
    CLI tool to push secrets from local files to AWS Secrets Manager.
    This should be run locally before deployment with proper AWS credentials configured.
    
    Each file in the secrets directory is pushed as a separate AWS secret,
    with each line in the file treated as a key=value pair.
    """
    # Get default app name from APPCONFIG.env
    default_app_name = get_app_name_from_appconfig()
    
    parser = argparse.ArgumentParser(description='Push secrets to AWS Secrets Manager')
    parser.add_argument('--app-name', 
                        required=not bool(default_app_name),  # Only required if not found in APPCONFIG.env
                        default=default_app_name,
                        help=f'Application name (default: {default_app_name} from APPCONFIG.env)')
    parser.add_argument('--secrets-dir', default=DEFAULT_SECRETS_DIR, 
                       help=f'Directory containing secret files (default: {DEFAULT_SECRETS_DIR})')
    parser.add_argument('--region', help='AWS region (default: use AWS CLI configured region)')
    parser.add_argument('--dry-run', action='store_true', help='Validate secrets without pushing to AWS')
    args = parser.parse_args()
    
    if not args.app_name:
        print("Error: --app-name is required and APP_NAME not found in APPCONFIG.env")
        sys.exit(1)
        
    print(f"Pushing secrets for app '{args.app_name}' from directory '{args.secrets_dir}'...")
    
    # Skip AWS credential check in dry-run mode
    if not args.dry_run:
        # Verify AWS credentials are available
        try:
            # Quick check to see if AWS credentials are configured
            sts = boto3.client('sts')
            sts.get_caller_identity()
        except NoCredentialsError:
            print("ERROR: AWS credentials not found.")
            print("Please configure your AWS credentials using:")
            print("  aws configure")
            print("Or set environment variables:")
            print("  export AWS_ACCESS_KEY_ID=your_access_key")
            print("  export AWS_SECRET_ACCESS_KEY=your_secret_key")
            print("  export AWS_DEFAULT_REGION=your_region")
            sys.exit(1)
        except ClientError as e:
            print(f"ERROR: AWS credentials issue: {str(e)}")
            sys.exit(1)
    
    # Ensure the secrets directory exists
    if not os.path.exists(args.secrets_dir):
        os.makedirs(args.secrets_dir)
        print(f"Created directory {args.secrets_dir}")
        print(f"Add secret files with key=value format:")
        print(f"Example - {args.secrets_dir}/database:")
        print(f"DB_USER=admin")
        print(f"DB_PASSWORD=securepassword")
        return
    
    # Make sure there are some secret files to push
    secret_files = [f for f in os.listdir(args.secrets_dir) 
                   if os.path.isfile(os.path.join(args.secrets_dir, f)) and not f.startswith('.')]
    
    if not secret_files:
        print(f"No secret files found in {args.secrets_dir}")
        print("Create files with key=value pairs on each line")
        return
    
    print(f"Found {len(secret_files)} secret file(s): {', '.join(secret_files)}")
    
    # Process each secret file to validate and show content in dry-run mode
    if args.dry_run:
        print("\nDRY RUN MODE - Validating secrets without pushing to AWS")
        for filename in secret_files:
            file_path = os.path.join(args.secrets_dir, filename)
            secret_values = {}
            
            # Read key-value pairs from the file
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            secret_values[key.strip()] = value.strip()
                        else:
                            print(f"  WARNING: Line {line_num} in {filename} does not contain '=' delimiter")
            
            # Create the descriptive name for the secret in AWS
            secret_name = f"{args.app_name}_{os.path.splitext(filename)[0]}"
            
            if secret_values:
                print(f"\n  Secret: {secret_name}")
                print(f"  File: {filename}")
                print(f"  Keys: {', '.join(secret_values.keys())}")
                print(f"  Would create/update AWS secret with {len(secret_values)} key-value pairs")
            else:
                print(f"\n  Warning: {filename} contains no valid key-value pairs")
        
        print("\nDry run completed. No changes were made to AWS.")
        return
    
    # Push secrets to AWS
    secret_arns = SecretManager.push_secrets_to_aws(args.app_name, args.secrets_dir, args.region)
    
    if secret_arns:
        print(f"\nSuccessfully pushed {len(secret_arns)} secret(s) to AWS Secrets Manager:")
        for secret_name, arn in secret_arns.items():
            print(f"  - {secret_name}: {arn}")
        print("\nThese secrets will be accessible during deployment.")
    else:
        print("No secrets were pushed to AWS Secrets Manager.")
        print("Check your files format and AWS credentials.")

if __name__ == "__main__":
    main() 