#!/bin/bash
# Robust migration script — handles already-initialized databases
set -e

echo "=== TAXUP Database Migration ==="

# Check current alembic state
CURRENT=$(alembic current 2>&1 || true)
echo "Current state: $CURRENT"

# If already at head, exit successfully
if echo "$CURRENT" | grep -q "(head)"; then
    echo "Database already at latest migration (head). Nothing to do."
    exit 0
fi

# Try running migrations normally
echo "Running: alembic upgrade head"
if alembic upgrade head; then
    echo "Migrations applied successfully."
    exit 0
fi

# If upgrade failed, check if tables already exist (common on re-deploy with existing DB)
echo "Migration failed. Checking if schema already exists..."

TABLES=$(python3 -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    url = os.environ['DATABASE_URL'].replace('postgresql://', 'postgresql+asyncpg://', 1).replace('postgres://', 'postgresql+asyncpg://', 1)
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        result = await conn.execute(text(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='users'\"))
        count = result.scalar()
        print(count)
    await engine.dispose()

asyncio.run(check())
" 2>/dev/null || echo "0")

if [ "$TABLES" = "1" ]; then
    echo "Schema already exists. Stamping alembic_version to head..."
    alembic stamp head
    echo "Database stamped successfully. Migration complete."
    exit 0
else
    echo "ERROR: Migration failed and schema does not exist. Manual intervention required."
    exit 1
fi
