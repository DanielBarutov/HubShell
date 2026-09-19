import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.modules.client_groups.application.service import ClientGroupService
from gameclub_backend.modules.client_groups.infrastructure.postgres import (
    PostgresClientGroupRepository,
)
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.slow]


@pytest.fixture
def postgres_dsn() -> str:
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run PostgreSQL client group tests")
    return dsn


@pytest.mark.asyncio
async def test_postgres_debtor_group_allows_first_metered_minute_after_free_time(
    postgres_dsn: str,
) -> None:
    """
    Проверяет на настоящей PostgreSQL, что должник с нулевым балансом может
    получить первое списание 10 ₽ в пределах лимита, а следующая копейка уже
    не увеличивает долг за заданный лимит.
    """
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    client_id: uuid.UUID | None = None
    group_id = f"pg-debt-{uuid.uuid4().hex[:16]}"
    try:
        group_repository = PostgresClientGroupRepository(lambda: engine)
        await ClientGroupService(group_repository).create(
            group_id,
            "PostgreSQL должники",
            allow_negative_balance=True,
            negative_balance_limit_cents=1_000,
        )
        clients = ClientService(
            PostgresClientRepository(lambda: engine),
            groups=group_repository,
        )
        client = await clients.create(f"PgDebtor{uuid.uuid4().hex[:12]}")
        client_id = client.id
        await clients.update(client.id, client.nickname, client_group_id=group_id)

        assert await clients.can_debit(client.id, 1_000, allow_negative_balance=True)
        updated, _ = await clients.debit(
            client.id,
            1_000,
            "Поминутная игра",
            "integration-test",
            f"pg-debt-meter-{uuid.uuid4()}",
            allow_negative_balance=True,
        )

        assert updated.balance_cents == -1_000
        assert not await clients.can_debit(client.id, 1, allow_negative_balance=True)
    finally:
        async with engine.begin() as connection:
            if client_id is not None:
                await connection.execute(
                    text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
            await connection.execute(
                text("DELETE FROM client_groups WHERE id = :group_id"),
                {"group_id": group_id},
            )
        await engine.dispose()
