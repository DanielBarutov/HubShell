import datetime

import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.infrastructure.memory import (
    InMemoryCashShiftRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.clients.application.guests import GuestService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.domain import Bonus, Money, Nickname, PhoneNumber
from gameclub_backend.modules.clients.infrastructure.guests_memory import InMemoryGuestRepository
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.direct_payments.application.service import (
    GuestSessionPaymentService,
)
from gameclub_backend.modules.direct_payments.infrastructure.cash import (
    CashShiftGuestPaymentSettlement,
)
from gameclub_backend.modules.direct_payments.infrastructure.memory import (
    InMemoryGuestSessionPaymentRepository,
)
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.infrastructure.memory import (
    InMemoryEntitlementRepository,
)
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.infrastructure.memory import (
    InMemoryReservationRepository,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationStatus
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)

pytestmark = pytest.mark.unit

async def test_workstation_lifecycle_and_duplicate_device_are_guarded() -> None:
    """
    Проверяет сценарий «test_workstation_lifecycle_and_duplicate_device_are_guarded» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    service = WorkstationService(InMemoryWorkstationRepository())
    workstation = await service.register(
        "device-01",
        "VIP-01",
        group_id="vip",
        position=1,
        capabilities=["theme.v1", "commands.v1", "theme.v1"],
    )

    assert workstation.status is WorkstationStatus.UNKNOWN
    assert workstation.capabilities == ("commands.v1", "theme.v1")
    heartbeat = await service.heartbeat(
        "device-01",
        client_version="1.0.0",
        capabilities=["commands.v1", "commands.v1", "theme.v1"],
    )
    assert heartbeat.status is WorkstationStatus.ONLINE
    assert heartbeat.client_version == "1.0.0"
    assert heartbeat.capabilities == ("commands.v1", "theme.v1")

    with pytest.raises(ApplicationError) as error:
        await service.register("device-01", "VIP-01")

    assert error.value.code is ErrorCode.CONFLICT


async def test_legacy_group_can_be_repositioned_without_saved_group_configuration() -> None:
    """
    Проверяет сценарий «test_legacy_group_can_be_repositioned_without_saved_group_configuration»
    и подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    class EmptyGroupRepository:
        async def get(self, group_id: str) -> None:
            return None

    repository = InMemoryWorkstationRepository()
    service = WorkstationService(repository, groups=EmptyGroupRepository())
    workstation = await service.register("legacy-device", "PC legacy", group_id="main", position=1)

    updated = await service.update(workstation.id, "PC legacy", "main", 6)

    assert updated.position == 6


async def test_workstation_status_becomes_stale_and_offline_after_heartbeat() -> None:
    """
    Проверяет сценарий «test_workstation_status_becomes_stale_and_offline_after_heartbeat» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    class FixedClock:
        def __init__(self) -> None:
            self.current = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    clock = FixedClock()
    service = WorkstationService(
        InMemoryWorkstationRepository(),
        clock=clock,
        stale_after_seconds=45,
        offline_after_seconds=120,
    )
    await service.register("device-01", "PC-01")
    await service.heartbeat("device-01")

    clock.current += datetime.timedelta(seconds=60)
    assert (await service.list())[0].status is WorkstationStatus.STALE
    clock.current += datetime.timedelta(seconds=61)
    assert (await service.list())[0].status is WorkstationStatus.OFFLINE


async def test_client_search_and_top_up_are_idempotent() -> None:
    """
    Проверяет сценарий «test_client_search_and_top_up_are_idempotent» и подтверждает ожидаемый
    публичный результат согласно соответствующему бизнес-правилу.
    """
    service = ClientService(InMemoryClientRepository())
    client = await service.create("NightFox", "+7 (999) 123-45-67")

    search_result = await service.search("nig", "nickname")
    assert [item.id for item in search_result] == [client.id]
    phone_result = await service.search("9991", "phone")
    assert [item.id for item in phone_result] == [client.id]
    phone_result_from_eight = await service.search("89991", "phone")
    assert [item.id for item in phone_result_from_eight] == [client.id]

    updated, first_operation = await service.top_up(
        client_id=client.id,
        amount_cents=1_000,
        bonus_amount=100,
        reason="Initial deposit",
        actor_id="operator",
        idempotency_key="deposit-001",
    )
    repeated, repeated_operation = await service.top_up(
        client_id=client.id,
        amount_cents=1_000,
        bonus_amount=100,
        reason="Initial deposit",
        actor_id="operator",
        idempotency_key="deposit-001",
    )

    assert updated.balance_cents == 1_000
    assert updated.balance_bonus == 100
    assert repeated == updated
    assert repeated_operation == first_operation

    with pytest.raises(ApplicationError) as mismatch_error:
        await service.top_up(
            client_id=client.id,
            amount_cents=2_000,
            bonus_amount=100,
            reason="Initial deposit",
            actor_id="operator",
            idempotency_key="deposit-001",
        )
    assert mismatch_error.value.code is ErrorCode.CONFLICT

    with pytest.raises(ApplicationError) as actor_error:
        await service.top_up(
            client_id=client.id,
            amount_cents=1_000,
            bonus_amount=100,
            reason="Initial deposit",
            actor_id="another-operator",
            idempotency_key="deposit-001",
        )
    assert actor_error.value.code is ErrorCode.CONFLICT

    with pytest.raises(ApplicationError) as reason_error:
        await service.top_up(
            client_id=client.id,
            amount_cents=100,
            bonus_amount=0,
            reason="   ",
            actor_id="operator",
            idempotency_key="deposit-empty-reason",
        )
    assert reason_error.value.code is ErrorCode.INVALID_ARGUMENT

    history = await service.list_operations(client.id)
    assert len(history) == 1
    assert history[0].id == first_operation.id
    assert history[0].reason == "Initial deposit"


async def test_entitlement_queue_requires_explicit_activation_and_preserves_order() -> None:
    """
    Проверяет сценарий «test_entitlement_queue_requires_explicit_activation_and_preserves_order»
    и подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    clients = ClientService(InMemoryClientRepository())
    client = await clients.create("PackageQueueClient")
    await clients.top_up(client.id, 1_000, 0, "Deposit", "operator", "package-deposit")
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Two hours",
        group_id="main",
        duration_minutes=120,
        price_cents=300,
        valid_from=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        valid_to=None,
        tariff_key="two-hours",
    )
    service = EntitlementService(
        InMemoryEntitlementRepository(),
        tariffs=catalog,
        clients=clients,
    )

    first = await service.purchase(client.id, tariff.id, "operator", "package-001")
    repeated = await service.purchase(client.id, tariff.id, "operator", "package-001")
    second = await service.purchase(client.id, tariff.id, "operator", "package-002")

    assert repeated.id == first.id
    assert [item.queue_position for item in await service.list_for_client(client.id)] == [1, 2]
    assert first.status.value == "queued"
    active = await service.activate(first.id, client.id)
    assert active.status.value == "active"
    with pytest.raises(ApplicationError) as conflict:
        await service.activate(second.id, client.id)
    assert conflict.value.code is ErrorCode.CONFLICT
    exhausted = await service.consume(first.id, client.id, 120)
    assert exhausted.status.value == "exhausted"
    assert (await service.activate(second.id, client.id)).status.value == "active"
    assert (await clients.get(client.id)).balance_cents == 400


async def test_guest_tariff_requires_confirmed_direct_payment_before_session_start() -> None:
    """
    Проверяет сценарий
    «test_guest_tariff_requires_confirmed_direct_payment_before_session_start» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "guest-payment-device",
        "Guest payment PC",
        group_id="main",
    )
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Guest hour",
        group_id="main",
        duration_minutes=60,
        price_cents=250,
        valid_from=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        valid_to=None,
        tariff_key="guest-hour",
    )
    cash_shifts = CashShiftService(InMemoryCashShiftRepository())
    shift = await cash_shifts.open("guest-register", 0, "operator", "guest-payment-shift")
    guest_payments = GuestSessionPaymentService(
        InMemoryGuestSessionPaymentRepository(),
        tariffs=catalog,
        cash=CashShiftGuestPaymentSettlement(cash_shifts),
    )
    clients = InMemoryClientRepository()
    sessions = SessionService(
        InMemorySessionRepository(),
        workstations=workstation_repository,
        clients=clients,
        guest_payments=guest_payments,
    )

    with pytest.raises(ApplicationError) as missing_payment:
        await sessions.start(
            workstation.id,
            created_by="operator",
            guest_name="Гость",
            tariff_id=tariff.id,
        )
    assert missing_payment.value.code is ErrorCode.CONFLICT

    payment = await guest_payments.confirm(
        workstation_id=workstation.id,
        tariff_id=tariff.id,
        tariff_quantity=1,
        guest_name="Гость",
        actor_id="operator",
        idempotency_key="guest-payment-001",
        cash_shift_id=shift.id,
        payment_parts=[{"method": "cash", "amount_cents": 250}],
    )
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        guest_name="Гость",
        tariff_id=tariff.id,
        guest_payment_id=payment.id,
    )

    assert session.guest_payment_id == payment.id
    assert (await cash_shifts.get(shift.id)).expected_close_cents == 250


async def test_tariffs_are_scoped_to_workstation_group_on_listing_and_session_start() -> None:
    """
    Проверяет сценарий
    «test_tariffs_are_scoped_to_workstation_group_on_listing_and_session_start» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    catalog = CatalogService(InMemoryCatalogRepository())
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    global_tariff = await catalog.create_tariff("Global", None, 60, 100, now, None)
    vip_tariff = await catalog.create_tariff("VIP", "VIP", 60, 200, now, None)
    main_tariff = await catalog.create_tariff("Main", "main", 60, 150, now, None)

    listed = await catalog.list_tariffs_for_group("vip")
    assert {item.id for item in listed} == {global_tariff.id, vip_tariff.id}

    workstations = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstations).register(
        "zone-device",
        "Zone PC",
        group_id="vip",
    )
    clients = InMemoryClientRepository()
    client = await ClientService(clients).create("ZoneFox")
    sessions = SessionService(
        InMemorySessionRepository(),
        workstations=workstations,
        clients=clients,
        tariffs=catalog,
    )

    with pytest.raises(ApplicationError) as error:
        await sessions.start(
            workstation.id,
            created_by="operator",
            client_id=client.id,
            tariff_id=main_tariff.id,
        )
    assert error.value.code is ErrorCode.CONFLICT


async def test_guest_payment_rejects_tariff_from_another_workstation_group() -> None:
    """
    Проверяет сценарий «test_guest_payment_rejects_tariff_from_another_workstation_group» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstations = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstations).register(
        "payment-zone-device",
        "Payment Zone PC",
        group_id="main",
    )
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "VIP package",
        "vip",
        60,
        250,
        datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        None,
    )
    cash_shifts = CashShiftService(InMemoryCashShiftRepository())
    shift = await cash_shifts.open("zone-register", 0, "operator", "zone-payment-shift")
    payments = GuestSessionPaymentService(
        InMemoryGuestSessionPaymentRepository(),
        tariffs=catalog,
        cash=CashShiftGuestPaymentSettlement(cash_shifts),
        workstations=workstations,
    )

    with pytest.raises(ApplicationError) as error:
        await payments.confirm(
            workstation_id=workstation.id,
            tariff_id=tariff.id,
            tariff_quantity=1,
            guest_name="Гость",
            actor_id="operator",
            idempotency_key="zone-payment-mismatch",
            cash_shift_id=shift.id,
            payment_parts=[{"method": "cash", "amount_cents": 250}],
        )
    assert error.value.code is ErrorCode.CONFLICT


async def test_guest_profile_search_and_booking_session_links() -> None:
    """
    Проверяет сценарий «test_guest_profile_search_and_booking_session_links» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    guest_repository = InMemoryGuestRepository()
    guest_service = GuestService(guest_repository)
    guest = await guest_service.create("  WalkInFox  ", "+7 (999) 123-45-67", "student")

    assert guest.nickname == "WalkInFox"
    assert guest.phone == "79991234567"
    assert [item.id for item in await guest_service.search("wal", "nickname")] == [guest.id]
    assert [item.id for item in await guest_service.search("9991", "phone")] == [guest.id]

    with pytest.raises(ApplicationError) as error:
        await guest_service.search("wa", "nickname")
    assert error.value.code is ErrorCode.INVALID_ARGUMENT

    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "guest-device",
        "Guest PC",
    )
    reservation = await ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=InMemoryClientRepository(),
        guests=guest_repository,
    ).create(
        workstation_ids=[workstation.id],
        start_at=datetime.datetime(2030, 1, 1, 12, tzinfo=datetime.UTC),
        end_at=datetime.datetime(2030, 1, 1, 13, tzinfo=datetime.UTC),
        created_by="operator",
        guest_id=guest.id,
    )
    assert reservation.guest_id == guest.id
    assert reservation.guest_name == guest.nickname

    session = await SessionService(
        InMemorySessionRepository(),
        workstations=workstation_repository,
        clients=InMemoryClientRepository(),
        guests=guest_repository,
    ).start(
        workstation.id,
        created_by="operator",
        guest_id=guest.id,
    )
    assert session.guest_id == guest.id
    assert session.guest_name == guest.nickname


def test_client_value_objects_normalize_and_guard_boundaries() -> None:
    """
    Проверяет сценарий «test_client_value_objects_normalize_and_guard_boundaries» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    assert Nickname("  NightFox  ").value == "NightFox"
    assert PhoneNumber("+7 (999) 123-45-67").value == "79991234567"
    assert PhoneNumber("8 (999) 123-45-67").value == "79991234567"
    assert PhoneNumber("9991234567").value == "79991234567"
    assert Money(250).add(Money(75)).cents == 325
    assert Money(325).subtract(Money(75)).cents == 250
    assert Bonus(10).add(Bonus(5)).units == 15

    with pytest.raises(ValueError):
        Nickname("no")
    with pytest.raises(ValueError):
        PhoneNumber("---")
    with pytest.raises(ValueError):
        PhoneNumber("+1 202 555 0142")
    with pytest.raises(ValueError):
        Money(-1)
    with pytest.raises(ValueError):
        Bonus(-1)


async def test_guest_mode_management_and_catalog_categories() -> None:
    """
    Проверяет сценарий «test_guest_mode_management_and_catalog_categories» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    workstation = await workstation_service.register("device-management-01", "PC 01")
    updated = await workstation_service.update(workstation.id, "PC 01 updated", "vip", 4)
    assert updated.name == "PC 01 updated"
    assert updated.group_id == "vip"
    assert updated.position == 4
    await workstation_service.disable(workstation.id, "Maintenance")
    enabled = await workstation_service.enable(workstation.id)
    assert enabled.status is WorkstationStatus.UNKNOWN

    reservation = await ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=InMemoryClientRepository(),
    ).create(
        workstation_ids=[workstation.id],
        start_at=datetime.datetime(2030, 1, 1, 12, tzinfo=datetime.UTC),
        end_at=datetime.datetime(2030, 1, 1, 13, tzinfo=datetime.UTC),
        created_by="operator",
    )
    assert reservation.guest_name == "Гость"

    await workstation_service.archive(workstation.id)
    assert await workstation_service.list() == []

    # A separate workstation is needed because the archived one must not start a session.
    session_workstation = await workstation_service.register("device-management-02", "PC 02")
    session = await SessionService(
        InMemorySessionRepository(),
        workstations=workstation_repository,
        clients=InMemoryClientRepository(),
    ).start(session_workstation.id, created_by="operator")
    assert session.guest_name == "Гость"

    catalog = CatalogService(InMemoryCatalogRepository())
    category = await catalog.create_category("drinks", "Напитки", "drink")
    assert category.id == "drinks"
    assert (await catalog.list_categories()) == [category]
    renamed = await catalog.update_category("drinks", "Холодные напитки", "drink")
    assert renamed.name == "Холодные напитки"
    await catalog.delete_category("drinks")
    assert await catalog.list_categories() == []
