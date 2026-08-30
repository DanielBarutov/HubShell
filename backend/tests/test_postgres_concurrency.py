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
    PostgresChargeReconciliationRepository,
    PostgresChargeRepository,
)
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.infrastructure.postgres import (
    PostgresCashShiftRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.clients.application.guests import GuestService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.postgres import (
    PostgresClientRepository,
    PostgresGuestRepository,
)
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.infrastructure.postgres import (
    PostgresReservationRepository,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.postgres import PostgresSessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.postgres import (
    PostgresWorkstationRepository,
)


def test_postgres_dsn_is_explicitly_configured() -> None:
    if not os.getenv("GAMECLUB_TEST_POSTGRES_DSN"):
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run PostgreSQL integration tests")


@pytest.fixture
def postgres_dsn() -> str:
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run PostgreSQL integration tests")
    return dsn


async def test_postgres_preserves_concurrent_distinct_top_ups(postgres_dsn: str) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    client_id = None
    try:
        client_repository = PostgresClientRepository(lambda: engine)
        client_service = ClientService(client_repository)
        client = await client_service.create(f"PgBalance{uuid.uuid4().hex[:12]}")
        client_id = client.id

        await asyncio.gather(
            *(
                client_service.top_up(
                    client_id=client.id,
                    amount_cents=100,
                    bonus_amount=10,
                    reason="PostgreSQL concurrency test",
                    actor_id="integration-test",
                    idempotency_key=f"pg-balance-{uuid.uuid4()}",
                )
                for _ in range(8)
            )
        )

        final_client = await client_service.get(client.id)
        assert final_client.balance_cents == 800
        assert final_client.balance_bonus == 80
    finally:
        if client_id is not None:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM balance_operations WHERE client_id = :client_id"),
                    {"client_id": client_id},
                )
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
        await engine.dispose()


async def test_postgres_persists_guest_links_for_reservation_and_session(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    guest_id = None
    workstation_id = None
    reservation_id = None
    session_id = None
    try:
        guest_repository = PostgresGuestRepository(lambda: engine)
        guest = await GuestService(guest_repository).create(
            f"PgGuest{uuid.uuid4().hex[:10]}",
            "+7 (999) 700-11-22",
        )
        guest_id = guest.id
        workstation_repository = PostgresWorkstationRepository(lambda: engine)
        workstation = await WorkstationService(workstation_repository).register(
            f"pg-guest-device-{uuid.uuid4().hex[:8]}",
            "PG Guest PC",
        )
        workstation_id = workstation.id
        reservation_service = ReservationService(
            PostgresReservationRepository(lambda: engine),
            workstations=workstation_repository,
            clients=PostgresClientRepository(lambda: engine),
            guests=guest_repository,
        )
        start_at = datetime.datetime(2040, 1, 1, 12, tzinfo=datetime.UTC)
        reservation = await reservation_service.create(
            workstation_ids=[workstation.id],
            start_at=start_at,
            end_at=start_at + datetime.timedelta(hours=1),
            created_by="integration-test",
            guest_id=guest.id,
        )
        reservation_id = reservation.id
        session_service = SessionService(
            PostgresSessionRepository(lambda: engine),
            workstations=workstation_repository,
            clients=PostgresClientRepository(lambda: engine),
            guests=guest_repository,
        )
        session = await session_service.start(
            workstation.id,
            created_by="integration-test",
            guest_id=guest.id,
        )
        session_id = session.id

        assert (await guest_repository.get(guest.id)).nickname == guest.nickname
        assert (await reservation_service.get(reservation.id)).guest_id == guest.id
        assert (await session_service.get(session.id)).guest_id == guest.id
    finally:
        async with engine.begin() as connection:
            if session_id is not None:
                await connection.execute(
                    text("DELETE FROM gaming_sessions WHERE id = :session_id"),
                    {"session_id": session_id},
                )
            if reservation_id is not None:
                await connection.execute(
                    text("DELETE FROM reservations WHERE id = :reservation_id"),
                    {"reservation_id": reservation_id},
                )
            if workstation_id is not None:
                await connection.execute(
                    text("DELETE FROM workstations WHERE id = :workstation_id"),
                    {"workstation_id": workstation_id},
                )
            if guest_id is not None:
                await connection.execute(
                    text("DELETE FROM guests WHERE id = :guest_id"),
                    {"guest_id": guest_id},
                )
        await engine.dispose()


async def test_postgres_quote_applies_versioned_discount_rule_data(postgres_dsn: str) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    tariff_id = None
    rule_id = None
    try:
        service = CatalogService(PostgresCatalogRepository(lambda: engine))
        moment = datetime.datetime(2035, 1, 15, 12, tzinfo=datetime.UTC)
        group_id = f"pg-vip-{uuid.uuid4().hex[:8]}"
        tariff = await service.create_tariff("PG VIP hour", group_id, 60, 999, moment, None)
        tariff_id = tariff.id
        rule = await service.create_discount_rule(
            group_id,
            percent_bps=1_250,
            priority=4,
            valid_from=moment,
            valid_to=None,
        )
        rule_id = rule.id

        quote = await service.quote(60, group_id, moment, discount_category=group_id.upper())

        assert quote.price_before_discount_cents == 999
        assert quote.discount_amount_cents == 124
        assert quote.price_cents == 875
        assert quote.discount_percent_bps == 1_250
    finally:
        async with engine.begin() as connection:
            if rule_id is not None:
                await connection.execute(
                    text("DELETE FROM discount_rules WHERE id = :rule_id"),
                    {"rule_id": rule_id},
                )
            if tariff_id is not None:
                await connection.execute(
                    text("DELETE FROM tariffs WHERE id = :tariff_id"),
                    {"tariff_id": tariff_id},
                )
        await engine.dispose()


async def test_postgres_assigns_unique_versions_under_concurrent_tariff_creates(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    tariff_ids: list[uuid.UUID] = []
    try:
        service = CatalogService(PostgresCatalogRepository(lambda: engine))
        tariff_key = f"pg-version-{uuid.uuid4().hex[:10]}"
        moment = datetime.datetime(2036, 1, 15, 12, tzinfo=datetime.UTC)
        tariffs = await asyncio.gather(
            *(
                service.create_tariff(
                    f"PG version {index}",
                    "pg-version-zone",
                    60,
                    700 + index,
                    moment + datetime.timedelta(days=index),
                    None,
                    tariff_key=tariff_key,
                )
                for index in range(2)
            )
        )
        tariff_ids.extend(tariff.id for tariff in tariffs)

        assert sorted(tariff.version for tariff in tariffs) == [1, 2]
    finally:
        async with engine.begin() as connection:
            for tariff_id in tariff_ids:
                await connection.execute(
                    text("DELETE FROM tariffs WHERE id = :tariff_id"),
                    {"tariff_id": tariff_id},
                )
        await engine.dispose()


async def test_postgres_charges_one_completed_session_once_under_concurrency(
    postgres_dsn: str,
) -> None:
    class FixedClock:
        current = datetime.datetime(2037, 1, 15, 12, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    workstation_id = None
    client_id = None
    tariff_id = None
    session_id = None
    try:
        clock = FixedClock()
        workstation_repository = PostgresWorkstationRepository(lambda: engine)
        workstation = await WorkstationService(workstation_repository).register(
            f"pg-billing-{uuid.uuid4()}",
            "PostgreSQL billing test PC",
            group_id="pg-billing-zone",
        )
        workstation_id = workstation.id

        client_repository = PostgresClientRepository(lambda: engine)
        client_service = ClientService(client_repository, clock=clock)
        client = await client_service.create(f"PgBilling{uuid.uuid4().hex[:12]}")
        client_id = client.id
        await client_service.top_up(
            client.id,
            amount_cents=1_000,
            bonus_amount=0,
            reason="Billing test balance",
            actor_id="integration-test",
            idempotency_key=f"pg-billing-deposit-{uuid.uuid4()}",
        )

        catalog_repository = PostgresCatalogRepository(lambda: engine)
        catalog = CatalogService(catalog_repository)
        tariff = await catalog.create_tariff(
            "PG billing hour",
            "pg-billing-zone",
            duration_minutes=60,
            price_cents=500,
            valid_from=clock.current,
            valid_to=None,
        )
        tariff_id = tariff.id

        session_repository = PostgresSessionRepository(lambda: engine)
        sessions = SessionService(
            session_repository,
            workstations=workstation_repository,
            clients=client_repository,
            clock=clock,
        )
        started = await sessions.start(
            workstation.id,
            created_by="integration-test",
            client_id=client.id,
            idempotency_key=f"pg-billing-session-{uuid.uuid4()}",
        )
        session_id = started.id
        clock.current += datetime.timedelta(minutes=31)
        completed = await sessions.stop(started.id)

        billing = BillingService(
            PostgresChargeRepository(lambda: engine),
            sessions=session_repository,
            workstations=workstation_repository,
            clients=client_service,
            catalog=catalog,
            clock=clock,
            reconciliation=PostgresChargeReconciliationRepository(lambda: engine),
        )
        results = await asyncio.gather(
            billing.charge_session(completed.id, "integration-test", "pg-charge-1"),
            billing.charge_session(completed.id, "integration-test", "pg-charge-2"),
        )

        assert {charge.id for charge, _ in results} == {results[0][0].id}
        assert {charge.balance_operation_id for charge, _ in results} == {
            results[0][0].balance_operation_id
        }
        final_client = await client_service.get(client.id)
        assert final_client.balance_cents == 500
    finally:
        async with engine.begin() as connection:
            if session_id is not None:
                await connection.execute(
                    text("DELETE FROM billing_reconciliations WHERE session_id = :session_id"),
                    {"session_id": session_id},
                )
                await connection.execute(
                    text("DELETE FROM session_charges WHERE session_id = :session_id"),
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


async def test_postgres_serializes_conflicting_reservations(postgres_dsn: str) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    workstation_id = None
    client_id = None
    reservation_ids: list[uuid.UUID] = []
    try:
        workstation_repository = PostgresWorkstationRepository(lambda: engine)
        workstation_service = WorkstationService(workstation_repository)
        workstation = await workstation_service.register(
            f"pg-reservation-{uuid.uuid4()}",
            "PostgreSQL concurrency test PC",
        )
        workstation_id = workstation.id

        client_repository = PostgresClientRepository(lambda: engine)
        client = await ClientService(client_repository).create(
            f"PgReservation{uuid.uuid4().hex[:12]}"
        )
        client_id = client.id
        reservation_service = ReservationService(
            PostgresReservationRepository(lambda: engine),
            workstations=workstation_repository,
            clients=client_repository,
        )

        start_at = datetime.datetime(
            2035,
            1,
            15,
            18,
            tzinfo=datetime.UTC,
        )
        results = await asyncio.gather(
            *(
                reservation_service.create(
                    workstation_ids=[workstation.id],
                    start_at=start_at,
                    end_at=start_at + datetime.timedelta(hours=2),
                    created_by="integration-test",
                    client_id=client.id,
                )
                for _ in range(2)
            ),
            return_exceptions=True,
        )

        successful = [item for item in results if not isinstance(item, Exception)]
        conflicts = [item for item in results if isinstance(item, ApplicationError)]
        reservation_ids.extend(item.id for item in successful)
        assert len(successful) == 1
        assert len(conflicts) == 1
        assert conflicts[0].code is ErrorCode.CONFLICT
    finally:
        async with engine.begin() as connection:
            if reservation_ids:
                for reservation_id in reservation_ids:
                    await connection.execute(
                        text("DELETE FROM reservations WHERE id = :reservation_id"),
                        {"reservation_id": reservation_id},
                    )
            if client_id is not None:
                await connection.execute(
                    text("DELETE FROM clients WHERE id = :client_id"),
                    {"client_id": client_id},
                )
            if workstation_id is not None:
                await connection.execute(
                    text("DELETE FROM workstations WHERE id = :workstation_id"),
                    {"workstation_id": workstation_id},
                )
        await engine.dispose()


async def test_postgres_serializes_active_sessions_and_retries_by_key(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    workstation_id = None
    try:
        workstation_repository = PostgresWorkstationRepository(lambda: engine)
        workstation = await WorkstationService(workstation_repository).register(
            f"pg-session-{uuid.uuid4()}",
            "PostgreSQL session test PC",
        )
        workstation_id = workstation.id
        service = SessionService(
            PostgresSessionRepository(lambda: engine),
            workstations=workstation_repository,
            clients=PostgresClientRepository(lambda: engine),
        )

        repeated = await asyncio.gather(
            *(
                service.start(
                    workstation_id=workstation.id,
                    created_by="integration-test",
                    guest_name="Retry guest",
                    idempotency_key="pg-session-retry-001",
                )
                for _ in range(4)
            )
        )
        assert {item.id for item in repeated} == {repeated[0].id}

        stopped = await service.stop(repeated[0].id)
        assert stopped.status.value == "completed"

        results = await asyncio.gather(
            *(
                service.start(
                    workstation_id=workstation.id,
                    created_by="integration-test",
                    guest_name=f"Concurrent guest {index}",
                    idempotency_key=f"pg-session-distinct-{index}",
                )
                for index in range(2)
            ),
            return_exceptions=True,
        )
        successful = [item for item in results if not isinstance(item, Exception)]
        conflicts = [item for item in results if isinstance(item, ApplicationError)]
        assert len(successful) == 1
        assert len(conflicts) == 1
        assert conflicts[0].code is ErrorCode.CONFLICT
    finally:
        async with engine.begin() as connection:
            if workstation_id is not None:
                await connection.execute(
                    text("DELETE FROM gaming_sessions WHERE workstation_id = :workstation_id"),
                    {"workstation_id": workstation_id},
                )
                await connection.execute(
                    text("DELETE FROM workstations WHERE id = :workstation_id"),
                    {"workstation_id": workstation_id},
                )
        await engine.dispose()


async def test_postgres_cash_shift_serializes_open_and_distinct_movements(
    postgres_dsn: str,
) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    shift_id = None
    try:
        service = CashShiftService(PostgresCashShiftRepository(lambda: engine))
        shift = await service.open(
            register_id=f"pg-register-{uuid.uuid4()}",
            opening_balance_cents=0,
            opened_by="integration-test",
            idempotency_key=f"pg-cash-open-{uuid.uuid4()}",
        )
        shift_id = shift.id
        results = await asyncio.gather(
            *(
                service.record_movement(
                    shift.id,
                    "cash_in",
                    100,
                    "Concurrent cash movement",
                    "integration-test",
                    f"pg-cash-movement-{uuid.uuid4()}",
                )
                for _ in range(8)
            )
        )
        assert len({movement.id for _, movement in results}) == 8
        final_shift = await service.get(shift.id)
        assert final_shift.expected_close_cents == 800

        repeated = await service.open(
            register_id=shift.register_id,
            opening_balance_cents=0,
            opened_by="integration-test",
            idempotency_key=shift.open_idempotency_key,
        )
        assert repeated.id == shift.id
    finally:
        async with engine.begin() as connection:
            if shift_id is not None:
                await connection.execute(
                    text("DELETE FROM cash_movements WHERE shift_id = :shift_id"),
                    {"shift_id": shift_id},
                )
                await connection.execute(
                    text("DELETE FROM cash_shifts WHERE id = :shift_id"),
                    {"shift_id": shift_id},
                )
        await engine.dispose()


async def test_postgres_cash_movement_reference_is_unique(postgres_dsn: str) -> None:
    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    shift_id = None
    try:
        service = CashShiftService(PostgresCashShiftRepository(lambda: engine))
        shift = await service.open(
            register_id=f"pg-reference-register-{uuid.uuid4()}",
            opening_balance_cents=0,
            opened_by="integration-test",
            idempotency_key=f"pg-reference-open-{uuid.uuid4()}",
        )
        shift_id = shift.id
        reference_id = f"payment-{uuid.uuid4()}"
        await service.record_movement(
            shift.id,
            "cash_in",
            100,
            "External payment",
            "integration-test",
            f"pg-reference-movement-{uuid.uuid4()}",
            reference_type="external_payment",
            reference_id=reference_id,
        )
        with pytest.raises(ApplicationError) as error:
            await service.record_movement(
                shift.id,
                "cash_in",
                100,
                "Duplicate external payment",
                "integration-test",
                f"pg-reference-duplicate-{uuid.uuid4()}",
                reference_type="external_payment",
                reference_id=reference_id,
            )
        assert error.value.code is ErrorCode.CONFLICT
    finally:
        async with engine.begin() as connection:
            if shift_id is not None:
                await connection.execute(
                    text("DELETE FROM cash_movements WHERE shift_id = :shift_id"),
                    {"shift_id": shift_id},
                )
                await connection.execute(
                    text("DELETE FROM cash_shifts WHERE id = :shift_id"),
                    {"shift_id": shift_id},
                )
        await engine.dispose()
