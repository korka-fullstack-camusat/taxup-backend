#!/bin/sh
# Robust migration script — handles already-initialized databases
echo "=== TAXUP Database Migration ==="

# Check current alembic state
CURRENT=$(alembic current 2>&1 || true)
echo "Current state: $CURRENT"

# If already at head, exit successfully
if echo "$CURRENT" | grep -q "(head)"; then
    echo "Database already at latest migration. Nothing to do."
    exit 0
fi

# Try running migrations normally
echo "Running: alembic upgrade head"
alembic upgrade head
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Migrations applied successfully."
    exit 0
fi

# Migration failed — check if tables already exist
echo "Migration failed (exit $EXIT_CODE). Checking if schema exists..."

TABLE_EXISTS=$(python3 -c "
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    url = os.environ.get('DATABASE_URL', '')
    url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    url = url.replace('postgres://', 'postgresql+asyncpg://', 1)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='users'\"))
            count = result.scalar()
            print(count)
    finally:
        await engine.dispose()

asyncio.run(check())
" 2>/dev/null || echo "0")

if [ "$TABLE_EXISTS" = "1" ]; then
    echo "Schema already exists. Stamping alembic to head..."
    alembic stamp head
    echo "Stamped successfully."
    exit 0
fi

echo "ERROR: Migration failed and schema does not exist."
exit 1
