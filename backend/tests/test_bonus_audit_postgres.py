import os
from pathlib import Path

import asyncpg
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

AUDIT_SQL = (Path(__file__).resolve().parents[1] / "scripts/audit_bonus_balances.sql").read_text()


async def test_bonus_inventory_detects_mismatches_and_orphans_without_changing_data():
    """Аудит обнаруживает расхождения и переполнение без изменения данных."""
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run PostgreSQL integration tests")
    connection = await asyncpg.connect(dsn.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        # Temporary tables hide real tables for this connection only.
        await connection.execute("""
            CREATE TEMP TABLE clients (id int, balance_bonus bigint);
            CREATE TEMP TABLE balance_operations (client_id int, bonus_amount bigint);
        """)
        begin, query, commit, _ = AUDIT_SQL.split(";")
        await connection.execute(begin)
        assert await connection.fetchval("SHOW transaction_read_only") == "on"
        empty = dict(await connection.fetchrow(query))
        assert all(value == 0 for value in empty.values())
        await connection.execute(commit)
        await connection.execute("""
            INSERT INTO clients VALUES (1, 100), (2, 20), (3, 0), (4, -1),
                (5, 9223372036854775807);
            INSERT INTO balance_operations VALUES (1, 40), (1, 60), (2, 10),
                (4, -1), (5, 9223372036854775807), (6, 50);
        """)
        before_clients = await connection.fetch("SELECT * FROM clients ORDER BY id")
        before_ledger = await connection.fetch(
            "SELECT * FROM balance_operations ORDER BY client_id, bonus_amount"
        )
        await connection.execute(begin)
        report = dict(await connection.fetchrow(query))
        await connection.execute(commit)
        assert report == {
            "clients": 5,
            "nonzero_bonus_clients": 4,
            "legacy_balance_units": 9223372036854775926,
            "legacy_ledger_units": 9223372036854775916,
            "clients_with_ledger_mismatch": 1,
            "orphan_ledger_clients": 1,
            "negative_bonus_records": 1,
            "balances_exceeding_minor_unit_bigint": 1,
        }
        assert await connection.fetch("SELECT * FROM clients ORDER BY id") == before_clients
        assert (
            await connection.fetch(
                "SELECT * FROM balance_operations ORDER BY client_id, bonus_amount"
            )
            == before_ledger
        )
    finally:
        await connection.close()
