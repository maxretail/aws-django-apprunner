# CDK Infrastructure

This directory contains the AWS CDK infrastructure code for deploying the Django application to AWS App Runner.

## Managing Secrets

Secrets are managed using the `SecretManager` class, which allows you to:

1. Store secrets locally during development (in the `.secrets` directory)
2. Push them to AWS Secrets Manager before deployment using local AWS credentials
3. Deploy your application using GitHub Actions, which will reference the secrets already stored in AWS
4. Inject the secrets as environment variables into your App Runner service

### Dynamic Secret Discovery

The system is fully dynamic - no need to modify any code to add new secrets:

1. Create a file in the `.secrets` directory with key-value pairs
2. Push the secrets to AWS using the `push_secrets.py` script
3. Deploy your application - the secrets will be automatically discovered and included

This means you can add new secrets by simply creating files - no code changes required!

### Secrets Structure

Each file in the `.secrets` directory becomes a separate AWS secret with key-value pairs:

```
.secrets/
  ├── django         # Contains Django-related secrets
  ├── apiKeys        # Contains various API keys
  └── database       # Contains database credentials
```

Where each file contains key-value pairs like:

```
# .secrets/django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_SUPERUSER_PASSWORD=admin-password

# .secrets/apiKeys
OPENAI_API_KEY=some-secret-key
STRIPE_API_KEY=sk_test_123
```

These become:
- AWS Secret named `YOUR_APP_NAME_django` with keys `DJANGO_SECRET_KEY` and `DJANGO_SUPERUSER_PASSWORD`
- AWS Secret named `YOUR_APP_NAME_apiKeys` with keys `OPENAI_API_KEY` and `STRIPE_API_KEY`

### Workflow with GitHub Actions

When using GitHub Actions for deployment, follow this workflow:

1. Develop locally, storing secrets in `.secrets/` (gitignored)
2. Before deployment, push your secrets to AWS using the provided CLI tool
3. Deploy with GitHub Actions, which will use the secrets already in AWS Secrets Manager

### Adding Secret Files

To add new secrets to your application, you don't need to modify any code:

1. Create a file in the `.secrets` directory with key-value pairs:

```bash
# Create .secrets directory if it doesn't exist
mkdir -p .secrets

# Add a secret file (replace FILENAME with your desired name)
cat > .secrets/FILENAME << EOF
KEY1=value1
KEY2=value2
EOF
```

That's it! The secret will be automatically discovered, pushed to AWS, and made available to your application.

### Pushing Secrets to AWS

Before deploying with GitHub Actions, push your secrets to AWS Secrets Manager using the provided CLI tool:

```bash
# Navigate to the CDK directory
cd cdk

# Make sure the script is executable
chmod +x push_secrets.py

# Push secrets to AWS (automatically uses APP_NAME from APPCONFIG.env)
./push_secrets.py

# Or specify a different app name
./push_secrets.py --app-name YOUR_APP_NAME

# Other options
./push_secrets.py --secrets-dir /path/to/secrets --region us-west-2 --dry-run
```

The script will:
1. Use the APP_NAME from APPCONFIG.env if --app-name is not specified
2. Read all files from your secrets directory
3. Create or update secrets in AWS Secrets Manager with the correct name format (`APP_NAME_filename`)
4. Output the ARNs of the created/updated secrets

Use the `--dry-run` option to validate your secrets without pushing them to AWS.

### Security Considerations

- The `.secrets` directory is added to `.gitignore` to prevent accidentally committing secrets
- Secrets are stored in AWS Secrets Manager with encryption at rest
- The App Runner service is granted minimal permissions to access only the necessary secrets
- Environment variables are injected into the App Runner service at runtime
- You must manually push secrets to AWS before deployment - they're never included in Git or GitHub Actions

### Accessing Secrets

To access specific secrets:

```bash
# List all secrets for your application (replace YOUR_APP_NAME)
aws secretsmanager list-secrets --filter Key="name",Values="YOUR_APP_NAME_" | jq '.SecretList[].Name'

# Get all key-value pairs from a specific secret
aws secretsmanager get-secret-value --secret-id YOUR_APP_NAME_django --query 'SecretString' --output text | jq

# Get a specific key from a secret
aws secretsmanager get-secret-value --secret-id YOUR_APP_NAME_django --query 'SecretString' --output text | jq -r '.DJANGO_SUPERUSER_PASSWORD'
``` 