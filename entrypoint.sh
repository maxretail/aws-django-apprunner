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

# Start the appropriate server based on environment
if [ "$DEBUG" = "1" ]; then
    echo "Starting development server..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "Starting production server..."
    exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 \
         --workers 2 \
         --proxy-headers \
         --forwarded-allow-ips '*' \
         --timeout-keep-alive 120 
fi