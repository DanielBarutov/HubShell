import asyncio
import datetime
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.entitlements.infrastructure.postgres import (
    PostgresEntitlementRepository,
)


@pytest.fixture
def postgres_dsn() -> str:
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run PostgreSQL contract tests")
    return dsn


@pytest.mark.asyncio
async def test_postgres_parallel_package_consumers_preserve_locked_delta(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    client_id: uuid.UUID | None = None
    tariff_id: uuid.UUID | None = None
    try:
        client_repository = PostgresClientRepository(lambda: engine)
        clients = ClientService(client_repository)
        client = await clients.create(f"PgPackageClient{uuid.uuid4().hex[:10]}")
        client_id = client.id
        await clients.top_up(
            client.id,
            amount_cents=1_000,
            bonus_amount=0,
            reason="PostgreSQL package concurrency test",
            actor_id="integration-test",
            idempotency_key=f"pg-package-deposit-{uuid.uuid4()}",
        )

        catalog = CatalogService(PostgresCatalogRepository(lambda: engine))
        now = datetime.datetime.now(datetime.UTC)
        tariff = await catalog.create_tariff(
            f"Pg package {uuid.uuid4().hex[:8]}",
            group_id="pg-contract-zone",
            duration_minutes=3,
            price_cents=100,
            valid_from=now - datetime.timedelta(minutes=1),
            valid_to=None,
        )
        tariff_id = tariff.id
        entitlements = EntitlementService(
            PostgresEntitlementRepository(lambda: engine),
            tariffs=catalog,
            clients=clients,
        )
        package = await entitlements.purchase(
            client.id,
            tariff.id,
            "integration-test",
            f"pg-package-{uuid.uuid4()}",
        )
        await entitlements.activate(package.id, client.id)

        results = await asyncio.gather(
            *(
                entitlements.consume_for_session(
                    client.id,
                    "pg-contract-zone",
                    2,
                    now=now,
                    initial_entitlement_id=package.id,
                )
                for _ in range(2)
            )
        )

        assert sorted(item.consumed_minutes for item in results) == [1, 2]
        assert sum(item.consumed_minutes for item in results) == 3
        assert (await entitlements.get(package.id)).status is EntitlementStatus.EXHAUSTED
    finally:
        if client_id is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM client_entitlements WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
                await connection.execute(
                    text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
        if tariff_id is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM tariffs WHERE id = :tariff_id"),
                    {"tariff_id": tariff_id},
                )
        await engine.dispose()
