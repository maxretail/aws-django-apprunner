#!/bin/bash
# Welcome script for Django development environment
# Displays available development tools and aliases

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Change to the project root (parent of scripts directory)
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo ""
echo "🚀 Django Development Environment Ready!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Available Development Tools:"
echo ""
echo "🧪 Testing:"
echo "   test                    - Run all Django tests"
echo "   test apps.core          - Run tests for specific app"
echo "   test -v 2               - Run tests with verbose output"
echo "   test --failfast         - Stop on first test failure"
echo "   runtests                - Alias for test command"
echo ""
echo "🐚 Container Shell Access:"
echo "   shell                   - Open bash shell in app container"
echo "   shell python manage.py  - Run Django commands in container"
echo "   appshell                - Alias for shell command"
echo ""
echo "📁 Direct Script Access:"
echo "   ./scripts/test.sh       - Test runner script"
echo "   ./scripts/shell.sh      - Container shell script"
echo ""
echo "💡 Quick Start Examples:"
echo "   test                    - Run all tests"
echo "   shell                   - Access Django environment"
echo "   shell python manage.py shell - Open Django shell"
echo "   shell python manage.py migrate - Run migrations"
echo ""
echo "📚 For more details, see the README.md file"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check Docker Compose status
if command -v docker compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    echo "⚠️  Docker Compose not found. Please install Docker Compose to use the development tools."
    echo ""
    exit 1
fi

# Check if services are running
if $DOCKER_COMPOSE_CMD ps app 2>/dev/null | grep -q "Up\|running"; then
    echo "✅ Docker Compose services are running!"
    echo "   You can now use the development tools above."
else
    echo "🔴 Docker Compose services are not running."
    echo ""
    echo "   The test and shell commands require Docker services to be running."
    echo "   Would you like to start them now?"
    echo ""
    echo "   Options:"
    echo "   • Run in background:  docker compose up -d"
    echo "   • Run with logs:      docker compose up"
    echo ""
    
    # Interactive prompt if running in an interactive terminal
    if [[ -t 0 && -t 1 ]]; then
        read -p "   Start services in background? (y/N): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "   Starting Docker Compose services..."
            $DOCKER_COMPOSE_CMD up -d
            if [ $? -eq 0 ]; then
                echo "   ✅ Services started successfully!"
                echo "   You can now use the development tools."
            else
                echo "   ❌ Failed to start services. Please check the logs."
            fi
        else
            echo "   You can start services manually when ready:"
            echo "   docker compose up -d"
        fi
    else
        echo "   Start services manually when you're ready to develop:"
        echo "   docker compose up -d"
    fi
fi

echo "" 