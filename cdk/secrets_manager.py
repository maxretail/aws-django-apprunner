import os
import json
import glob
import boto3
import logging
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_apprunner as apprunner,
)
from constructs import Construct

# Set up logging back to INFO level
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('SecretManager')

# Constants
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_SECRETS_DIR = os.path.join(PROJECT_ROOT, ".secrets")

def mask_secret_value(value):
    """
    Mask a secret value to show only first and last character.
    
    Args:
        value: The secret value to mask
    
    Returns:
        Masked value like: f***t (for 'first')
    """
    if not value or len(value) <= 2:
        return "***"
    return f"{value[0]}****{value[-1]}"

class SecretManager:
    """
    Manages secrets for the application. Secrets are loaded from local files
    during development and stored in AWS Secrets Manager for production.
    
    Local secrets should be stored in a '.secrets' directory that is
    added to .gitignore to prevent accidentally committing them.
    
    Each file in the .secrets directory is treated as a separate secret with key=value pairs
    and will be pushed to AWS Secrets Manager as a separate secret.
    """
    
    def __init__(self, scope: Construct, app_name: str, secrets_dir: str = DEFAULT_SECRETS_DIR):
        """
        Initialize the secret manager.
        
        Args:
            scope: The CDK construct scope
            app_name: The name of the application
            secrets_dir: Directory where local secrets are stored (should be gitignored)
        """
        self.scope = scope
        self.app_name = app_name
        self.secrets_dir = secrets_dir
        self.secrets = {}  # Dictionary of secret files to their key-value pairs
        self.aws_secrets = {}  # Dictionary of secret names to their AWS Secret objects
        
    def add_secret_file(self, filename: str, default_values: dict = None):
        """
        Add a secret file to the manager. If a local file exists, it will be loaded.
        Otherwise, default values will be used.
        
        Args:
            filename: Name of the secret file (without path)
            default_values: Default key-value pairs to use if no local file exists
        
        Returns:
            Dictionary of key-value pairs from the file or defaults
        """
        # Try to load from local file
        local_path = os.path.join(self.secrets_dir, filename)
        values = default_values or {}
        
        if os.path.exists(local_path):
            with open(local_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        values[key.strip()] = value.strip()
        
        # Store the secret file and its key-value pairs
        self.secrets[filename] = values
        
        # Log the keys with masked values
        masked_values = {k: mask_secret_value(v) for k, v in values.items()}
        logger.info(f"Loaded secret file '{filename}' with {len(values)} key(s): {masked_values}")
        
        return values
        
    def create_secrets_in_secrets_manager(self):
        """
        Create secrets in AWS Secrets Manager for each secret file.
        
        Returns:
            Dictionary of secret names to their AWS Secret objects
        """
        logger.info(f"Creating secrets in AWS Secrets Manager for app '{self.app_name}'")
        
        for filename, values in self.secrets.items():
            if not values:
                logger.warning(f"Skipping empty secret file: {filename}")
                continue  # Skip empty secrets
                
            # Create a descriptive name for the secret in AWS
            secret_name = f"{self.app_name}_{os.path.splitext(filename)[0]}"
            logger.info(f"Creating AWS secret '{secret_name}' with {len(values)} key(s)")
            
            # Create the secret in AWS Secrets Manager
            secret = secretsmanager.Secret(
                self.scope, 
                f"{self.app_name}Secret{os.path.splitext(filename)[0].capitalize()}",
                description=f"Secrets for {self.app_name} - {filename}",
                secret_name=secret_name,
                secret_object_value={
                    key: value
                    for key, value in values.items()
                }
            )
            
            self.aws_secrets[secret_name] = secret
            logger.info(f"Created secret '{secret_name}' in AWS Secrets Manager")
        
        return self.aws_secrets
    
    def get_environment_variables(self):
        """
        Get environment variables for all secrets.
            
        Returns:
            A list of key-value pairs for environment variables
        """
        env_vars = []
        logger.info(f"Preparing environment variables from secrets for app '{self.app_name}'")
        
        for filename, secret_values in self.secrets.items():
            # Create the descriptive name for the secret in AWS
            secret_name = f"{self.app_name}_{os.path.splitext(filename)[0]}"
            
            # Get the AWS secret object
            aws_secret = self.aws_secrets.get(secret_name)
            if not aws_secret:
                logger.warning(f"Secret '{secret_name}' not found in AWS Secrets Manager")
                continue
                
            # Add each key-value pair from this secret file as an environment variable
            for key in secret_values.keys():
                env_vars.append(
                    apprunner.CfnService.KeyValuePairProperty(
                        name=key.upper(),
                        value=aws_secret.secret_value_from_json(key).to_string()
                    )
                )
                logger.info(f"Added environment variable: {key.upper()} from {secret_name}")
        
        logger.info(f"Total environment variables from secrets: {len(env_vars)}")
        return env_vars

    @staticmethod
    def push_secrets_to_aws(app_name: str, secrets_dir: str = DEFAULT_SECRETS_DIR, region: str = None):
        """
        Standalone utility to push local secrets to AWS Secrets Manager.
        This should be run locally with AWS credentials configured, 
        before deploying with GitHub Actions.
        
        Each file in the secrets directory is pushed as a separate secret with its key-value pairs.
        
        Args:
            app_name: Name of the application
            secrets_dir: Directory containing secret files
            region: AWS region (uses default from AWS config if not specified)
        
        Returns:
            Dictionary of secret names to their ARNs
        """
        # Create the boto3 client using local AWS credentials
        secretsmanager_client = boto3.client('secretsmanager', region_name=region)
        
        # Check if the secrets directory exists
        if not os.path.exists(secrets_dir):
            os.makedirs(secrets_dir)
            print(f"Created directory {secrets_dir}")
            print(f"Add your secret files in format:")
            print(f"KEY1=VALUE1")
            print(f"KEY2=VALUE2")
            return {}
        
        # Get all files in the secrets directory
        secret_files = [f for f in os.listdir(secrets_dir) if os.path.isfile(os.path.join(secrets_dir, f)) and not f.startswith('.')]
        
        if not secret_files:
            print(f"No secret files found in {secrets_dir}")
            print("Create files with key=value pairs on each line")
            return {}
            
        print(f"Found {len(secret_files)} secret file(s): {', '.join(secret_files)}")
        secret_arns = {}
        
        # Process each secret file
        for filename in secret_files:
            file_path = os.path.join(secrets_dir, filename)
            secret_values = {}
            
            # Read key-value pairs from the file
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        secret_values[key.strip()] = value.strip()
            
            if not secret_values:
                print(f"No key=value pairs found in {filename}, skipping")
                continue
                
            # Format the secret name in AWS
            secret_name = f"{app_name}_{os.path.splitext(filename)[0]}"
            
            try:
                # Check if this secret already exists
                try:
                    response = secretsmanager_client.describe_secret(SecretId=secret_name)
                    secret_arn = response.get('ARN')
                    
                    # Update existing secret
                    secretsmanager_client.put_secret_value(
                        SecretId=secret_name,
                        SecretString=json.dumps(secret_values)
                    )
                    print(f"Updated existing secret {secret_name} with {len(secret_values)} key(s)")
                    
                except secretsmanager_client.exceptions.ResourceNotFoundException:
                    # Create new secret
                    response = secretsmanager_client.create_secret(
                        Name=secret_name,
                        Description=f"Secrets for {app_name} - {filename}",
                        SecretString=json.dumps(secret_values)
                    )
                    secret_arn = response.get('ARN')
                    print(f"Created new secret {secret_name} with {len(secret_values)} key(s)")
                
                secret_arns[secret_name] = secret_arn
                
            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")
        
        return secret_arns 

    def discover_and_load_all_secret_files(self):
        """
        Automatically discover and load all secret files in the secrets directory.
        This makes the SecretManager dynamic without requiring explicit file listing.
        
        Returns:
            Dictionary of filenames to their loaded key-value pairs
        """
        # Ensure the directory exists
        if not os.path.exists(self.secrets_dir):
            os.makedirs(self.secrets_dir, exist_ok=True)
            logger.info(f"Created secrets directory: {self.secrets_dir}")
            return {}
            
        # Find all files in the secrets directory that aren't hidden
        secret_files = []
        for file_path in glob.glob(os.path.join(self.secrets_dir, '*')):
            if os.path.isfile(file_path) and not os.path.basename(file_path).startswith('.'):
                secret_files.append(os.path.basename(file_path))
        
        logger.info(f"Discovered {len(secret_files)} secret files: {', '.join(secret_files)}")
        
        # Load each file
        for filename in secret_files:
            if filename not in self.secrets:  # Only load if not already added
                values = self.add_secret_file(filename)
                logger.info(f"Loaded secret file '{filename}' with {len(values)} key(s): {', '.join(values.keys())}")
                
        return self.secrets 