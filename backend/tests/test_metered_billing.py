import asyncio
import datetime
import uuid

import pytest

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.domain import MeterStatus
from gameclub_backend.modules.billing.infrastructure.memory import (
    InMemoryChargeRepository,
    InMemoryMeterRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import BillingMode
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime.datetime(2026, 8, 29, 12, tzinfo=datetime.UTC)

    def now(self) -> datetime.datetime:
        return self.current


async def build_metered_services(clock: FixedClock):
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "meter-device", "Meter PC", group_id="vip"
    )
    client_repository = InMemoryClientRepository()
    clients = ClientService(client_repository, clock=clock)
    client = await clients.create("MeterFox")
    await clients.top_up(
        client.id,
        amount_cents=1_000,
        bonus_amount=0,
        reason="Meter test",
        actor_id="operator",
        idempotency_key="meter-deposit-" + uuid.uuid4().hex,
    )
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "VIP minute",
        "vip",
        duration_minutes=1,
        price_cents=0,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=10,
        free_minutes=5,
    )
    session_repository = InMemorySessionRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
    )
    meter_repository = InMemoryMeterRepository()
    billing = BillingService(
        InMemoryChargeRepository(),
        sessions=session_repository,
        workstations=workstation_repository,
        clients=clients,
        catalog=catalog,
        clock=clock,
        meter_repository=meter_repository,
    )
    return workstation, client, tariff, sessions, billing, meter_repository, clients


@pytest.mark.asyncio
async def test_metered_session_charges_only_delta_after_free_minutes() -> None:
    clock = FixedClock()
    workstation, client, tariff, sessions, billing, meters, clients = await build_metered_services(
        clock
    )
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        tariff_id=tariff.id,
        idempotency_key="meter-session-1",
    )

    clock.current += datetime.timedelta(minutes=5)
    free = await billing.meter_session(session.id)
    assert free is not None
    assert free.billed_minutes == 0
    assert free.billed_cents == 0

    clock.current += datetime.timedelta(minutes=2)
    first = await billing.meter_session(session.id)
    repeated = await billing.meter_session(session.id)
    assert first is not None and repeated is not None
    assert first.billed_minutes == repeated.billed_minutes == 2
    assert first.billed_cents == repeated.billed_cents == 20
    assert (await clients.get(client.id)).balance_cents == 980

    completed = await sessions.stop(session.id)
    charge, charged_client = await billing.charge_session(
        completed.id,
        charged_by="operator",
        idempotency_key="meter-charge-1",
    )
    assert charge.amount_cents == 20
    assert charged_client.balance_cents == 980
    assert (await meters.get(session.id)).status is MeterStatus.SETTLED


@pytest.mark.asyncio
async def test_metered_session_becomes_exhausted_without_overdraft() -> None:
    clock = FixedClock()
    workstation, client, tariff, sessions, billing, meters, clients = await build_metered_services(
        clock
    )
    await clients.debit(
        client.id,
        amount_cents=990,
        reason="Prepare low balance",
        actor_id="operator",
        idempotency_key="meter-low-balance",
    )
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        tariff_id=tariff.id,
        idempotency_key="meter-session-2",
    )
    clock.current += datetime.timedelta(minutes=6)
    await billing.meter_session(session.id)
    clock.current += datetime.timedelta(minutes=1)
    with pytest.raises(ApplicationError, match="Insufficient balance"):
        await billing.meter_session(session.id)
    meter = await meters.get(session.id)
    assert meter is not None and meter.status is MeterStatus.EXHAUSTED
    assert (await clients.get(client.id)).balance_cents == 0


@pytest.mark.asyncio
async def test_concurrent_metering_is_serialized_per_session() -> None:
    clock = FixedClock()
    workstation, client, tariff, sessions, billing, meters, clients = await build_metered_services(
        clock
    )
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        tariff_id=tariff.id,
        idempotency_key="meter-session-concurrent",
    )
    clock.current += datetime.timedelta(minutes=7)

    first, second = await asyncio.gather(
        billing.meter_session(session.id),
        billing.meter_session(session.id),
    )

    assert first is not None and second is not None
    assert first.billed_minutes == second.billed_minutes == 2
    assert first.billed_cents == second.billed_cents == 20
    assert (await clients.get(client.id)).balance_cents == 980
    assert (await meters.get(session.id)).billed_cents == 20
