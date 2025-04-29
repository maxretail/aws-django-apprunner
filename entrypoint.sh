#!/bin/bash

# Exit on error
set -e

# Wait for database to be ready
echo "Waiting for database to be ready..."
max_retries=30
retry_count=0

while ! nc -z $DB_HOST $DB_PORT; do
    retry_count=$((retry_count+1))
    if [ $retry_count -ge $max_retries ]; then
        echo "Error: Could not connect to database after $max_retries attempts"
        exit 1
    fi
    echo "Database not ready yet, attempt $retry_count of $max_retries..."
    sleep 2
done

echo "Database is ready!"

# Run migrations
echo "Running migrations..."
python manage.py migrate

# Create superuser
echo "Ensuring superuser exists..."
python manage.py ensure_superuser

# Start the ASGI server
echo "Starting ASGI server..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 \
     --workers 2 \
     --threads 2 \
     --worker-class gthread \
     --worker-tmp-dir /dev/shm \
     --timeout 120 