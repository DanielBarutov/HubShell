import asyncio
import datetime
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.infrastructure.postgres import (
    PostgresChargeRepository,
    PostgresMeterRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import BillingMode
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.entitlements.infrastructure.postgres import (
    PostgresEntitlementRepository,
)
from gameclub_backend.modules.offline.application.service import OfflineReplayService
from gameclub_backend.modules.offline.domain import (
    OfflineBatch,
    OfflineOperation,
    OfflineOperationKind,
)
from gameclub_backend.modules.offline.infrastructure.postgres import PostgresOfflineReplayRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.transfer import SessionTransferService
from gameclub_backend.modules.sessions.infrastructure.postgres import PostgresSessionRepository
from gameclub_backend.modules.sessions.infrastructure.transfers_postgres import (
    PostgresSessionTransferRepository,
)
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.postgres import (
    PostgresWorkstationRepository,
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


@pytest.mark.asyncio
async def test_postgres_transfer_confirms_once_and_rejects_other_key(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    workstation_ids: list[uuid.UUID] = []
    client_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    offer_id: uuid.UUID | None = None
    try:
        workstation_repository = PostgresWorkstationRepository(lambda: engine)
        workstations = WorkstationService(workstation_repository)
        source = await workstations.register(
            f"pg-transfer-source-{uuid.uuid4().hex[:8]}",
            "PG Transfer Source",
            group_id="pg-transfer-zone",
        )
        target = await workstations.register(
            f"pg-transfer-target-{uuid.uuid4().hex[:8]}",
            "PG Transfer Target",
            group_id="pg-transfer-zone",
        )
        workstation_ids.extend((source.id, target.id))

        client_repository = PostgresClientRepository(lambda: engine)
        client = await ClientService(client_repository).create(
            f"PgTransferClient{uuid.uuid4().hex[:8]}"
        )
        client_id = client.id
        session_repository = PostgresSessionRepository(lambda: engine)
        sessions = SessionService(
            session_repository,
            workstations=workstation_repository,
            clients=client_repository,
        )
        session = await sessions.start(
            source.id,
            created_by="integration-test",
            client_id=client.id,
            idempotency_key=f"pg-transfer-session-{uuid.uuid4()}",
        )
        session_id = session.id
        transfer_repository = PostgresSessionTransferRepository(lambda: engine)
        first_transfer = SessionTransferService(
            transfer_repository,
            sessions=session_repository,
            workstations=workstation_repository,
        )
        second_transfer = SessionTransferService(
            transfer_repository,
            sessions=session_repository,
            workstations=workstation_repository,
        )
        offer_key = f"pg-transfer-offer-{uuid.uuid4()}"
        offer_results = await asyncio.gather(
            first_transfer.create_offer(
                session.id,
                target.id,
                offer_key,
            ),
            second_transfer.create_offer(
                session.id,
                target.id,
                offer_key,
            ),
        )
        # Offer creation must converge before confirmations race.
        if offer_results[0].id != offer_results[1].id:
            raise AssertionError("Concurrent offer creation did not converge")
        offer = offer_results[0]
        offer_id = offer.id

        results = await asyncio.gather(
            first_transfer.confirm(offer.id, "pg-transfer-confirm-a"),
            second_transfer.confirm(offer.id, "pg-transfer-confirm-b"),
            return_exceptions=True,
        )

        successful = [item for item in results if not isinstance(item, Exception)]
        failures = [item for item in results if isinstance(item, Exception)]
        assert len(successful) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], ApplicationError)
        assert failures[0].code is ErrorCode.CONFLICT
        confirmed_offer, transferred = successful[0]
        assert confirmed_offer.confirm_idempotency_key in {
            "pg-transfer-confirm-a",
            "pg-transfer-confirm-b",
        }
        assert transferred.workstation_id == target.id
        persisted = await transfer_repository.get(offer.id)
        assert persisted is not None
        assert persisted.confirm_idempotency_key == confirmed_offer.confirm_idempotency_key
        persisted_session = await session_repository.get(session.id)
        assert persisted_session is not None
        assert persisted_session.workstation_id == target.id
    finally:
        async with engine.begin() as connection:
            if offer_id is not None:
                await connection.execute(
                    text("DELETE FROM session_transfer_offers WHERE id = :offer_id"),
                    {"offer_id": offer_id},
                )
            if session_id is not None:
                await connection.execute(
                    text("DELETE FROM gaming_sessions WHERE id = :session_id"),
                    {"session_id": session_id},
                )
            if client_id is not None:
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
            for workstation_id in workstation_ids:
                await connection.execute(
                    text("DELETE FROM workstations WHERE id = :workstation_id"),
                    {"workstation_id": workstation_id},
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_offline_duplicate_delivery_does_not_debit_twice(
    postgres_dsn: str,
) -> None:
    class FixedClock:
        def __init__(self) -> None:
            self.current = datetime.datetime(2026, 9, 2, 12, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    clock = FixedClock()
    workstation_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    tariff_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    try:
        workstation_repository = PostgresWorkstationRepository(lambda: engine)
        workstation = await WorkstationService(workstation_repository).register(
            f"pg-offline-device-{uuid.uuid4().hex[:8]}",
            "PG Offline PC",
            group_id="pg-offline-zone",
        )
        workstation_id = workstation.id
        client_repository = PostgresClientRepository(lambda: engine)
        clients = ClientService(client_repository, clock=clock)
        client = await clients.create(f"PgOfflineClient{uuid.uuid4().hex[:8]}")
        client_id = client.id
        await clients.top_up(
            client.id,
            amount_cents=500,
            bonus_amount=0,
            reason="PostgreSQL offline concurrency test",
            actor_id="integration-test",
            idempotency_key=f"pg-offline-deposit-{uuid.uuid4()}",
        )
        catalog = CatalogService(PostgresCatalogRepository(lambda: engine))
        tariff = await catalog.create_tariff(
            f"PG offline minute {uuid.uuid4().hex[:8]}",
            group_id="pg-offline-zone",
            duration_minutes=1,
            price_cents=0,
            valid_from=clock.current,
            valid_to=None,
            billing_mode=BillingMode.PER_MINUTE,
            price_per_minute_cents=10,
        )
        tariff_id = tariff.id
        session_repository = PostgresSessionRepository(lambda: engine)
        meter_repository = PostgresMeterRepository(lambda: engine)
        sessions = SessionService(
            session_repository,
            workstations=workstation_repository,
            clients=client_repository,
            clock=clock,
            meters=meter_repository,
        )
        session = await sessions.start(
            workstation.id,
            created_by="integration-test",
            client_id=client.id,
            source="device",
            tariff_id=tariff.id,
            idempotency_key=f"pg-offline-session-{uuid.uuid4()}",
        )
        session_id = session.id
        clock.current += datetime.timedelta(minutes=7)
        operation = OfflineOperation.create(
            session_id=session.id,
            device_id=workstation.device_id,
            sequence=1,
            kind=OfflineOperationKind.METER_DELTA,
            payload={"minutes": 7},
            snapshot_version=1,
            idempotency_key=f"pg-offline-meter-{uuid.uuid4()}",
            created_at=clock.now(),
        )
        batch = OfflineBatch(1, workstation.device_id, session.id, (operation,))

        def make_offline_service() -> OfflineReplayService:
            service_session_repository = PostgresSessionRepository(lambda: engine)
            service_meter_repository = PostgresMeterRepository(lambda: engine)
            service_sessions = SessionService(
                service_session_repository,
                workstations=workstation_repository,
                clients=client_repository,
                clock=clock,
                meters=service_meter_repository,
            )
            service_billing = BillingService(
                PostgresChargeRepository(lambda: engine),
                sessions=service_session_repository,
                workstations=workstation_repository,
                clients=clients,
                catalog=catalog,
                clock=clock,
                meter_repository=service_meter_repository,
            )
            return OfflineReplayService(
                PostgresOfflineReplayRepository(lambda: engine),
                sessions=service_sessions,
                session_repository=service_session_repository,
                workstations=workstation_repository,
                billing=service_billing,
                clock=clock,
            )

        first, second = await asyncio.gather(
            make_offline_service().replay(batch, actor_device_id=workstation.device_id),
            make_offline_service().replay(batch, actor_device_id=workstation.device_id),
        )

        assert {item.status.value for item in (first.results[0], second.results[0])} <= {
            "applied",
            "duplicate",
        }
        # Device sessions receive the five-minute login grant; only two of the
        # seven elapsed minutes are billable.
        assert (await clients.get(client.id)).balance_cents == 480
        meter = await BillingService(
            PostgresChargeRepository(lambda: engine),
            sessions=session_repository,
            workstations=workstation_repository,
            clients=clients,
            catalog=catalog,
            clock=clock,
            meter_repository=meter_repository,
        ).get_meter(session.id)
        assert meter.billed_cents == 20
    finally:
        async with engine.begin() as connection:
            if session_id is not None:
                await connection.execute(
                    text("DELETE FROM offline_operations WHERE session_id = :session_id"),
                    {"session_id": session_id},
                )
                await connection.execute(
                    text("DELETE FROM session_meters WHERE session_id = :session_id"),
                    {"session_id": session_id},
                )
                await connection.execute(
                    text("DELETE FROM gaming_sessions WHERE id = :session_id"),
                    {"session_id": session_id},
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
            if workstation_id is not None:
                await connection.execute(
                    text("DELETE FROM workstations WHERE id = :workstation_id"),
                    {"workstation_id": workstation_id},
                )
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_transfer_to_two_targets_commits_only_one_owner(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    workstation_ids: list[uuid.UUID] = []
    offer_ids: list[uuid.UUID] = []
    client_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    try:
        workstation_repository = PostgresWorkstationRepository(lambda: engine)
        workstations = WorkstationService(workstation_repository)
        source = await workstations.register(
            f"pg-transfer-two-source-{uuid.uuid4().hex[:8]}",
            "PG Transfer Two Source",
            group_id="pg-transfer-two-zone",
        )
        target_a = await workstations.register(
            f"pg-transfer-two-a-{uuid.uuid4().hex[:8]}",
            "PG Transfer Two A",
            group_id="pg-transfer-two-zone",
        )
        target_b = await workstations.register(
            f"pg-transfer-two-b-{uuid.uuid4().hex[:8]}",
            "PG Transfer Two B",
            group_id="pg-transfer-two-zone",
        )
        workstation_ids.extend((source.id, target_a.id, target_b.id))
        client_repository = PostgresClientRepository(lambda: engine)
        client = await ClientService(client_repository).create(
            f"PgTransferTwoClient{uuid.uuid4().hex[:8]}"
        )
        client_id = client.id
        session_repository = PostgresSessionRepository(lambda: engine)
        sessions = SessionService(
            session_repository,
            workstations=workstation_repository,
            clients=client_repository,
        )
        session = await sessions.start(
            source.id,
            created_by="integration-test",
            client_id=client.id,
            idempotency_key=f"pg-transfer-two-session-{uuid.uuid4()}",
        )
        session_id = session.id
        transfer_repository = PostgresSessionTransferRepository(lambda: engine)
        transfer = SessionTransferService(
            transfer_repository,
            sessions=session_repository,
            workstations=workstation_repository,
        )
        offer_a = await transfer.create_offer(
            session.id,
            target_a.id,
            f"pg-transfer-two-offer-a-{uuid.uuid4()}",
        )
        offer_b = await transfer.create_offer(
            session.id,
            target_b.id,
            f"pg-transfer-two-offer-b-{uuid.uuid4()}",
        )
        offer_ids.extend((offer_a.id, offer_b.id))

        results = await asyncio.gather(
            transfer.confirm(offer_a.id, "pg-transfer-two-confirm-a"),
            transfer.confirm(offer_b.id, "pg-transfer-two-confirm-b"),
            return_exceptions=True,
        )

        successful = [item for item in results if not isinstance(item, Exception)]
        failures = [item for item in results if isinstance(item, Exception)]
        assert len(successful) == 1
        assert len(failures) == 1
        assert isinstance(failures[0], ApplicationError)
        assert failures[0].code is ErrorCode.CONFLICT
        _, transferred = successful[0]
        assert transferred.workstation_id in {target_a.id, target_b.id}
        assert await session_repository.get_active_for_workstation(source.id) is None
        active_target_ids = {
            workstation_id
            for workstation_id in (target_a.id, target_b.id)
            if await session_repository.get_active_for_workstation(workstation_id) is not None
        }
        assert active_target_ids == {transferred.workstation_id}
    finally:
        async with engine.begin() as connection:
            for offer_id in offer_ids:
                await connection.execute(
                    text("DELETE FROM session_transfer_offers WHERE id = :offer_id"),
                    {"offer_id": offer_id},
                )
            if session_id is not None:
                await connection.execute(
                    text("DELETE FROM gaming_sessions WHERE id = :session_id"),
                    {"session_id": session_id},
                )
            if client_id is not None:
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
            for workstation_id in workstation_ids:
                await connection.execute(
                    text("DELETE FROM workstations WHERE id = :workstation_id"),
                    {"workstation_id": workstation_id},
                )
        await engine.dispose()
