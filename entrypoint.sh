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

# Retrieve AWS secrets in production mode
if [ "$DEBUG" != "1" ]; then
    echo "Production mode detected. Retrieving AWS secrets..."
    
    # Check if APP_NAME is provided
    if [ -z "$APP_NAME" ]; then
        echo "Error: APP_NAME environment variable is required in production mode"
        exit 1
    fi
    
    echo "Retrieving secrets for prefix $APP_NAME..."
    
    # Get secrets from AWS Secrets Manager and set as environment variables
    SECRETS=$(aws secretsmanager list-secrets --filters Key=name,Values=$APP_NAME --query "SecretList[*].Name" --output text)
    
    for SECRET_NAME in $SECRETS; do
        echo "Processing secret: $SECRET_NAME"
        SECRET_VALUE=$(aws secretsmanager get-secret-value --secret-id $SECRET_NAME --query SecretString --output text)
        
        # Parse JSON and set each key-value pair as environment variable
        echo "Setting environment variables from secret..."
        while IFS="=" read -r key value; do
            # Skip empty lines
            if [ -z "$key" ]; then
                continue
            fi
            
            # Try to process this environment variable
            echo "Processing: $key"
            {
                # Remove quotes and any trailing comma from value
                value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e 's/,$//')
                key=$(echo "$key" | sed -e 's/^"//' -e 's/"$//' -e 's/[[:space:]]*$//')
                
                if [ ! -z "$key" ]; then
                    echo "Setting $key"
                    export "$key"="$value"
                    echo "Successfully set $key"
                else
                    echo "Warning: Empty key found, skipping"
                fi
            } || {
                echo "Warning: Failed to process environment variable $key, continuing with others"
            }
        done < <(echo "$SECRET_VALUE" | jq -r 'to_entries | .[] | "\(.key)=\(.value)"' 2>/dev/null || echo "ERROR_PARSING_JSON=true")
        
        # Check if we had a JSON parsing error
        if [ "$ERROR_PARSING_JSON" = "true" ]; then
            echo "Warning: Failed to parse secret JSON for $SECRET_NAME, but continuing with other secrets"
        fi
    done
    
    echo "AWS secrets loaded successfully"
fi

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
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
    
    echo "Starting production server..."
    exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 \
         --workers 2 \
         --proxy-headers \
         --forwarded-allow-ips '*' \
         --timeout-keep-alive 120 
fi