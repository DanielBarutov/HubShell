import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [pytest.mark.postgres, pytest.mark.integration]
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic/versions/20261017_0078_bonus_wallets.py"
)
spec = importlib.util.spec_from_file_location("bonus_migration", MIGRATION_PATH)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def run_migration(connection, action):
    with Operations.context(MigrationContext.configure(connection)):
        getattr(migration, action)()


@pytest.fixture
async def legacy_database():
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN for PostgreSQL checks")
    engine = create_async_engine(dsn)
    schema = f"bonus_migration_{uuid.uuid4().hex}"
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await connection.execute(
                text("""
                CREATE TABLE clients (id uuid PRIMARY KEY, balance_bonus bigint NOT NULL)
            """)
            )
            await connection.execute(
                text("""
                CREATE TABLE balance_operations (client_id uuid, bonus_amount bigint)
            """)
            )
            try:
                yield connection
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def test_upgrade_preserves_legacy_and_creates_exact_opening_entries(legacy_database):
    """Миграция сохраняет старые поля и журнал, создавая точные начальные остатки."""
    connection = legacy_database
    nonzero, zero = uuid.uuid4(), uuid.uuid4()
    await connection.execute(
        text("INSERT INTO clients VALUES (:nonzero, 123), (:zero, 0)"),
        {"nonzero": nonzero, "zero": zero},
    )
    await connection.execute(
        text("INSERT INTO balance_operations VALUES (:id, 123)"), {"id": nonzero}
    )
    before = (await connection.execute(text("SELECT * FROM balance_operations"))).all()
    await connection.run_sync(run_migration, "upgrade")
    assert (await connection.execute(text("SELECT * FROM balance_operations"))).all() == before
    assert (
        await connection.execute(
            text("SELECT balance_bonus FROM clients WHERE id = :id"), {"id": nonzero}
        )
    ).scalar_one() == 123
    wallets = dict(
        (
            await connection.execute(
                text("SELECT client_id, total_cents FROM client_bonus_wallets")
            )
        ).all()
    )
    assert wallets == {nonzero: 12_300, zero: 0}
    row = (await connection.execute(text("SELECT * FROM client_bonus_operations"))).mappings().one()
    assert row["client_id"] == nonzero
    assert row["amount_cents"] == row["total_delta_cents"] == row["total_after_cents"] == 12_300
    assert row["idempotency_key"] == f"bonus-opening:{nonzero}"
    assert row["actor_id"] == "bonus-migration"
    await connection.run_sync(run_migration, "downgrade")
    assert (
        await connection.execute(text("SELECT to_regclass('client_bonus_wallets')"))
    ).scalar() is None
    assert (await connection.execute(text("SELECT * FROM balance_operations"))).all() == before


@pytest.mark.parametrize("invalid", [-1, 92_233_720_368_547_759])
async def test_invalid_legacy_amount_stops_migration_without_partial_schema(
    legacy_database, invalid
):
    """Неконвертируемый остаток прерывает миграцию без частичных изменений."""
    connection = legacy_database
    await connection.execute(
        text("INSERT INTO clients VALUES (:id, :amount)"), {"id": uuid.uuid4(), "amount": invalid}
    )
    with pytest.raises(Exception, match="cannot be converted safely"):
        async with connection.begin_nested():
            await connection.run_sync(run_migration, "upgrade")
    assert (
        await connection.execute(text("SELECT balance_bonus FROM clients"))
    ).scalar_one() == invalid
    assert (
        await connection.execute(text("SELECT to_regclass('client_bonus_wallets')"))
    ).scalar() is None


async def test_downgrade_refuses_to_erase_bonus_activity(legacy_database):
    """Откат после бонусных операций запрещён без потери истории."""
    connection = legacy_database
    client_id = uuid.uuid4()
    await connection.execute(text("INSERT INTO clients VALUES (:id, 100)"), {"id": client_id})
    await connection.run_sync(run_migration, "upgrade")
    await connection.execute(
        text("""
        UPDATE client_bonus_operations
        SET idempotency_key = 'operator-bonus:activity', amount_cents = 10001
    """)
    )
    with pytest.raises(Exception, match="Bonus activity prevents lossless downgrade"):
        async with connection.begin_nested():
            await connection.run_sync(run_migration, "downgrade")
    assert (
        await connection.execute(text("SELECT total_cents FROM client_bonus_wallets"))
    ).scalar() == 10000
    assert (
        await connection.execute(text("SELECT count(*) FROM client_bonus_operations"))
    ).scalar() == 1


def run_earnings_migration(connection, action):
    path = MIGRATION_PATH.with_name("20261017_0079_bonus_earnings.py")
    module_spec = importlib.util.spec_from_file_location("earnings_migration", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, action)()


async def test_earnings_migration_preserves_existing_monetary_debt(legacy_database):
    """Миграция включает старый денежный долг в FIFO, не начисляя за него бонусы."""
    connection = legacy_database
    client_id = uuid.uuid4()
    await connection.execute(
        text("ALTER TABLE clients ADD balance_cents bigint NOT NULL DEFAULT 0")
    )
    await connection.execute(
        text("""
        ALTER TABLE clients ADD created_at timestamptz NOT NULL DEFAULT now()
    """)
    )
    await connection.execute(
        text("INSERT INTO clients (id, balance_bonus, balance_cents) VALUES (:id, 0, -1500)"),
        {"id": client_id},
    )
    await connection.run_sync(run_earnings_migration, "upgrade")
    debt = (await connection.execute(text("SELECT * FROM client_bonus_debits"))).mappings().one()
    assert debt["client_id"] == client_id
    assert debt["money_cents"] == 1500
    assert debt["paid_cents"] == 0
    assert debt["source_key"] is None
    assert (
        await connection.execute(text("SELECT count(*) FROM client_bonus_earnings"))
    ).scalar() == 0
    await connection.run_sync(run_earnings_migration, "downgrade")
    assert (await connection.execute(text("SELECT balance_cents FROM clients"))).scalar() == -1500
