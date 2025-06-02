#!/bin/bash
# Test runner script for the Django application
# Runs tests inside the Docker container
# 
# Usage examples:
#   ./scripts/test.sh                           # Run all tests
#   ./scripts/test.sh apps.projects             # Run tests for projects app
#   ./scripts/test.sh -v 2                     # Run with verbosity level 2
#   ./scripts/test.sh apps.core -v 2 --failfast # Run core tests with options
#   ./scripts/test.sh --help                   # Show Django test help

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

# Check if this is a help or version command
HELP_COMMANDS=("--help" "-h" "--version")
IS_HELP_COMMAND=false

for arg in "$@"; do
    for help_cmd in "${HELP_COMMANDS[@]}"; do
        if [[ "$arg" == "$help_cmd" ]]; then
            IS_HELP_COMMAND=true
            break 2
        fi
    done
done

# Show what we're about to run
if [ "$IS_HELP_COMMAND" = true ]; then
    echo "Showing Django test help..."
elif [ $# -eq 0 ]; then
    echo "Running all Django tests in container..."
else
    echo "Running Django tests with arguments: $*"
fi

# Run the test command with all provided arguments
$DOCKER_COMPOSE_CMD exec app python manage.py test "$@"

# Check if the command was successful and only show success message for actual test runs
if [ $? -eq 0 ]; then
    if [ "$IS_HELP_COMMAND" = false ]; then
        echo "✅ All tests passed!"
    fi
else
    echo "❌ Some tests failed."
    exit 1
fi 