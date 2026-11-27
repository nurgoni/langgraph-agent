#!/bin/sh
# Seed the demo datasets (F39) into their own databases, plus a read-only login role.
# Runs in the postgres image (service `demo-seed` in compose.yaml); idempotent.
#   PGHOST/PGUSER/PGPASSWORD: an admin connection to the postgres service.
#   DEMO_READONLY_USER/DEMO_READONLY_PASSWORD: the role the agent service connects with.
set -eu

RO_USER="${DEMO_READONLY_USER:-analyst_ro}"
RO_PASSWORD="${DEMO_READONLY_PASSWORD:-analyst_ro}"
PSQL="psql -v ON_ERROR_STOP=1 --quiet"

$PSQL -d postgres -v role="$RO_USER" -v password="$RO_PASSWORD" -f /demo/readonly_role.sql

for name in shop sensors; do
    database="demo_${name}"
    if ! $PSQL -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${database}'" | grep -q 1; then
        $PSQL -d postgres -c "CREATE DATABASE ${database}"
    fi
    $PSQL -d "$database" -f "/demo/${name}.sql"
    $PSQL -d "$database" -v role="$RO_USER" -f /demo/readonly_grants.sql
    echo "Seeded ${database}"
done
