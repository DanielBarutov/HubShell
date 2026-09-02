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
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.entitlements.infrastructure.memory import (
    InMemoryEntitlementRepository,
)
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
    meter_repository = InMemoryMeterRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
    )
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


async def build_package_metered_services(
    clock: FixedClock,
    duration_minutes: int = 3,
    window_start_minute: int | None = None,
    window_end_minute: int | None = None,
    window_timezone: str | None = None,
):
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "package-device", "Package PC", group_id="vip"
    )
    client_repository = InMemoryClientRepository()
    clients = ClientService(client_repository, clock=clock)
    client = await clients.create("PackageFox")
    await clients.top_up(
        client.id,
        amount_cents=1_000,
        bonus_amount=0,
        reason="Package meter test",
        actor_id="operator",
        idempotency_key="package-meter-deposit",
    )
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "VIP package",
        "vip",
        duration_minutes=duration_minutes,
        price_cents=100,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.BLOCK,
        window_start_minute=window_start_minute,
        window_end_minute=window_end_minute,
        window_timezone=window_timezone,
    )
    session_repository = InMemorySessionRepository()
    meter_repository = InMemoryMeterRepository()
    entitlement_repository = InMemoryEntitlementRepository()
    entitlements = EntitlementService(
        entitlement_repository,
        tariffs=catalog,
        clients=clients,
        clock=clock,
        active_sessions=session_repository,
        workstations=workstation_repository,
    )
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
        entitlements=entitlements,
        meters=meter_repository,
    )
    billing = BillingService(
        InMemoryChargeRepository(),
        sessions=session_repository,
        workstations=workstation_repository,
        clients=clients,
        catalog=catalog,
        clock=clock,
        meter_repository=meter_repository,
        entitlements=entitlements,
    )
    return (
        workstation,
        client,
        tariff,
        sessions,
        billing,
        meter_repository,
        clients,
        entitlements,
    )


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
async def test_device_login_adds_separate_five_minute_grant() -> None:
    clock = FixedClock()
    workstation, client, tariff, sessions, billing, _meters, clients = await build_metered_services(
        clock
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        tariff_id=tariff.id,
        idempotency_key="meter-device-session-1",
    )

    assert session.login_grant_minutes == 5
    clock.current += datetime.timedelta(minutes=10)
    meter = await billing.meter_session(session.id)

    assert meter is not None
    assert meter.billed_minutes == 0
    assert (await clients.get(client.id)).balance_cents == 1_000


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


@pytest.mark.asyncio
async def test_package_meter_auto_advances_and_stop_burns_only_active_remainder() -> None:
    clock = FixedClock()
    (
        workstation,
        client,
        tariff,
        sessions,
        billing,
        meters,
        clients,
        entitlements,
    ) = await build_package_metered_services(clock)
    first = await entitlements.purchase(client.id, tariff.id, "operator", "package-1")
    second = await entitlements.purchase(client.id, tariff.id, "operator", "package-2")
    third = await entitlements.purchase(client.id, tariff.id, "operator", "package-3")
    await entitlements.activate(first.id, client.id)
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="package-session-1",
    )

    clock.current += datetime.timedelta(minutes=2)
    first_tick = await billing.meter_session(session.id)
    assert first_tick is not None
    assert first_tick.package_minutes == 2
    assert first_tick.billed_minutes == first_tick.billed_cents == 0
    assert (await clients.get(client.id)).balance_cents == 700

    clock.current += datetime.timedelta(minutes=2)
    second_tick = await billing.meter_session(session.id)
    assert second_tick is not None
    assert second_tick.package_minutes == 4
    assert second_tick.active_entitlement_id == second.id
    assert (await entitlements.get(first.id)).status is EntitlementStatus.EXHAUSTED
    assert (await entitlements.get(second.id)).remaining_minutes == 2

    completed = await sessions.stop(session.id)
    assert (await entitlements.get(second.id)).status is EntitlementStatus.BURNED
    assert (await entitlements.get(third.id)).status is EntitlementStatus.QUEUED
    assert (await clients.get(client.id)).balance_cents == 700
    assert (await meters.get(session.id)).package_minutes == 4
    charge, charged_client = await billing.charge_session(
        completed.id,
        charged_by="operator",
        idempotency_key="package-charge-1",
    )
    assert charge.amount_cents == 0
    assert charged_client.balance_cents == 700
    assert (await meters.get(session.id)).status is MeterStatus.SETTLED


@pytest.mark.asyncio
async def test_package_purchased_during_uncovered_active_session_activates_immediately() -> None:
    clock = FixedClock()
    (
        workstation,
        client,
        tariff,
        sessions,
        billing,
        _meters,
        _clients,
        entitlements,
    ) = await build_package_metered_services(clock)
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="package-session-immediate",
    )

    clock.current += datetime.timedelta(minutes=10)
    purchased = await entitlements.purchase(client.id, tariff.id, "operator", "package-live")
    assert (await entitlements.get_active_for_client(client.id)).id == purchased.id

    clock.current += datetime.timedelta(minutes=1)
    meter = await billing.meter_session(session.id)
    assert meter is not None
    assert meter.package_minutes == 1
    assert meter.billed_minutes == 0


@pytest.mark.asyncio
async def test_windowed_package_consumes_only_minutes_inside_local_window() -> None:
    clock = FixedClock()
    clock.current = datetime.datetime(2026, 8, 29, 18, tzinfo=datetime.UTC)
    (
        _workstation,
        client,
        tariff,
        sessions,
        billing,
        meters,
        _clients,
        entitlements,
    ) = await build_package_metered_services(
        clock,
        duration_minutes=60,
        window_start_minute=22 * 60,
        window_end_minute=6 * 60,
        window_timezone="Europe/Moscow",
    )
    package = await entitlements.purchase(client.id, tariff.id, "operator", "night-meter")
    session = await sessions.start(
        workstation_id=_workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="night-meter-session",
    )

    clock.current += datetime.timedelta(hours=8, minutes=30)
    await entitlements.activate(package.id, client.id)
    clock.current += datetime.timedelta(minutes=60)
    first_tick = await billing.meter_session(session.id)
    assert first_tick is not None
    assert first_tick.package_minutes == 30

    clock.current += datetime.timedelta(minutes=60)
    outside = await billing.meter_session(session.id)
    assert outside is None
    assert (await meters.get(session.id)).package_minutes == 30


@pytest.mark.asyncio
async def test_session_snapshot_exposes_server_time_package_queue_and_meter() -> None:
    clock = FixedClock()
    (
        workstation,
        client,
        tariff,
        sessions,
        billing,
        _meters,
        _clients,
        entitlements,
    ) = await build_package_metered_services(clock)
    package = await entitlements.purchase(client.id, tariff.id, "operator", "snapshot-package")
    await entitlements.activate(package.id, client.id)
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="snapshot-session",
    )
    clock.current += datetime.timedelta(minutes=1)
    await billing.meter_session(session.id)

    snapshot = await sessions.snapshot(session.id)
    assert snapshot.schema_version == 1
    assert snapshot.server_time == clock.current
    assert snapshot.zone_id == "vip"
    assert snapshot.balance_cents == 900
    assert snapshot.active_entitlement is not None
    assert snapshot.active_entitlement.id == package.id
    assert snapshot.meter is not None
    assert snapshot.meter.package_minutes == 1
    assert snapshot.allowed_actions == ("stop",)


@pytest.mark.asyncio
async def test_package_time_window_uses_configured_timezone() -> None:
    clock = FixedClock()
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Night package",
        "vip",
        duration_minutes=60,
        price_cents=100,
        valid_from=clock.current,
        valid_to=None,
        window_start_minute=22 * 60,
        window_end_minute=6 * 60,
        window_timezone="Europe/Moscow",
    )
    clients = ClientService(InMemoryClientRepository(), clock=clock)
    client = await clients.create("NightFox")
    await clients.top_up(
        client.id,
        amount_cents=200,
        bonus_amount=0,
        reason="Night package test",
        actor_id="operator",
        idempotency_key="night-deposit",
    )
    entitlements = EntitlementService(
        InMemoryEntitlementRepository(),
        tariffs=catalog,
        clients=clients,
        clock=clock,
    )
    item = await entitlements.purchase(client.id, tariff.id, "operator", "night-package")
    assert await entitlements.next_compatible(client.id, "vip", now=clock.current) is None

    clock.current = datetime.datetime(2026, 8, 29, 19, tzinfo=datetime.UTC)
    assert (await entitlements.next_compatible(client.id, "vip", now=clock.current)).id == item.id
    assert (await entitlements.activate(item.id, client.id)).status is EntitlementStatus.ACTIVE
