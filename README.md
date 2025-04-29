# Django AWS App Runner Template

A template for deploying Django applications on AWS App Runner with Docker, PostgreSQL, and AWS CDK infrastructure. This template is designed to be used with VS Code or Cursor via devcontainers.

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/maxretail/aws-django-apprunner <project name>
   cd <project name>
   ```

2. Open the project in VS Code or Cursor:
   - VS Code: Open the folder and click "Reopen in Container" when prompted
   - Cursor: Open the folder and it will automatically detect and use the devcontainer

3. Start the development environment:
   ```bash
   docker-compose up
   ```

The application will be available at `http://localhost:8000`.

## Development Environment

This project uses VS Code/Cursor devcontainers to provide a consistent development environment. The devcontainer includes:

- Python 3.9
- PostgreSQL client
- AWS CLI
- CDK CLI
- All necessary development tools

The devcontainer automatically configures:
- Python virtual environment
- Git configuration
- AWS credentials (if available)
- Development database
- Django development server

### Development Helpers

The project includes `.cursor-helper.json` which provides context to Cursor's AI about the development environment. This ensures that Django commands are always run in the correct context - inside the Docker container. For example:

```bash
# When running Django commands, they will automatically be wrapped to run in the container:
docker compose exec -it app bash -c "python manage.py check"
```

This helper ensures that commands are always run in the correct context when using Cursor's AI features.

## Project Structure

```
.
├── apps/                 # Django applications
├── config/              # Django project configuration
├── static/              # Static files
├── templates/           # HTML templates
├── scripts/             # Utility scripts
├── cdk/                 # AWS CDK infrastructure code
├── .devcontainer/       # VS Code/Cursor dev container configuration
├── .github/             # GitHub workflows and configurations
├── APPCONFIG.env        # AWS application configuration
├── .env                 # Environment variables (not tracked in git)
├── .env.example         # Example environment variables
├── apprunner.yaml       # AWS App Runner configuration
├── docker-compose.yml   # Local development setup
├── Dockerfile           # Production container configuration
├── manage.py            # Django management script
└── requirements.txt     # Python dependencies
```

## Environment Variables

### Local Development Environment Variables

For local development, the following variables are used:

- `DJANGO_SUPERUSER_EMAIL`: Email for the development superuser (default: devops@example.com)
- `DJANGO_SUPERUSER_PASSWORD`: Password for the development superuser (default: devops123)

These are configured in `APPCONFIG.env` and can be overridden in your local environment. In production, the superuser credentials are managed through AWS Secrets Manager and the CDK stack.

## Deployment

The application is deployed using AWS App Runner. The deployment process is automated through GitHub Actions.

### GitHub Actions Deployment

The repository includes a GitHub Actions workflow that automatically deploys the application when changes are pushed to the main branch. The workflow:

1. Reads the APP_NAME from APPCONFIG.env
2. Builds and pushes a Docker image to Amazon ECR
3. Updates the App Runner service with the new image

#### Required GitHub Secrets

The following secrets must be configured in your GitHub repository:

- `AWS_ACCESS_KEY_ID`: AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: AWS secret access key
- `AWS_REGION`: (Optional) The AWS region to deploy to (defaults to us-east-1)

The AWS credentials should have permissions to:
- Push to ECR
- Create/update App Runner services
- Access any other AWS resources your application needs

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

[Add your license information here] 