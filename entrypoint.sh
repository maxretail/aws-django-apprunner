#!/bin/bash

# Exit on error
set -e

# Wait for database to be ready
echo "Waiting for database to be ready..."
max_retries=30
retry_count=0

while ! nc -z ${DB_HOST:-localhost} ${DB_PORT:-5432}; do
    retry_count=$((retry_count+1))
    if [ $retry_count -ge $max_retries ]; then
        echo "Error: Could not connect to database after $max_retries attempts"
        exit 1
    fi
    echo "Database not ready yet, attempt $retry_count of $max_retries..."
    sleep 2
done

echo "Database is ready!"

# Create media directories if they don't exist
# Note: In development with docker-compose volumes, we may need to create these
# The directories should be created by Django when needed, but we'll try to create them here
echo "Ensuring media directories exist..."
python manage.py shell << 'EOF' 2>/dev/null || true
import os
from django.conf import settings
try:
    media_root = settings.MEDIA_ROOT
    vessel_icons_dir = os.path.join(media_root, 'vessel_icons')
    os.makedirs(media_root, exist_ok=True)
    os.makedirs(vessel_icons_dir, exist_ok=True)
    print(f'Media directories ready at {media_root}')
except Exception as e:
    print(f'Note: Media directory setup: {e}')
    pass
EOF

# Run migrations
echo "Running migrations..."
python manage.py migrate

# Create superuser
echo "Ensuring superuser exists..."
python manage.py ensure_superuser

# Start the appropriate server based on environment
PORT=${PORT:-8000}

# Start Django-Q2 worker in background (for both dev and prod)
echo "Starting Django-Q2 worker in background..."
nohup python manage.py qcluster > /tmp/qcluster.log 2>&1 &
QCLUSTER_PID=$!
echo "QCluster started with PID: $QCLUSTER_PID"

# Function to cleanup on exit
cleanup() {
    echo "Shutting down QCluster (PID: $QCLUSTER_PID)..."
    kill $QCLUSTER_PID 2>/dev/null || true
    wait $QCLUSTER_PID 2>/dev/null || true
}
trap cleanup EXIT

if [ "$DEBUG" = "1" ]; then
    echo "Starting development server on port $PORT..."
    exec python manage.py runserver 0.0.0.0:$PORT
else
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
    
    echo "Starting production server on port $PORT..."
    exec gunicorn config.wsgi:application \
         --bind 0.0.0.0:$PORT \
         --workers 2 \
         --threads 4 \
         --timeout 120 \
         --access-logfile - \
         --error-logfile -
fi
