import asyncio
import datetime
import json
import logging
import uuid

import pytest

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.jobs.billing import meter_sessions_once
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.domain import MeterStatus
from gameclub_backend.modules.billing.infrastructure.memory import (
    InMemoryChargeRepository,
    InMemoryMeterRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import BillingMode
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.client_groups.application.service import ClientGroupService
from gameclub_backend.modules.client_groups.infrastructure.memory import (
    InMemoryClientGroupRepository,
)
from gameclub_backend.modules.clients.application.portal import ClientPortalService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.direct_payments.application.service import GuestSessionPaymentService
from gameclub_backend.modules.direct_payments.infrastructure.memory import (
    InMemoryGuestSessionPaymentRepository,
)
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import (
    EntitlementSettlementStatus,
    EntitlementStatus,
)
from gameclub_backend.modules.entitlements.infrastructure.memory import (
    InMemoryEntitlementRepository,
)
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.sessions.presentation.http import SessionSnapshotResponse
from gameclub_backend.modules.workstations.application.commands import WorkstationCommandService
from gameclub_backend.modules.workstations.application.groups import WorkstationGroupService
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationGroup
from gameclub_backend.modules.workstations.domain_commands import WorkstationCommandStatus
from gameclub_backend.modules.workstations.infrastructure.commands_memory import (
    InMemoryCommandNotifier,
    InMemoryWorkstationCommandRepository,
)
from gameclub_backend.modules.workstations.infrastructure.groups_memory import (
    InMemoryWorkstationGroupRepository,
)
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.presentation.grpc.services import to_session_snapshot_proto

pytestmark = [pytest.mark.unit, pytest.mark.concurrency]


class FixedClock:
    def __init__(self) -> None:
        self.current = datetime.datetime(2026, 8, 29, 12, tzinfo=datetime.UTC)

    def now(self) -> datetime.datetime:
        return self.current


class EmptyChargeHistory:
    async def list_charges_for_client(self, client_id: uuid.UUID, limit: int):
        del client_id, limit
        return []


class NoopCashSettlement:
    async def settle(
        self,
        shift_id: uuid.UUID,
        amount_cents: int,
        payment_idempotency_key: str,
        actor_id: str,
    ) -> None:
        del shift_id, amount_cents, payment_idempotency_key, actor_id


class ReviewCashSettlement(NoopCashSettlement):
    def __init__(self) -> None:
        self.fail = True
        self.calls: list[str] = []

    async def settle(
        self,
        shift_id: uuid.UUID,
        amount_cents: int,
        payment_idempotency_key: str,
        actor_id: str,
    ) -> None:
        del shift_id, amount_cents, actor_id
        self.calls.append(payment_idempotency_key)
        if self.fail:
            raise RuntimeError("cash acceptance is unknown")


async def build_metered_services(
    clock: FixedClock,
    tariff_free_minutes: int = 5,
    price_per_minute_cents: int = 10,
    initial_balance_cents: int = 1_000,
    create_per_minute_tariff: bool = True,
    client_groups=None,
):
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "meter-device", "Meter PC", group_id="vip"
    )
    client_repository = InMemoryClientRepository()
    clients = ClientService(client_repository, clock=clock, groups=client_groups)
    client = await clients.create("MeterFox")
    if initial_balance_cents:
        await clients.top_up(
            client.id,
            amount_cents=initial_balance_cents,
            bonus_amount=0,
            reason="Meter test",
            actor_id="operator",
            idempotency_key="meter-deposit-" + uuid.uuid4().hex,
        )
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = None
    if create_per_minute_tariff:
        tariff = await catalog.create_tariff(
            "VIP minute",
            "vip",
            duration_minutes=1,
            price_cents=0,
            valid_from=clock.current,
            valid_to=None,
            billing_mode=BillingMode.PER_MINUTE,
            price_per_minute_cents=price_per_minute_cents,
            free_minutes=tariff_free_minutes,
        )
    session_repository = InMemorySessionRepository()
    meter_repository = InMemoryMeterRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
        tariffs=catalog,
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
    time_restricted: bool = False,
    sale_window_start_minute: int | None = None,
    sale_window_end_minute: int | None = None,
    usage_window_start_minute: int | None = None,
    usage_window_end_minute: int | None = None,
    window_timezone: str | None = None,
    cash_settlement=None,
    return_catalog: bool = False,
    client_groups=None,
    client_group_id: str | None = None,
    initial_balance_cents: int = 1_000,
    tariff_price_cents: int = 100,
    activate_package_on_purchase: bool = True,
):
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "package-device", "Package PC", group_id="vip"
    )
    client_repository = InMemoryClientRepository()
    clients = ClientService(client_repository, clock=clock, groups=client_groups)
    client = await clients.create("PackageFox", client_group_id=client_group_id)
    if initial_balance_cents:
        await clients.top_up(
            client.id,
            amount_cents=initial_balance_cents,
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
        price_cents=tariff_price_cents,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.BLOCK,
        time_restricted=time_restricted,
        sale_window_start_minute=sale_window_start_minute,
        sale_window_end_minute=sale_window_end_minute,
        usage_window_start_minute=usage_window_start_minute,
        usage_window_end_minute=usage_window_end_minute,
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
        active_sessions=session_repository if activate_package_on_purchase else None,
        workstations=workstation_repository if activate_package_on_purchase else None,
        cash=cash_settlement,
    )
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
        entitlements=entitlements,
        meters=meter_repository,
        tariffs=catalog,
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
    result = (
        workstation,
        client,
        tariff,
        sessions,
        billing,
        meter_repository,
        clients,
        entitlements,
    )
    return (*result, catalog) if return_catalog else result


@pytest.mark.asyncio
async def test_metered_session_charges_only_delta_after_free_minutes() -> None:
    """
    Проверяет сценарий «test_metered_session_charges_only_delta_after_free_minutes» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_device_login_adds_separate_five_minute_grant» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    assert (await sessions.snapshot(session.id)).login_grant_remaining_minutes == 5
    clock.current += datetime.timedelta(minutes=2)
    assert (await sessions.snapshot(session.id)).login_grant_remaining_minutes == 3
    clock.current += datetime.timedelta(minutes=8)
    meter = await billing.meter_session(session.id)

    assert meter is not None
    assert meter.billed_minutes == 0
    assert (await clients.get(client.id)).balance_cents == 1_000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("create_per_minute_tariff", "expected_reason"),
    (
        pytest.param(True, "balance_exhausted", id="ставка-есть-денег-нет"),
        pytest.param(False, "time_exhausted", id="ставка-выключена"),
    ),
)
async def test_regular_device_session_stops_exactly_after_five_free_minutes(
    create_per_minute_tariff: bool,
    expected_reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Проверяет остановку обычной сессии на пятой минуте без пакета и доступных денег."""
    clock = FixedClock()
    (
        workstation,
        client,
        _tariff,
        sessions,
        billing,
        _meters,
        _clients,
    ) = await build_metered_services(
        clock,
        tariff_free_minutes=0,
        initial_balance_cents=0,
        create_per_minute_tariff=create_per_minute_tariff,
    )
    commands = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=sessions._workstations,
        notifier=InMemoryCommandNotifier(),
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key=f"free-session-stop-{expected_reason}",
    )

    clock.current = session.started_at + datetime.timedelta(minutes=5)

    with caplog.at_level(logging.WARNING, logger="gameclub_backend.jobs.billing"):
        assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 1
    assert (await sessions.get(session.id)).status.value == "completed"
    assert f"session_meter_stopped session_id={session.id}" in caplog.text
    assert f"reason={expected_reason}" in caplog.text
    expected_error = (
        "Insufficient balance"
        if expected_reason == "balance_exhausted"
        else "Session time exhausted"
    )
    assert f"error={expected_error}" in caplog.text
    pending = await commands.pending_for_device(workstation.device_id)
    assert [command.command_type for command in pending] == ["session.stop", "display.lock"]
    assert {json.loads(command.payload_json)["reason"] for command in pending} == {expected_reason}


@pytest.mark.asyncio
async def test_debtor_starts_per_minute_billing_after_five_free_minutes() -> None:
    """
    Проверяет, что клиент группы с долгом не выходит на пятой бесплатной минуте,
    а на шестой получает первое поминутное списание в пределах лимита долга.
    """
    clock = FixedClock()
    groups = InMemoryClientGroupRepository()
    await ClientGroupService(groups, clock=clock).create(
        "debtors",
        "Должники",
        allow_negative_balance=True,
        negative_balance_limit_cents=60_000,
    )
    (
        workstation,
        client,
        _tariff,
        sessions,
        billing,
        meters,
        clients,
    ) = await build_metered_services(
        clock,
        tariff_free_minutes=0,
        price_per_minute_cents=1_000,
        initial_balance_cents=0,
        client_groups=groups,
    )
    await clients.update(client.id, "MeterFox", client_group_id="debtors")
    commands = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=sessions._workstations,
        notifier=InMemoryCommandNotifier(),
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="debtor-five-free-minutes",
    )

    clock.current = session.started_at + datetime.timedelta(minutes=5)

    assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 0
    assert (await sessions.get(session.id)).status.value == "active"
    assert (await clients.get(client.id)).balance_cents == 0
    assert await commands.pending_for_device(workstation.device_id) == []

    clock.current += datetime.timedelta(minutes=1)

    assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 0
    assert (await sessions.get(session.id)).status.value == "active"
    assert (await clients.get(client.id)).balance_cents == -1_000
    assert (await meters.get(session.id)).billed_minutes == 1
    assert await commands.pending_for_device(workstation.device_id) == []


@pytest.mark.asyncio
async def test_device_login_selects_zone_per_minute_tariff_without_package() -> None:
    """
    Проверяет сценарий «test_device_login_selects_zone_per_minute_tariff_without_package» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clock = FixedClock()
    workstation, client, tariff, sessions, billing, meters, clients = await build_metered_services(
        clock,
        tariff_free_minutes=0,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="meter-device-zone-tariff",
    )

    assert session.tariff_id == tariff.id
    snapshot = await sessions.snapshot(session.id)
    assert snapshot.active_tariff is not None
    assert snapshot.active_tariff.id == tariff.id
    assert snapshot.active_tariff.price_per_minute_cents == tariff.price_per_minute_cents
    assert snapshot.active_tariff.free_minutes == tariff.free_minutes

    clock.current += datetime.timedelta(minutes=6)
    meter = await billing.meter_session(session.id)

    assert meter is not None
    assert meter.billed_minutes == 1
    assert meter.billed_cents == 10
    assert (await clients.get(client.id)).balance_cents == 990
    assert (await meters.get(session.id)).tariff_id == tariff.id


@pytest.mark.asyncio
async def test_existing_zone_rate_starts_metering_after_five_free_minutes() -> None:
    """
    Проверяет, что старая зона со ставкой 10 ₽/мин после запуска восстанавливает
    внутренний тариф: баланс 100 ₽ показывает 10 минут, а на шестой минуте
    списывается первые 10 ₽ без остановки ПК.
    """
    clock = FixedClock()
    groups = InMemoryWorkstationGroupRepository()
    await groups.save(
        WorkstationGroup(
            id="vip",
            name="VIP-зона",
            theme="vip",
            per_minute_price_cents=1_000,
            updated_at=clock.now(),
        )
    )
    catalog = CatalogService(InMemoryCatalogRepository(), zones=groups)
    group_service = WorkstationGroupService(
        groups,
        clock=clock,
        zone_rate_synchronizer=catalog,
    )
    await group_service.restore_per_minute_tariffs()

    tariff = await catalog.find_per_minute_tariff("vip", clock.now())
    assert tariff is not None
    assert tariff.price_per_minute_cents == 1_000

    workstations = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstations, groups=groups).register(
        "restored-rate-device",
        "VIP-01",
        group_id="vip",
    )
    client_repository = InMemoryClientRepository()
    clients = ClientService(client_repository, clock=clock)
    client = await clients.create("RestoredRateFox")
    await clients.top_up(
        client.id,
        amount_cents=10_000,
        bonus_amount=0,
        reason="Баланс для поминутной игры",
        actor_id="operator",
        idempotency_key="restored-rate-deposit",
    )
    session_repository = InMemorySessionRepository()
    meters = InMemoryMeterRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstations,
        clients=client_repository,
        clock=clock,
        tariffs=catalog,
    )
    billing = BillingService(
        InMemoryChargeRepository(),
        sessions=session_repository,
        workstations=workstations,
        clients=clients,
        catalog=catalog,
        clock=clock,
        meter_repository=meters,
    )
    commands = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=workstations,
        notifier=InMemoryCommandNotifier(),
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="restored-rate-session",
    )

    assert session.tariff_id == tariff.id
    assert (await sessions.snapshot(session.id)).balance_remaining_minutes == 10

    clock.current = session.started_at + datetime.timedelta(minutes=5)
    assert await meter_sessions_once(billing, session_repository, sessions, commands) == 0
    assert (await sessions.get(session.id)).status.value == "active"
    assert (await clients.get(client.id)).balance_cents == 10_000

    clock.current += datetime.timedelta(minutes=1)
    meter = await billing.meter_session(session.id)

    assert meter is not None
    assert meter.billed_minutes == 1
    assert meter.billed_cents == 1_000
    assert (await clients.get(client.id)).balance_cents == 9_000
    assert (await sessions.snapshot(session.id)).balance_remaining_minutes == 9


@pytest.mark.asyncio
async def test_metering_replaces_archived_legacy_minute_tariff_with_current_zone_snapshot() -> None:
    """
    Проверяет сценарий
    «test_metering_replaces_archived_legacy_minute_tariff_with_current_zone_snapshot» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clock = FixedClock()
    (
        workstation,
        client,
        old_tariff,
        sessions,
        billing,
        meters,
        clients,
    ) = await build_metered_services(clock, tariff_free_minutes=0)
    catalog = billing._catalog
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        tariff_id=old_tariff.id,
        idempotency_key="meter-legacy-archived-tariff",
    )
    await catalog._repository.save_tariff(old_tariff.archive())
    clock.current += datetime.timedelta(minutes=6)
    replacement = await catalog.create_tariff(
        "VIP current minute",
        "vip",
        duration_minutes=1,
        price_cents=0,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=25,
        free_minutes=0,
    )
    meter = await billing.meter_session(session.id)

    assert meter is not None
    assert meter.tariff_id == replacement.id
    assert meter.billed_minutes == 6
    assert meter.billed_cents == 150
    assert (await clients.get(client.id)).balance_cents == 850
    assert (await meters.get(session.id)).tariff_id == replacement.id


@pytest.mark.asyncio
async def test_repeated_device_login_returns_the_same_grant() -> None:
    """
    Проверяет сценарий «test_repeated_device_login_returns_the_same_grant» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clock = FixedClock()
    (
        workstation,
        client,
        tariff,
        sessions,
        _billing,
        _meters,
        _clients,
    ) = await build_metered_services(clock)
    first = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        tariff_id=tariff.id,
        idempotency_key="meter-device-session-repeat",
    )
    repeated = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        tariff_id=tariff.id,
        idempotency_key="meter-device-session-repeat",
    )

    assert repeated.id == first.id
    assert repeated.login_grant_minutes == first.login_grant_minutes == 5


@pytest.mark.asyncio
async def test_metered_session_becomes_exhausted_without_overdraft() -> None:
    """
    Проверяет сценарий «test_metered_session_becomes_exhausted_without_overdraft» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    stopped = await sessions.get(session.id)
    assert stopped.status.value == "completed"
    meter = await meters.get(session.id)
    assert meter is not None and meter.status is MeterStatus.EXHAUSTED
    assert (await clients.get(client.id)).balance_cents == 0


@pytest.mark.asyncio
async def test_concurrent_metering_is_serialized_per_session() -> None:
    """
    Проверяет сценарий «test_concurrent_metering_is_serialized_per_session» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_package_meter_auto_advances_and_stop_burns_only_active_remainder» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий
    «test_package_purchased_during_uncovered_active_session_activates_immediately» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
async def test_regular_package_starts_after_login_grant_and_returns_win_snapshot() -> None:
    """Проверяет, что обычный клиент не тратит пакет первые пять минут и видит это в gRPC-снимке."""
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
    ) = await build_package_metered_services(clock, duration_minutes=300)
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="regular-package-session",
    )

    purchased = await entitlements.purchase(
        client.id,
        tariff.id,
        "operator",
        "regular-package-purchase",
    )
    just_purchased = to_session_snapshot_proto(await sessions.snapshot(session.id))

    assert just_purchased.login_grant_remaining_minutes == 5
    assert just_purchased.active_package.id == str(purchased.id)
    assert just_purchased.active_package.tariff_name == "VIP package"
    assert just_purchased.active_package.remaining_minutes == 300

    clock.current += datetime.timedelta(minutes=5)
    at_grant_boundary = await billing.meter_session(session.id)
    boundary_snapshot = to_session_snapshot_proto(await sessions.snapshot(session.id))

    assert at_grant_boundary is None
    assert boundary_snapshot.login_grant_remaining_minutes == 0
    assert boundary_snapshot.active_package.remaining_minutes == 300
    assert boundary_snapshot.meter.package_minutes == 0
    assert boundary_snapshot.meter.billed_cents == 0

    clock.current += datetime.timedelta(minutes=1)
    after_grant = await billing.meter_session(session.id)
    after_grant_snapshot = to_session_snapshot_proto(await sessions.snapshot(session.id))

    assert after_grant is not None
    assert after_grant.package_minutes == 1
    assert after_grant.billed_cents == 0
    assert after_grant_snapshot.login_grant_remaining_minutes == 0
    assert after_grant_snapshot.active_package.remaining_minutes == 299
    assert after_grant_snapshot.meter.package_minutes == 1
    assert after_grant_snapshot.meter.active_entitlement_id == str(purchased.id)


@pytest.mark.asyncio
async def test_package_bought_during_free_minutes_prevents_vip_worker_from_stopping_session(
) -> None:
    """Проверяет, что купленный до конца бесплатных минут VIP-пакет не даёт
    фоновой задаче перезагрузить ПК.
    """
    clock = FixedClock()
    (
        workstation,
        client,
        package_tariff,
        sessions,
        billing,
        _meters,
        _clients,
        entitlements,
        catalog,
    ) = await build_package_metered_services(
        clock,
        duration_minutes=300,
        initial_balance_cents=1_000,
        tariff_price_cents=100,
        return_catalog=True,
    )
    await catalog.create_tariff(
        "VIP · Поминутно",
        "vip",
        duration_minutes=1,
        price_cents=0,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=10,
    )
    commands = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=sessions._workstations,
        notifier=InMemoryCommandNotifier(),
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="vip-package-during-free-minutes",
    )
    purchased = await entitlements.purchase(
        client.id,
        package_tariff.id,
        "operator",
        "vip-package-during-free-minutes-purchase",
    )

    clock.current = session.started_at + datetime.timedelta(minutes=5)

    assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 0
    assert (await sessions.get(session.id)).status.value == "active"
    assert (await entitlements.get(purchased.id)).remaining_minutes == 300
    assert await commands.pending_for_device(workstation.device_id) == []

    clock.current += datetime.timedelta(minutes=1)

    assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 0
    assert (await sessions.get(session.id)).status.value == "active"
    assert (await entitlements.get(purchased.id)).remaining_minutes == 299
    assert await commands.pending_for_device(workstation.device_id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("purchase_channel", ("client", "operator"))
async def test_queued_package_at_free_boundary_starts_before_vip_worker_can_stop_session(
    purchase_channel: str,
) -> None:
    """Проверяет, что пакет из клиента или окна продаж стартует до остановки VIP-сессии."""
    clock = FixedClock()
    (
        workstation,
        client,
        package_tariff,
        sessions,
        billing,
        _meters,
        _clients,
        entitlements,
        catalog,
    ) = await build_package_metered_services(
        clock,
        duration_minutes=300,
        initial_balance_cents=1_000,
        tariff_price_cents=100,
        return_catalog=True,
        activate_package_on_purchase=False,
    )
    await catalog.create_tariff(
        "VIP · Поминутно",
        "vip",
        duration_minutes=1,
        price_cents=0,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=10,
    )
    commands = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=sessions._workstations,
        notifier=InMemoryCommandNotifier(),
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key=f"queued-vip-package-{purchase_channel}",
    )
    if purchase_channel == "client":
        portal = ClientPortalService(
            clients=_clients,
            sessions=billing._sessions,
            charges=EmptyChargeHistory(),
            sales=ProductSaleService(
                InMemoryProductSaleRepository(),
                products=catalog,
                clients=_clients,
                clock=clock,
            ),
            tariffs=catalog,
            entitlements=entitlements,
            workstations=sessions._workstations,
            clock=clock,
        )
        await portal.purchase_entitlement(
            client.id,
            package_tariff.id,
            f"queued-vip-package-purchase-{purchase_channel}",
            workstation.device_id,
        )
    else:
        await entitlements.purchase(
            client.id,
            package_tariff.id,
            "operator:purchase",
            f"queued-vip-package-purchase-{purchase_channel}",
        )
    assert (await entitlements.get_active_for_client(client.id)) is None

    clock.current = session.started_at + datetime.timedelta(minutes=5)

    assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 0
    active = await entitlements.get_active_for_client(client.id)
    assert active is not None
    assert active.tariff_id == package_tariff.id
    assert active.remaining_minutes == 300
    assert (await sessions.get(session.id)).status.value == "active"
    assert await commands.pending_for_device(workstation.device_id) == []

    clock.current += datetime.timedelta(minutes=1)

    assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 0
    assert (await entitlements.get(active.id)).remaining_minutes == 299
    assert (await sessions.get(session.id)).status.value == "active"
    assert await commands.pending_for_device(workstation.device_id) == []


@pytest.mark.asyncio
async def test_three_hour_package_stays_active_at_two_hours_fifty_nine_remaining() -> None:
    """Проверяет переход с пяти бесплатных минут на трёхчасовой пакет без перезагрузки ПК."""
    clock = FixedClock()
    (
        workstation,
        client,
        package_tariff,
        sessions,
        billing,
        meters,
        clients,
        entitlements,
        catalog,
    ) = await build_package_metered_services(
        clock,
        duration_minutes=180,
        initial_balance_cents=1_000,
        tariff_price_cents=100,
        return_catalog=True,
    )
    await catalog.create_tariff(
        "VIP · Поминутно",
        "vip",
        duration_minutes=1,
        price_cents=0,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=10,
    )
    commands = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=sessions._workstations,
        notifier=InMemoryCommandNotifier(),
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="three-hour-package-session",
    )
    package = await entitlements.purchase(
        client.id,
        package_tariff.id,
        "operator",
        "three-hour-package-purchase",
    )
    assert (await clients.get(client.id)).balance_cents == 900

    expected_remaining = (
        (5, 180),
        (6, 179),  # 2 ч 59 мин: первая минута пакета уже списалась.
        (7, 178),
        (8, 177),
        (9, 176),
        (10, 175),
    )
    for elapsed, remaining_minutes in expected_remaining:
        clock.current = session.started_at + datetime.timedelta(minutes=elapsed)
        assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 0
        current_session = await sessions.get(session.id)
        current_package = await entitlements.get(package.id)
        current_client = await clients.get(client.id)
        current_meter = await meters.get(session.id)
        assert current_session is not None
        assert current_session.status.value == "active"
        assert current_package.status is EntitlementStatus.ACTIVE
        assert current_package.remaining_minutes == remaining_minutes
        assert current_client.balance_cents == 900
        assert current_meter is not None
        assert current_meter.billed_cents == 0
        assert current_meter.billed_minutes == 0
        assert current_meter.package_minutes == max(0, elapsed - 5)
        assert await commands.pending_for_device(workstation.device_id) == []


@pytest.mark.asyncio
async def test_three_minute_package_counts_each_minute_and_stops_device_at_zero_balance() -> None:
    """Проверяет пять бесплатных минут, расход трёх пакетных минут и команду остановки ПК."""
    clock = FixedClock()
    (
        workstation,
        client,
        package_tariff,
        sessions,
        billing,
        meters,
        clients,
        entitlements,
        catalog,
    ) = await build_package_metered_services(
        clock,
        duration_minutes=3,
        initial_balance_cents=100,
        tariff_price_cents=100,
        return_catalog=True,
    )
    await catalog.create_tariff(
        "VIP · Поминутно",
        "vip",
        duration_minutes=1,
        price_cents=0,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=10,
    )
    commands = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=sessions._workstations,
        notifier=InMemoryCommandNotifier(),
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="three-minute-package-session",
    )
    package = await entitlements.purchase(
        client.id,
        package_tariff.id,
        "operator",
        "three-minute-package-purchase",
    )

    assert (await clients.get(client.id)).balance_cents == 0
    expected_minutes = (
        (1, 4, 3),
        (2, 3, 3),
        (3, 2, 3),
        (4, 1, 3),
        (5, 0, 3),
        (6, 0, 2),
        (7, 0, 1),
    )
    for elapsed, expected_grant, expected_package in expected_minutes:
        clock.current = session.started_at + datetime.timedelta(minutes=elapsed)
        assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 0
        snapshot = await sessions.snapshot(session.id)
        assert snapshot.login_grant_remaining_minutes == expected_grant
        assert snapshot.active_entitlement is not None
        assert snapshot.active_entitlement.remaining_minutes == expected_package
        assert await commands.pending_for_device(workstation.device_id) == []

    clock.current = session.started_at + datetime.timedelta(minutes=8)
    assert await meter_sessions_once(billing, billing._sessions, sessions, commands) == 1

    assert (await entitlements.get(package.id)).status is EntitlementStatus.EXHAUSTED
    assert (await entitlements.get(package.id)).remaining_minutes == 0
    assert (await meters.get(session.id)).package_minutes == 3
    assert (await sessions.get(session.id)).status.value == "completed"
    assert (await sessions.snapshot(session.id)).active_entitlement is None
    pending = await commands.pending_for_device(workstation.device_id)
    assert [command.command_type for command in pending] == ["session.stop", "display.lock"]
    assert all(
        json.loads(command.payload_json)["session_id"] == str(session.id) for command in pending
    )
    acknowledged = await commands.acknowledge(
        pending[0].id,
        workstation.device_id,
        success=True,
        message="access gate opened",
    )
    assert acknowledged.status is WorkstationCommandStatus.ACKNOWLEDGED


@pytest.mark.asyncio
async def test_debtor_package_starts_after_login_grant_when_price_is_within_debt_limit() -> None:
    """Проверяет, что пакет в долг активируется и расходуется после пяти бесплатных минут."""
    clock = FixedClock()
    group_repository = InMemoryClientGroupRepository()
    groups = ClientGroupService(group_repository, clock=clock)
    await groups.create(
        "debtors",
        "Должники",
        allow_negative_balance=True,
        negative_balance_limit_cents=60_000,
    )
    (
        workstation,
        client,
        tariff,
        sessions,
        billing,
        _meters,
        clients,
        entitlements,
    ) = await build_package_metered_services(
        clock,
        duration_minutes=300,
        client_groups=group_repository,
        client_group_id="debtors",
        initial_balance_cents=0,
        tariff_price_cents=50_000,
    )
    session = await sessions.start(
        workstation.id,
        created_by="device",
        client_id=client.id,
        source="device",
        idempotency_key="debtor-package-session",
    )

    purchased = await entitlements.purchase(
        client.id,
        tariff.id,
        "operator",
        "debtor-package-purchase",
    )

    assert (await clients.get(client.id)).balance_cents == -50_000
    assert (await entitlements.get_active_for_client(client.id)).id == purchased.id
    assert (await sessions.snapshot(session.id)).login_grant_remaining_minutes == 5

    clock.current += datetime.timedelta(minutes=6)
    meter = await billing.meter_session(session.id)

    assert meter is not None
    assert meter.package_minutes == 1
    assert meter.active_entitlement_id == purchased.id
    assert meter.billed_cents == 0


@pytest.mark.asyncio
async def test_package_purchased_with_active_package_stays_queued() -> None:
    """
    Проверяет сценарий «test_package_purchased_with_active_package_stays_queued» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clock = FixedClock()
    (
        workstation,
        client,
        tariff,
        sessions,
        _billing,
        _meters,
        _clients,
        entitlements,
    ) = await build_package_metered_services(clock)
    first = await entitlements.purchase(client.id, tariff.id, "operator", "active-package-1")
    await entitlements.activate(first.id, client.id)
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="active-package-session",
    )

    second = await entitlements.purchase(client.id, tariff.id, "operator", "active-package-2")

    assert second.status is EntitlementStatus.QUEUED
    assert second.queue_position == first.queue_position + 1
    assert (await entitlements.get_active_for_client(client.id)).id == first.id
    assert session.status.value == "active"


@pytest.mark.asyncio
async def test_parallel_package_consumers_count_actual_locked_delta() -> None:
    """
    Проверяет сценарий «test_parallel_package_consumers_count_actual_locked_delta» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clock = FixedClock()
    (
        workstation,
        client,
        tariff,
        sessions,
        _billing,
        _meters,
        _clients,
        entitlements,
    ) = await build_package_metered_services(clock, duration_minutes=3)
    package = await entitlements.purchase(client.id, tariff.id, "operator", "parallel-package")
    await entitlements.activate(package.id, client.id)
    await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="parallel-package-session",
    )

    results = await asyncio.gather(
        *(
            entitlements.consume_for_session(
                client.id,
                "vip",
                2,
                now=clock.current,
                initial_entitlement_id=package.id,
            )
            for _ in range(2)
        )
    )

    assert sorted(result.consumed_minutes for result in results) == [1, 2]
    assert sum(result.consumed_minutes for result in results) == 3
    assert (await entitlements.get(package.id)).status is EntitlementStatus.EXHAUSTED


@pytest.mark.asyncio
async def test_auto_next_accepts_exhausted_session_package_baseline() -> None:
    """
    Проверяет сценарий «test_auto_next_accepts_exhausted_session_package_baseline» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clock = FixedClock()
    (
        workstation,
        client,
        tariff,
        sessions,
        _billing,
        _meters,
        _clients,
        entitlements,
    ) = await build_package_metered_services(clock, duration_minutes=1)
    first = await entitlements.purchase(client.id, tariff.id, "operator", "baseline-package-1")
    second = await entitlements.purchase(client.id, tariff.id, "operator", "baseline-package-2")
    await entitlements.activate(first.id, client.id)
    await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="baseline-package-session",
    )
    await entitlements.consume_for_session(
        client.id,
        "vip",
        1,
        now=clock.current,
        initial_entitlement_id=first.id,
    )

    result = await entitlements.consume_for_session(
        client.id,
        "vip",
        1,
        now=clock.current,
        initial_entitlement_id=first.id,
    )

    assert result.consumed_minutes == 1
    assert result.active_entitlement_id is None
    assert result.exhausted_entitlement_ids == (second.id,)


@pytest.mark.asyncio
async def test_exhausted_package_falls_back_to_per_minute_with_positive_balance() -> None:
    """
    Проверяет переход с исчерпанного пакета на поминутную тарификацию при
    положительном балансе клиента и списание только следующей минуты.
    """
    clock = FixedClock()
    (
        workstation,
        client,
        package_tariff,
        sessions,
        billing,
        meters,
        clients,
        entitlements,
    ) = await build_package_metered_services(clock, duration_minutes=1)
    minute_tariff = await billing._catalog.create_tariff(
        "VIP fallback minute",
        "vip",
        duration_minutes=1,
        price_cents=0,
        valid_from=clock.current,
        valid_to=None,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=10,
        free_minutes=0,
    )
    package = await entitlements.purchase(
        client.id,
        package_tariff.id,
        "operator",
        "fallback-package",
    )
    await entitlements.activate(package.id, client.id)
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        tariff_id=package_tariff.id,
        idempotency_key="fallback-session",
    )

    clock.current += datetime.timedelta(minutes=1)
    package_tick = await billing.meter_session(session.id)
    assert package_tick is not None
    assert package_tick.package_minutes == 1
    assert (await entitlements.get(package.id)).status is EntitlementStatus.EXHAUSTED

    clock.current += datetime.timedelta(minutes=1)
    fallback_tick = await billing.meter_session(session.id)

    assert fallback_tick is not None
    assert fallback_tick.tariff_id == minute_tariff.id
    assert fallback_tick.billed_minutes == 1
    assert fallback_tick.billed_cents == 10
    assert (await clients.get(client.id)).balance_cents == 890
    assert (await meters.get(session.id)).status is MeterStatus.RUNNING


@pytest.mark.asyncio
async def test_debtor_group_stops_session_after_reaching_600_ruble_debt_limit() -> None:
    """
    Проверяет, что клиент группы «Должники» может досидеть ровно до долга 600 ₽,
    а следующая поминутная минута не увеличивает долг и завершает сессию.
    """
    clock = FixedClock()
    groups = InMemoryClientGroupRepository()
    group_service = ClientGroupService(groups, clock=clock)
    await group_service.create(
        "debtors",
        "Должники",
        allow_negative_balance=True,
        negative_balance_limit_cents=60_000,
    )
    (
        workstation,
        client,
        tariff,
        sessions,
        billing,
        meters,
        clients,
    ) = await build_metered_services(
        clock,
        tariff_free_minutes=0,
        price_per_minute_cents=10_000,
        initial_balance_cents=10_000,
        client_groups=groups,
    )
    await clients.update(client.id, "MeterFox", client_group_id="debtors")
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        tariff_id=tariff.id,
        idempotency_key="debtor-limit-session",
    )

    clock.current += datetime.timedelta(minutes=7)
    limit_tick = await billing.meter_session(session.id)

    assert limit_tick is not None
    assert limit_tick.billed_minutes == 7
    assert limit_tick.billed_cents == 70_000
    assert (await clients.get(client.id)).balance_cents == -60_000
    assert (await meters.get(session.id)).status is MeterStatus.RUNNING
    assert (await sessions.get(session.id)).status.value == "active"
    assert (await sessions.snapshot(session.id)).balance_remaining_minutes == 0

    clock.current += datetime.timedelta(minutes=1)
    with pytest.raises(ApplicationError, match="Insufficient balance"):
        await billing.meter_session(session.id)

    assert (await clients.get(client.id)).balance_cents == -60_000
    assert (await meters.get(session.id)).status is MeterStatus.EXHAUSTED
    assert (await sessions.get(session.id)).status.value == "completed"


@pytest.mark.asyncio
async def test_windowed_package_stops_session_and_burns_remainder_when_window_closes() -> None:
    """
    Проверяет, что закрытие окна расходования завершает сессию и сжигает остаток
    уже активного пакета.
    """
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
        time_restricted=True,
        sale_window_start_minute=0,
        sale_window_end_minute=23 * 60 + 59,
        usage_window_start_minute=22 * 60,
        usage_window_end_minute=6 * 60,
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
    assert first_tick.status is MeterStatus.SETTLED
    assert (await entitlements.get(package.id)).status is EntitlementStatus.BURNED
    assert (await entitlements.get(package.id)).remaining_minutes == 30
    completed = await sessions.get(session.id)
    assert completed.status.value == "completed"
    assert completed.ended_at == datetime.datetime(2026, 8, 30, 3, tzinfo=datetime.UTC)

    assert (await meters.get(session.id)).package_minutes == 30


@pytest.mark.asyncio
async def test_eleven_hour_night_package_started_at_one_ends_session_at_eight() -> None:
    """
    Проверяет, что ночной пакет с 21:00 до 08:00 завершает сессию в 08:00,
    даже если у него остаются неиспользованные минуты.
    """
    clock = FixedClock()
    clock.current = datetime.datetime(2026, 8, 29, 22, tzinfo=datetime.UTC)
    (
        workstation,
        client,
        tariff,
        sessions,
        billing,
        _meters,
        _clients,
        entitlements,
    ) = await build_package_metered_services(
        clock,
        duration_minutes=11 * 60,
        time_restricted=True,
        sale_window_start_minute=0,
        sale_window_end_minute=23 * 60 + 59,
        usage_window_start_minute=21 * 60,
        usage_window_end_minute=8 * 60,
        window_timezone="Europe/Moscow",
    )
    package = await entitlements.purchase(client.id, tariff.id, "operator", "eleven-hour-night")
    await entitlements.activate(package.id, client.id)
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="eleven-hour-night-session",
    )

    clock.current += datetime.timedelta(hours=7)
    meter = await billing.meter_session(session.id)
    completed = await sessions.get(session.id)
    burned = await entitlements.get(package.id)

    assert meter is not None
    assert meter.package_minutes == 7 * 60
    assert completed.status.value == "completed"
    assert completed.ended_at == datetime.datetime(2026, 8, 30, 5, tzinfo=datetime.UTC)
    assert burned.status is EntitlementStatus.BURNED
    assert burned.remaining_minutes == 4 * 60
    assert burned.burn_reason == "usage_window_ended"


@pytest.mark.asyncio
async def test_package_purchase_is_rejected_outside_sale_window() -> None:
    """
    Проверяет, что зарегистрированный клиент не может купить тариф вне окна продажи.
    """
    clock = FixedClock()
    (
        _workstation,
        client,
        _tariff,
        _sessions,
        _billing,
        _meters,
        _clients,
        entitlements,
    ) = await build_package_metered_services(
        clock,
        time_restricted=True,
        sale_window_start_minute=22 * 60,
        sale_window_end_minute=6 * 60,
        usage_window_start_minute=22 * 60,
        usage_window_end_minute=6 * 60,
        window_timezone="UTC",
    )

    with pytest.raises(ApplicationError, match="not available"):
        await entitlements.purchase(client.id, _tariff.id, "operator", "outside-sale-window")


@pytest.mark.asyncio
async def test_guest_purchase_is_rejected_outside_sale_window() -> None:
    """
    Проверяет тот же запрет для прямой гостевой покупки тарифа.
    """
    clock = FixedClock()
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Guest night package",
        "vip",
        duration_minutes=60,
        price_cents=500,
        valid_from=clock.current,
        valid_to=None,
        time_restricted=True,
        sale_window_start_minute=22 * 60,
        sale_window_end_minute=6 * 60,
        usage_window_start_minute=22 * 60,
        usage_window_end_minute=6 * 60,
        window_timezone="UTC",
        audience="guest",
    )
    payments = GuestSessionPaymentService(
        InMemoryGuestSessionPaymentRepository(),
        tariffs=catalog,
        cash=NoopCashSettlement(),
        clock=clock,
    )

    with pytest.raises(ApplicationError, match="not available for guests"):
        await payments.confirm(
            workstation_id=uuid.uuid4(),
            tariff_id=tariff.id,
            tariff_quantity=1,
            guest_name="Night Guest",
            actor_id="operator",
            idempotency_key="guest-outside-sale-window",
            payment_parts=[{"method": "cash", "amount_cents": 500}],
        )


@pytest.mark.asyncio
async def test_session_snapshot_exposes_server_time_package_queue_and_meter() -> None:
    """
    Проверяет сценарий «test_session_snapshot_exposes_server_time_package_queue_and_meter» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    assert snapshot.tariff_names[tariff.id] == "VIP package"
    http_snapshot = SessionSnapshotResponse.from_domain(snapshot).model_dump(mode="json")
    grpc_snapshot = to_session_snapshot_proto(snapshot)
    assert http_snapshot["entitlements"][0]["tariff_name"] == "VIP package"
    assert grpc_snapshot.active_package.tariff_name == "VIP package"
    assert snapshot.meter is not None
    assert snapshot.meter.package_minutes == 1
    assert snapshot.allowed_actions == ("stop",)


@pytest.mark.asyncio
async def test_package_time_window_uses_configured_timezone() -> None:
    """
    Проверяет сценарий «test_package_time_window_uses_configured_timezone» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clock = FixedClock()
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Night package",
        "vip",
        duration_minutes=60,
        price_cents=100,
        valid_from=clock.current,
        valid_to=None,
        time_restricted=True,
        sale_window_start_minute=22 * 60,
        sale_window_end_minute=6 * 60,
        usage_window_start_minute=22 * 60,
        usage_window_end_minute=6 * 60,
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
    clock.current = datetime.datetime(2026, 8, 29, 19, tzinfo=datetime.UTC)
    item = await entitlements.purchase(client.id, tariff.id, "operator", "night-package")
    clock.current = datetime.datetime(2026, 8, 29, 18, tzinfo=datetime.UTC)
    assert await entitlements.next_compatible(client.id, "vip", now=clock.current) is None
    clock.current = datetime.datetime(2026, 8, 29, 19, tzinfo=datetime.UTC)
    assert (await entitlements.next_compatible(client.id, "vip", now=clock.current)).id == item.id
    assert (await entitlements.activate(item.id, client.id)).status is EntitlementStatus.ACTIVE


@pytest.mark.asyncio
async def test_available_package_starts_when_earlier_night_package_waits_for_window() -> None:
    """
    Проверяет, что ночной пакет вне окна расходования остаётся в очереди и не
    мешает сразу запустить следующий доступный пакет активной сессии.
    """
    clock = FixedClock()
    (
        workstation,
        client,
        _package_tariff,
        sessions,
        _billing,
        _meters,
        _clients,
        entitlements,
        catalog,
    ) = await build_package_metered_services(clock, return_catalog=True)
    night = await catalog.create_tariff(
        "Ночной тест",
        "vip",
        duration_minutes=660,
        price_cents=100,
        valid_from=clock.current,
        valid_to=None,
        time_restricted=True,
        sale_window_start_minute=0,
        sale_window_end_minute=1_439,
        usage_window_start_minute=22 * 60,
        usage_window_end_minute=8 * 60,
        window_timezone="Europe/Moscow",
    )
    normal = await catalog.create_tariff(
        "Тест",
        "vip",
        duration_minutes=3,
        price_cents=100,
        valid_from=clock.current,
        valid_to=None,
    )
    await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="night-queue-session",
    )

    waiting = await entitlements.purchase(client.id, night.id, "operator", "night-queue")
    started = await entitlements.purchase(client.id, normal.id, "operator", "normal-queue")

    assert waiting.status is EntitlementStatus.QUEUED
    assert started.status is EntitlementStatus.ACTIVE
    assert (await entitlements.get_active_for_client(client.id)).id == started.id


@pytest.mark.asyncio
async def test_package_purchase_persists_cash_transfer_mixed_payment_parts() -> None:
    """
    Проверяет смешанную оплату пакета наличными и переводом, а состав оплаты
    сохраняется в выданном праве на время.
    """
    clock = FixedClock()
    _, client, tariff, _, _, _, clients, entitlements = await build_package_metered_services(
        clock,
        cash_settlement=NoopCashSettlement(),
    )

    purchased = await entitlements.purchase(
        client.id,
        tariff.id,
        "operator",
        "mixed-package-1",
        payment_parts=[
            {"method": "cash", "amount_cents": 40},
            {"method": "transfer", "amount_cents": 60, "reference": "bank-42"},
        ],
        cash_shift_id=uuid.uuid4(),
    )

    assert [(part.method, part.amount_cents) for part in purchased.payment_parts] == [
        ("cash", 40),
        ("transfer", 60),
    ]
    assert purchased.payment_parts[1].reference == "bank-42"
    assert (await clients.get(client.id)).balance_cents == 1_000


@pytest.mark.asyncio
async def test_package_cash_failure_is_persisted_for_explicit_reconciliation() -> None:
    """
    Проверяет, что сбой после создания package не теряет факт settlement и
    повторяет наличную часть по тому же идемпотентному ключу.
    """
    clock = FixedClock()
    repository = InMemoryEntitlementRepository()
    cash = ReviewCashSettlement()
    catalog = CatalogService(InMemoryCatalogRepository())
    stored_tariff = await catalog.create_tariff(
        "Cash review package",
        "vip",
        duration_minutes=60,
        price_cents=100,
        valid_from=clock.current,
        valid_to=None,
        tariff_key="cash-review-package",
    )
    clients = ClientService(InMemoryClientRepository(), clock=clock)
    review_client = await clients.create("CashReview")
    await clients.top_up(
        review_client.id,
        500,
        0,
        "seed",
        "operator",
        "cash-review-seed",
    )
    service = EntitlementService(
        repository,
        tariffs=catalog,
        clients=clients,
        cash=cash,
        clock=clock,
    )

    with pytest.raises(RuntimeError, match="unknown"):
        await service.purchase(
            review_client.id,
            stored_tariff.id,
            "operator",
            "cash-review-package-1",
            payment_parts=[{"method": "cash", "amount_cents": 100}],
            cash_shift_id=uuid.uuid4(),
        )

    pending = await repository.get_by_idempotency_key("cash-review-package-1")
    assert pending is not None
    assert pending.settlement_status is EntitlementSettlementStatus.NEEDS_REVIEW
    assert pending.status is EntitlementStatus.QUEUED
    cash.fail = False
    reconciled = await service.retry_settlement_review(pending.id, "supervisor")
    assert reconciled.settlement_status is EntitlementSettlementStatus.SETTLED
    assert cash.calls == ["cash-review-package-1:0", "cash-review-package-1:0"]
