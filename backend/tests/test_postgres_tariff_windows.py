import datetime
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import TariffAudience
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.infrastructure.postgres import (
    PostgresEntitlementRepository,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.slow]


@pytest.fixture
def postgres_dsn() -> str:
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run PostgreSQL tariff tests")
    return dsn


@pytest.mark.asyncio
async def test_postgres_persists_tariff_windows_audience_and_entitlement_snapshot(
    postgres_dsn: str,
) -> None:
    """
    Проверяет реальными PostgreSQL-репозиториями сохранение тарифа и immutable snapshot покупки.
    """
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    client_id: uuid.UUID | None = None
    tariff_id: uuid.UUID | None = None
    entitlement_id: uuid.UUID | None = None
    try:
        now = datetime.datetime.now(datetime.UTC).replace(second=0, microsecond=0)
        current_minute = now.hour * 60 + now.minute
        sale_start = (current_minute - 1) % (24 * 60)
        sale_end = (current_minute + 1) % (24 * 60)
        catalog = CatalogService(PostgresCatalogRepository(lambda: engine))
        tariff = await catalog.create_tariff(
            f"PG guest window {uuid.uuid4().hex[:8]}",
            "pg-tariff-zone",
            duration_minutes=60,
            price_cents=500,
            valid_from=now - datetime.timedelta(minutes=1),
            valid_to=None,
            time_restricted=True,
            sale_window_start_minute=sale_start,
            sale_window_end_minute=sale_end,
            usage_window_start_minute=22 * 60,
            usage_window_end_minute=6 * 60,
            window_timezone="UTC",
            audience=TariffAudience.REGISTERED,
        )
        tariff_id = tariff.id
        persisted = await catalog.get_tariff(tariff.id)
        assert persisted is not None
        assert persisted.audience is TariffAudience.REGISTERED
        assert persisted.sale_window_start_minute == sale_start
        assert persisted.sale_window_end_minute == sale_end
        assert persisted.usage_window_start_minute == 22 * 60
        assert persisted.usage_window_end_minute == 6 * 60
        assert persisted.window_timezone == "UTC"

        clients = ClientService(PostgresClientRepository(lambda: engine))
        client = await clients.create(f"PgTariffClient{uuid.uuid4().hex[:8]}")
        client_id = client.id
        await clients.top_up(
            client.id,
            amount_cents=1_000,
            bonus_amount=0,
            reason="PostgreSQL tariff test",
            actor_id="integration-test",
            idempotency_key=f"pg-tariff-deposit-{uuid.uuid4()}",
        )
        entitlements = EntitlementService(
            PostgresEntitlementRepository(lambda: engine),
            tariffs=catalog,
            clients=clients,
        )
        entitlement = await entitlements.purchase(
            client.id,
            tariff.id,
            "integration-test",
            f"pg-tariff-purchase-{uuid.uuid4()}",
        )
        entitlement_id = entitlement.id
        snapshot = await entitlements.get(entitlement.id)

        assert snapshot.audience is TariffAudience.REGISTERED
        assert snapshot.time_restricted is True
        assert snapshot.sale_window_start_minute == sale_start
        assert snapshot.sale_window_end_minute == sale_end
        assert snapshot.usage_window_start_minute == 22 * 60
        assert snapshot.usage_window_end_minute == 6 * 60
        assert snapshot.window_timezone == "UTC"
    finally:
        async with engine.begin() as connection:
            if entitlement_id is not None:
                await connection.execute(
                    text("DELETE FROM client_entitlements WHERE id = :id"),
                    {"id": entitlement_id},
                )
            if client_id is not None:
                await connection.execute(
                    text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
            if tariff_id is not None:
                await connection.execute(
                    text("DELETE FROM tariffs WHERE id = :tariff_id"),
                    {"tariff_id": tariff_id},
                )
        await engine.dispose()
