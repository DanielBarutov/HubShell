#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.postgres-test.yml"
COMPOSE_PROJECT="hubshell-postgres-test"
PG_PORT="${GAMECLUB_TEST_POSTGRES_PORT:-55434}"
export GAMECLUB_TEST_POSTGRES_DSN="${GAMECLUB_TEST_POSTGRES_DSN:-postgresql+asyncpg://gameclub_test:gameclub_test@127.0.0.1:${PG_PORT}/gameclub_test}"
export GAMECLUB_POSTGRES_DSN="$GAMECLUB_TEST_POSTGRES_DSN"

cd "$ROOT_DIR"
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" up -d --wait postgres-test
uv run --directory ./backend alembic upgrade head
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres-test \
  psql -v ON_ERROR_STOP=1 -U gameclub_test -d gameclub_test \
  < "$ROOT_DIR/scripts/postgres-test-seed.sql"
printf 'PostgreSQL test database is migrated and seeded.\n'
printf 'GAMECLUB_TEST_POSTGRES_DSN=%s\n' "$GAMECLUB_TEST_POSTGRES_DSN"
