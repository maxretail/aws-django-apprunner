#!/bin/bash
# Shell access script for the Django application container
# Opens an interactive shell inside the Docker app container
# 
# Usage:
#   ./scripts/shell.sh                    # Open bash shell in app container
#   ./scripts/shell.sh python manage.py  # Run a specific command in container

set -e  # Exit on any error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Change to the project root (parent of scripts directory)
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker compose &> /dev/null
then
    echo "Error: docker-compose or docker compose command not found"
    exit 1
fi

# Use docker compose if available, fallback to docker-compose
if command -v docker compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

# Check if the app container is running
if ! $DOCKER_COMPOSE_CMD ps app 2>/dev/null | grep -q "Up\|running"; then
    echo "❌ Docker Compose services are not running!"
    echo ""
    echo "Please start the services first:"
    echo "  docker compose up -d"
    echo ""
    echo "Or run in the foreground to see logs:"
    echo "  docker compose up"
    echo ""
    exit 1
fi

# If no arguments provided, open an interactive bash shell
if [ $# -eq 0 ]; then
    echo "Opening interactive shell in app container..."
    $DOCKER_COMPOSE_CMD exec app bash
else
    # If arguments provided, execute the command in the container
    echo "Executing command in app container: $*"
    $DOCKER_COMPOSE_CMD exec app "$@"
fi 