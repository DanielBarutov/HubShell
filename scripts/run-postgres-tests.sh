#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_PORT="${GAMECLUB_TEST_POSTGRES_PORT:-55434}"
export GAMECLUB_TEST_POSTGRES_DSN="${GAMECLUB_TEST_POSTGRES_DSN:-postgresql+asyncpg://gameclub_test:gameclub_test@127.0.0.1:${PG_PORT}/gameclub_test}"

cd "$ROOT_DIR"
"$ROOT_DIR/scripts/prepare-postgres-test.sh"
GAMECLUB_TEST_POSTGRES_DSN="$GAMECLUB_TEST_POSTGRES_DSN" \
  uv run --directory ./backend pytest -q -m postgres "$@"
