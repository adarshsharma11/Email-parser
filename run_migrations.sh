#!/bin/bash

# Load .env variables if they exist
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | xargs)
fi

# Ensure DATABASE_URL is set correctly for str_command_center if not already in .env
# This script assumes you want to run migrations against str_command_center
echo "Running migrations for database: str_command_center"

# Check if alembic is installed
if ! command -v alembic &> /dev/null
then
    echo "alembic could not be found, installing..."
    pip install alembic asyncpg "sqlalchemy[asyncio]" psycopg2-binary
fi

# Run migrations
alembic upgrade head

echo "Migrations completed successfully."
