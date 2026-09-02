import asyncio
import datetime
import uuid

import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.domain import ReconciliationStatus
from gameclub_backend.modules.billing.infrastructure.memory import (
    InMemoryChargeReconciliationRepository,
    InMemoryChargeRepository,
)
from gameclub_backend.modules.cash_shifts.application.producers import (
    BillingCashSettlementProducer,
    BillingSettlement,
    ExternalPayment,
    ExternalPaymentProducer,
)
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.infrastructure.memory import (
    InMemoryCashApprovalRepository,
    InMemoryCashShiftRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import TariffLifecycle
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
from gameclub_backend.modules.reservations.domain import ReservationStatus
from gameclub_backend.modules.reservations.infrastructure.memory import (
    InMemoryReservationRepository,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import SessionStatus
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationStatus
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)


async def test_workstation_lifecycle_and_duplicate_device_are_guarded() -> None:
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
    class EmptyGroupRepository:
        async def get(self, group_id: str) -> None:
            return None

    repository = InMemoryWorkstationRepository()
    service = WorkstationService(repository, groups=EmptyGroupRepository())
    workstation = await service.register("legacy-device", "PC legacy", group_id="main", position=1)

    updated = await service.update(workstation.id, "PC legacy", "main", 6)

    assert updated.position == 6


async def test_workstation_status_becomes_stale_and_offline_after_heartbeat() -> None:
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


async def test_guest_profile_search_and_booking_session_links() -> None:
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


async def test_cash_shift_schedule_opens_and_closes_idempotently() -> None:
    class FixedClock:
        def __init__(self) -> None:
            self.current = datetime.datetime(2026, 8, 28, 6, 59, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    clock = FixedClock()
    repository = InMemoryCashShiftRepository()
    service = CashShiftService(repository, clock=clock)
    await service.save_schedule(
        register_id="front-desk",
        timezone="Europe/Moscow",
        auto_open=True,
        auto_open_at=datetime.time(10, 0),
        auto_close=True,
        auto_close_at=datetime.time(23, 0),
        opening_balance_cents=500,
    )

    clock.current = datetime.datetime(2026, 8, 28, 7, 0, tzinfo=datetime.UTC)
    assert await service.run_auto_schedule() == 1
    assert await service.run_auto_schedule() == 0
    opened = (await service.list())[0]
    assert opened.opened_by == "system:auto"
    assert opened.opening_balance_cents == 500

    clock.current = datetime.datetime(2026, 8, 28, 20, 0, tzinfo=datetime.UTC)
    assert await service.run_auto_schedule() == 1
    closed = await service.get(opened.id)
    assert closed.status.value == "closed"
    assert closed.actual_close_cents == closed.expected_close_cents


async def test_client_operation_history_is_scoped_and_limited() -> None:
    repository = InMemoryClientRepository()
    service = ClientService(repository)
    first_client = await service.create("HistoryFirstFox")
    second_client = await service.create("HistorySecondFox")

    for index in range(3):
        await service.top_up(
            client_id=first_client.id,
            amount_cents=(index + 1) * 100,
            bonus_amount=0,
            reason=f"Deposit {index}",
            actor_id="operator",
            idempotency_key=f"history-{index}",
        )
    await service.top_up(
        client_id=second_client.id,
        amount_cents=500,
        bonus_amount=0,
        reason="Other client",
        actor_id="operator",
        idempotency_key="history-other",
    )

    history = await service.list_operations(first_client.id, limit=2)
    assert len(history) == 2
    assert [item.reason for item in history] == ["Deposit 2", "Deposit 1"]


async def test_cash_shift_lifecycle_is_idempotent_and_tracks_expected_difference() -> None:
    service = CashShiftService(
        InMemoryCashShiftRepository(),
        approvals=InMemoryCashApprovalRepository(),
    )
    shift = await service.open(
        register_id="front-desk",
        opening_balance_cents=1_000,
        opened_by="operator",
        idempotency_key="cash-open-001",
    )
    repeated = await service.open(
        register_id="front-desk",
        opening_balance_cents=1_000,
        opened_by="operator",
        idempotency_key="cash-open-001",
    )
    assert repeated == shift
    with pytest.raises(ApplicationError) as opening_key_error:
        await service.open(
            register_id="front-desk",
            opening_balance_cents=2_000,
            opened_by="operator",
            idempotency_key="cash-open-001",
        )
    assert opening_key_error.value.code is ErrorCode.CONFLICT

    correction_approval = await service.approve(
        shift.id,
        "correction",
        "cash-movement-003",
        "supervisor",
        "Verified the drawer count",
        "cash-approval-lifecycle-correction",
    )

    _, cash_in = await service.record_movement(
        shift.id,
        "cash_in",
        500,
        "Cash deposit",
        "operator",
        "cash-movement-001",
    )
    _, cash_out = await service.record_movement(
        shift.id,
        "cash_out",
        100,
        "Change payout",
        "operator",
        "cash-movement-002",
    )
    updated, correction = await service.record_movement(
        shift.id,
        "correction",
        -50,
        "Count correction",
        "operator",
        "cash-movement-003",
        approval_id=correction_approval.id,
    )
    assert cash_in.delta_cents == 500
    assert cash_out.delta_cents == -100
    assert correction.delta_cents == -50
    assert updated.expected_close_cents == 1_350
    with pytest.raises(ApplicationError) as movement_key_error:
        await service.record_movement(
            shift.id,
            "cash_in",
            999,
            "Different payload",
            "operator",
            "cash-movement-001",
        )
    assert movement_key_error.value.code is ErrorCode.CONFLICT

    with pytest.raises(ApplicationError) as missing_close_approval:
        await service.close(shift.id, 1_300, "operator", "cash-close-001")
    assert missing_close_approval.value.code is ErrorCode.PERMISSION_DENIED

    close_approval = await service.approve(
        shift.id,
        "close_difference",
        "cash-close-001",
        "supervisor",
        "Verified the closing count",
        "cash-approval-lifecycle-close",
    )

    with pytest.raises(ApplicationError) as correction_error:
        await service.record_movement(
            shift.id,
            "correction",
            10,
            "Unauthorized correction",
            "operator",
            "cash-movement-unauthorized",
        )
    assert correction_error.value.code is ErrorCode.PERMISSION_DENIED

    closed = await service.close(
        shift.id,
        1_300,
        "operator",
        "cash-close-001",
        approval_id=close_approval.id,
    )
    repeated_close = await service.close(shift.id, 1_300, "operator", "cash-close-001")
    assert closed.status.value == "closed"
    assert closed.difference_cents == -50
    assert repeated_close == closed
    with pytest.raises(ApplicationError) as close_key_error:
        await service.close(shift.id, 1_300, "another-operator", "cash-close-001")
    assert close_key_error.value.code is ErrorCode.CONFLICT

    with pytest.raises(ApplicationError) as error:
        await service.record_movement(
            shift.id,
            "cash_in",
            1,
            "Too late",
            "operator",
            "cash-movement-004",
        )
    assert error.value.code is ErrorCode.CONFLICT


async def test_cash_shift_preserves_concurrent_distinct_movements() -> None:
    service = CashShiftService(InMemoryCashShiftRepository())
    shift = await service.open("front-desk", 0, "operator", "cash-open-concurrent")

    await asyncio.gather(
        *(
            service.record_movement(
                shift.id,
                "cash_in",
                100,
                "Concurrent cash in",
                "operator",
                f"cash-movement-concurrent-{index}",
            )
            for index in range(8)
        )
    )

    final_shift = await service.get(shift.id)
    assert final_shift.expected_close_cents == 800
    assert len(await service.list_movements(shift.id)) == 8


async def test_cash_movement_reference_is_required_as_a_pair_and_is_unique() -> None:
    service = CashShiftService(InMemoryCashShiftRepository())
    shift = await service.open("front-desk", 0, "operator", "cash-open-reference")

    with pytest.raises(ApplicationError) as pair_error:
        await service.record_movement(
            shift.id,
            "cash_in",
            100,
            "External payment",
            "operator",
            "cash-reference-missing-id",
            reference_type="external_payment",
        )
    assert pair_error.value.code is ErrorCode.INVALID_ARGUMENT

    await service.record_movement(
        shift.id,
        "cash_in",
        100,
        "External payment",
        "operator",
        "cash-reference-first",
        reference_type="external_payment",
        reference_id="payment-001",
    )
    with pytest.raises(ApplicationError) as duplicate_error:
        await service.record_movement(
            shift.id,
            "cash_in",
            100,
            "Duplicate external payment",
            "operator",
            "cash-reference-second",
            reference_type="external_payment",
            reference_id="payment-001",
        )
    assert duplicate_error.value.code is ErrorCode.CONFLICT


async def test_cash_producers_require_finalized_sources_and_are_idempotent() -> None:
    service = CashShiftService(InMemoryCashShiftRepository())
    shift = await service.open("front-desk", 0, "operator", "cash-open-producers")
    billing = BillingCashSettlementProducer(service)

    with pytest.raises(ApplicationError) as pending_error:
        await billing.publish(
            shift.id,
            BillingSettlement("charge-001", 500, confirmed=False),
        )
    assert pending_error.value.code is ErrorCode.CONFLICT

    movement = await billing.publish(shift.id, BillingSettlement("settlement-001", 500, True))
    repeated = await billing.publish(shift.id, BillingSettlement("settlement-001", 500, True))
    assert movement.id == repeated.id
    assert movement.reference_type == "billing_settlement"

    payments = ExternalPaymentProducer(service)
    with pytest.raises(ApplicationError) as unfinalized_error:
        await payments.publish(
            shift.id,
            ExternalPayment("provider", "payment-001", 300, "pending"),
        )
    assert unfinalized_error.value.code is ErrorCode.CONFLICT
    external = await payments.publish(
        shift.id,
        ExternalPayment("provider", "payment-001", 300, "captured"),
    )
    assert external.reference_id == "provider:payment-001"
    assert (await service.get(shift.id)).expected_close_cents == 800


async def test_cash_risk_operation_requires_matching_supervisor_approval() -> None:
    service = CashShiftService(
        InMemoryCashShiftRepository(),
        approvals=InMemoryCashApprovalRepository(),
    )
    shift = await service.open("front-desk", 0, "operator", "cash-open-approval")
    approval = await service.approve(
        shift.id,
        "correction",
        "cash-correction-001",
        "supervisor",
        "Verified the drawer count",
        "cash-approval-001",
    )
    assert approval.approved_by == "supervisor"
    assert (
        await service.approve(
            shift.id,
            "correction",
            "cash-correction-001",
            "supervisor",
            "Verified the drawer count",
            "cash-approval-001",
        )
    ) == approval
    with pytest.raises(ApplicationError) as approval_key_error:
        await service.approve(
            shift.id,
            "correction",
            "cash-correction-001",
            "supervisor",
            "Changed reason",
            "cash-approval-001",
        )
    assert approval_key_error.value.code is ErrorCode.CONFLICT

    await service.record_movement(
        shift.id,
        "cash_in",
        100,
        "Initial drawer amount",
        "operator",
        "cash-correction-initial-balance",
    )

    with pytest.raises(ApplicationError) as mismatch_error:
        await service.require_approval(
            approval.id,
            shift.id,
            "correction",
            "another-target",
        )
    assert mismatch_error.value.code is ErrorCode.CONFLICT

    with pytest.raises(ApplicationError) as missing_operation_approval:
        await service.record_movement(
            shift.id,
            "correction",
            -10,
            "Drawer correction",
            "operator",
            "cash-correction-001",
        )
    assert missing_operation_approval.value.code is ErrorCode.PERMISSION_DENIED

    await service.record_movement(
        shift.id,
        "correction",
        -10,
        "Drawer correction",
        "operator",
        "cash-correction-001",
        approval_id=approval.id,
    )


async def test_client_top_up_is_idempotent_under_concurrent_retries() -> None:
    repository = InMemoryClientRepository()
    service = ClientService(repository)
    client = await service.create("ConcurrentFox")

    results = await asyncio.gather(
        *(
            service.top_up(
                client_id=client.id,
                amount_cents=1_000,
                bonus_amount=100,
                reason="Concurrent retry",
                actor_id="operator",
                idempotency_key="deposit-concurrent-001",
            )
            for _ in range(8)
        )
    )

    assert {operation.id for _, operation in results} == {results[0][1].id}
    assert results[0][0].balance_cents == 1_000
    assert results[0][0].balance_bonus == 100


async def test_client_top_up_preserves_concurrent_distinct_operations() -> None:
    repository = InMemoryClientRepository()
    service = ClientService(repository)
    client = await service.create("ConcurrentBalanceFox")

    await asyncio.gather(
        *(
            service.top_up(
                client_id=client.id,
                amount_cents=100,
                bonus_amount=10,
                reason="Concurrent deposit",
                actor_id="operator",
                idempotency_key=f"deposit-concurrent-{index}",
            )
            for index in range(8)
        )
    )

    final_client = await service.get(client.id)
    assert final_client.balance_cents == 800
    assert final_client.balance_bonus == 80


async def test_client_top_up_rejects_racing_key_reused_for_another_client() -> None:
    repository = InMemoryClientRepository()
    service = ClientService(repository)
    first_client = await service.create("FirstBalanceFox")
    second_client = await service.create("SecondBalanceFox")

    results = await asyncio.gather(
        service.top_up(
            client_id=first_client.id,
            amount_cents=100,
            bonus_amount=0,
            reason="First",
            actor_id="operator",
            idempotency_key="racing-shared-key",
        ),
        service.top_up(
            client_id=second_client.id,
            amount_cents=100,
            bonus_amount=0,
            reason="Second",
            actor_id="operator",
            idempotency_key="racing-shared-key",
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    conflicts = [result for result in results if isinstance(result, ApplicationError)]
    assert len(conflicts) == 1
    assert conflicts[0].code is ErrorCode.CONFLICT


async def test_catalog_quote_selects_the_cheapest_applicable_tariff() -> None:
    service = CatalogService(InMemoryCatalogRepository())
    moment = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)
    await service.create_tariff("VIP hour", "vip", 60, 500, moment, None)
    selected = await service.create_tariff("VIP two hours", "vip", 120, 800, moment, None)

    quote = await service.quote(90, "vip", moment)

    assert quote.tariff_id == selected.id
    assert quote.price_cents == 800


async def test_catalog_quote_applies_highest_priority_discount_without_float() -> None:
    service = CatalogService(InMemoryCatalogRepository())
    moment = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)
    await service.create_tariff("Standard hour", "standard", 60, 499, moment, None)
    await service.create_discount_rule(
        " VIP ", percent_bps=1_000, priority=0, valid_from=moment, valid_to=None
    )
    await service.create_discount_rule(
        "vip", percent_bps=1_250, priority=2, valid_from=moment, valid_to=None
    )

    quote = await service.quote(60, "standard", moment, discount_category="VIP")

    assert quote.price_before_discount_cents == 499
    assert quote.discount_percent_bps == 1_250
    assert quote.discount_amount_cents == 62
    assert quote.price_cents == 437
    assert quote.discount_category == "vip"


async def test_billing_charges_completed_session_once_with_quote_snapshot() -> None:
    class FixedClock:
        current = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    clock = FixedClock()
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    workstation = await workstation_service.register("billing-device", "Billing PC", group_id="vip")

    client_repository = InMemoryClientRepository()
    client_service = ClientService(client_repository, clock=clock)
    client = await client_service.create("BillingFox")
    await client_service.top_up(
        client.id,
        amount_cents=1_000,
        bonus_amount=25,
        reason="Initial balance",
        actor_id="operator",
        idempotency_key="billing-deposit",
    )

    catalog = CatalogService(InMemoryCatalogRepository())
    await catalog.create_tariff(
        "VIP hour",
        "vip",
        duration_minutes=60,
        price_cents=500,
        valid_from=clock.current,
        valid_to=None,
    )
    session_repository = InMemorySessionRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="billing-session-start",
    )
    clock.current += datetime.timedelta(minutes=31)
    completed = await sessions.stop(session.id)

    reconciliation_repository = InMemoryChargeReconciliationRepository()
    billing = BillingService(
        InMemoryChargeRepository(),
        sessions=session_repository,
        workstations=workstation_repository,
        clients=client_service,
        catalog=catalog,
        clock=clock,
        reconciliation=reconciliation_repository,
    )
    results = await asyncio.gather(
        billing.charge_session(completed.id, "operator", "billing-charge-1"),
        billing.charge_session(completed.id, "operator", "billing-charge-2"),
    )

    assert {charge.id for charge, _ in results} == {results[0][0].id}
    assert results[0][0].duration_minutes == 31
    assert results[0][0].amount_cents == 500
    assert results[0][0].amount_before_discount_cents == 500
    assert results[0][0].balance_operation_id == results[1][0].balance_operation_id
    assert (await client_service.get(client.id)).balance_cents == 500
    assert (await client_service.get(client.id)).balance_bonus == 25
    reconciliation = await reconciliation_repository.get_by_session_id(completed.id)
    assert reconciliation is not None
    assert reconciliation.status is ReconciliationStatus.COMPLETED
    assert reconciliation.charge_id == results[0][0].id
    revenue = await billing.revenue_between(
        datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC),
        datetime.datetime(2026, 8, 27, 13, tzinfo=datetime.UTC),
    )
    assert revenue.amount_cents == 500
    assert revenue.charge_count == 1


async def test_billing_reconciliation_retries_after_charge_persistence_failure() -> None:
    class FixedClock:
        current = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    class FailOnceChargeRepository(InMemoryChargeRepository):
        should_fail = True

        async def save(self, charge):
            if self.should_fail:
                self.should_fail = False
                raise RuntimeError("temporary charge storage failure")
            return await super().save(charge)

    clock = FixedClock()
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "reconcile-device",
        "Reconciliation PC",
        group_id="standard",
    )
    client_repository = InMemoryClientRepository()
    client_service = ClientService(client_repository, clock=clock)
    client = await client_service.create("RecoveryFox")
    await client_service.top_up(
        client.id,
        amount_cents=1_000,
        bonus_amount=0,
        reason="Recovery balance",
        actor_id="operator",
        idempotency_key="recovery-deposit",
    )
    catalog = CatalogService(InMemoryCatalogRepository())
    await catalog.create_tariff(
        "Standard hour",
        "standard",
        duration_minutes=60,
        price_cents=500,
        valid_from=clock.current,
        valid_to=None,
    )
    session_repository = InMemorySessionRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
    )
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="recovery-session",
    )
    clock.current += datetime.timedelta(minutes=31)
    completed = await sessions.stop(session.id)
    reconciliation_repository = InMemoryChargeReconciliationRepository()
    billing = BillingService(
        FailOnceChargeRepository(),
        sessions=session_repository,
        workstations=workstation_repository,
        clients=client_service,
        catalog=catalog,
        clock=clock,
        reconciliation=reconciliation_repository,
    )

    with pytest.raises(RuntimeError, match="temporary charge storage failure"):
        await billing.charge_session(completed.id, "operator", "recovery-charge")

    pending = await reconciliation_repository.get_by_session_id(completed.id)
    assert pending is not None
    assert pending.status is ReconciliationStatus.RETRYABLE
    assert await reconciliation_repository.list_due(clock.current, 100) == []
    assert (
        len(
            await reconciliation_repository.list_due(
                clock.current + datetime.timedelta(seconds=2),
                100,
            )
        )
        == 1
    )
    assert (await client_service.get(client.id)).balance_cents == 500

    recovered, _ = await billing.charge_session(completed.id, "operator", "another-key")

    assert recovered.session_id == completed.id
    assert (await client_service.get(client.id)).balance_cents == 500
    finished = await reconciliation_repository.get_by_session_id(completed.id)
    assert finished is not None
    assert finished.status is ReconciliationStatus.COMPLETED


async def test_client_debit_rejects_insufficient_spendable_balance() -> None:
    service = ClientService(InMemoryClientRepository())
    client = await service.create(f"NoBalance{uuid.uuid4().hex[:8]}")

    with pytest.raises(ApplicationError) as error:
        await service.debit(
            client.id,
            amount_cents=1,
            reason="Session",
            actor_id="operator",
            idempotency_key="empty-balance-debit",
        )

    assert error.value.code is ErrorCode.CONFLICT


async def test_catalog_quote_ignores_inactive_and_out_of_period_discounts() -> None:
    service = CatalogService(InMemoryCatalogRepository())
    moment = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)
    await service.create_tariff("Standard hour", None, 60, 500, moment, None)
    await service.create_discount_rule(
        "vip",
        percent_bps=5_000,
        priority=10,
        valid_from=moment + datetime.timedelta(days=1),
        valid_to=None,
    )

    quote = await service.quote(60, None, moment, discount_category="vip")

    assert quote.price_cents == 500
    assert quote.discount_amount_cents == 0
    assert quote.discount_percent_bps == 0


async def test_catalog_tariff_lifecycle_requires_publish_before_quote() -> None:
    service = CatalogService(InMemoryCatalogRepository())
    moment = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)
    draft = await service.create_tariff(
        "Draft tariff",
        "draft-zone",
        60,
        700,
        moment,
        None,
        tariff_key="weekday-draft",
        lifecycle=TariffLifecycle.DRAFT,
    )

    with pytest.raises(ApplicationError) as draft_error:
        await service.quote(60, "draft-zone", moment)
    assert draft_error.value.code is ErrorCode.NOT_FOUND

    published = await service.publish_tariff(draft.id)
    assert published.lifecycle is TariffLifecycle.PUBLISHED
    assert published.version == 1
    assert (await service.quote(60, "draft-zone", moment)).price_cents == 700
    snapshot = await service.snapshot()
    assert [item.id for item in snapshot.tariffs] == [draft.id]

    archived = await service.archive_tariff(draft.id)
    assert archived.lifecycle is TariffLifecycle.ARCHIVED
    assert snapshot != await service.snapshot()
    assert not (await service.snapshot()).tariffs
    with pytest.raises(ApplicationError) as archived_error:
        await service.quote(60, "draft-zone", moment)
    assert archived_error.value.code is ErrorCode.NOT_FOUND


async def test_catalog_assigns_next_version_for_same_tariff_key() -> None:
    service = CatalogService(InMemoryCatalogRepository())
    moment = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)

    first = await service.create_tariff(
        "Version one",
        "version-zone",
        60,
        700,
        moment,
        None,
        tariff_key="same-tariff",
    )
    second = await service.create_tariff(
        "Version two",
        "version-zone",
        60,
        800,
        moment + datetime.timedelta(days=1),
        None,
        tariff_key="same-tariff",
    )

    assert first.version == 1
    assert second.version == 2
    assert first.tariff_key == second.tariff_key == "same-tariff"


async def test_reservation_rejects_conflicts_and_allows_reuse_after_cancel() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    workstation = await workstation_service.register("device-01", "PC-01")
    client_repository = InMemoryClientRepository()
    client_service = ClientService(client_repository)
    client = await client_service.create("NightFox")
    reservation_service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    end_at = start_at + datetime.timedelta(hours=2)

    reservation = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=end_at,
        created_by="operator",
        client_id=client.id,
    )

    with pytest.raises(ApplicationError) as error:
        await reservation_service.create(
            workstation_ids=[workstation.id],
            start_at=start_at + datetime.timedelta(minutes=30),
            end_at=end_at,
            created_by="operator",
            guest_name="Guest",
        )

    assert error.value.code is ErrorCode.CONFLICT
    cancelled = await reservation_service.cancel(reservation.id)
    assert cancelled.status.value == "cancelled"
    replacement = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=end_at,
        created_by="operator",
        guest_name="Guest",
    )
    assert replacement.id != reservation.id

    repeated = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=end_at,
        end_at=end_at + datetime.timedelta(hours=2),
        created_by="operator",
        guest_name="Another name is ignored for a repeated key",
        idempotency_key="reservation-002",
    )
    repeated_again = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=end_at,
        end_at=end_at + datetime.timedelta(hours=2),
        created_by="operator",
        guest_name="Another name is ignored for a repeated key",
        idempotency_key="reservation-002",
    )
    assert repeated_again.id == repeated.id
    with pytest.raises(ApplicationError) as mismatch_error:
        await reservation_service.create(
            workstation_ids=[workstation.id],
            start_at=end_at,
            end_at=end_at + datetime.timedelta(hours=2),
            created_by="operator",
            guest_name="Different payload",
            idempotency_key="reservation-002",
        )
    assert mismatch_error.value.code is ErrorCode.CONFLICT
    with pytest.raises(ApplicationError) as author_error:
        await reservation_service.create(
            workstation_ids=[workstation.id],
            start_at=end_at,
            end_at=end_at + datetime.timedelta(hours=2),
            created_by="another-operator",
            guest_name="Another name is ignored for a repeated key",
            idempotency_key="reservation-002",
        )
    assert author_error.value.code is ErrorCode.CONFLICT


async def test_reservation_availability_returns_conflict_and_disabled_reason() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    workstation = await workstation_service.register("device-availability", "PC-01")
    disabled = await workstation_service.register("device-disabled", "PC-02")
    await workstation_service.disable(disabled.id, "Maintenance")
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("AvailabilityFox")
    service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2026, 8, 27, 20, tzinfo=datetime.UTC)
    end_at = start_at + datetime.timedelta(hours=1)
    reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=end_at,
        created_by="operator",
        client_id=client.id,
    )

    conflict = await service.check_availability([workstation.id], start_at, end_at)
    unavailable = await service.check_availability([disabled.id], start_at, end_at)
    free = await service.check_availability(
        [workstation.id], end_at, end_at + datetime.timedelta(hours=1)
    )

    assert conflict.available is False
    assert conflict.conflicting_reservation_ids == (reservation.id,)
    assert conflict.reason == "workstation_reserved"
    assert unavailable.available is False
    assert unavailable.reason == "workstation_disabled"
    assert free.available is True
    assert free.reason is None


async def test_reservation_conflict_is_serialized_for_concurrent_creates() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-concurrent-reservation",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("ReservationFox")
    reservation_service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    end_at = start_at + datetime.timedelta(hours=2)

    results = await asyncio.gather(
        *(
            reservation_service.create(
                workstation_ids=[workstation.id],
                start_at=start_at,
                end_at=end_at,
                created_by="operator",
                client_id=client.id,
            )
            for _ in range(2)
        ),
        return_exceptions=True,
    )

    reservations = [item for item in results if not isinstance(item, Exception)]
    conflicts = [item for item in results if isinstance(item, ApplicationError)]
    assert len(reservations) == 1
    assert len(conflicts) == 1
    assert conflicts[0].code is ErrorCode.CONFLICT


async def test_reservation_lifecycle_rejects_invalid_transitions() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-lifecycle-reservation",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("LifecycleFox")
    service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=start_at + datetime.timedelta(hours=1),
        created_by="operator",
        client_id=client.id,
    )

    with pytest.raises(ApplicationError) as complete_error:
        await service.complete(reservation.id)
    assert complete_error.value.code is ErrorCode.CONFLICT

    updated = await service.update(
        reservation.id,
        workstation_ids=[workstation.id],
        start_at=start_at + datetime.timedelta(minutes=15),
        end_at=start_at + datetime.timedelta(hours=1, minutes=15),
        guest_name="Updated guest",
        notes="Updated note",
    )
    assert updated.guest_name == "Updated guest"
    assert updated.notes == "Updated note"

    active = await service.activate(reservation.id)
    assert active.status is ReservationStatus.ACTIVE
    completed = await service.complete(reservation.id)
    assert completed.status is ReservationStatus.COMPLETED

    with pytest.raises(ApplicationError) as cancel_error:
        await service.cancel(reservation.id)
    assert cancel_error.value.code is ErrorCode.CONFLICT


async def test_reservation_no_show_requires_grace_period() -> None:
    class FixedClock:
        def __init__(self) -> None:
            self.current = datetime.datetime(2026, 8, 27, 17, 59, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-grace-reservation",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("GraceReservationFox")
    clock = FixedClock()
    service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
        clock=clock,
        grace_period_minutes=15,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=start_at + datetime.timedelta(hours=1),
        created_by="operator",
        client_id=client.id,
    )

    with pytest.raises(ApplicationError) as early_error:
        await service.mark_no_show(reservation.id)
    assert early_error.value.code is ErrorCode.CONFLICT

    clock.current = start_at + datetime.timedelta(minutes=14, seconds=59)
    with pytest.raises(ApplicationError) as grace_error:
        await service.mark_no_show(reservation.id)
    assert grace_error.value.code is ErrorCode.CONFLICT

    clock.current = start_at + datetime.timedelta(minutes=15)
    no_show = await service.mark_no_show(reservation.id)
    assert no_show.status is ReservationStatus.NO_SHOW


async def test_reservation_sweep_is_idempotent_and_skips_changed_state() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-sweep-reservation",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("SweepReservationFox")
    repository = InMemoryReservationRepository()
    service = ReservationService(
        repository,
        workstations=workstation_repository,
        clients=client_repository,
        grace_period_minutes=15,
    )
    start_at = datetime.datetime(2026, 8, 27, 18, tzinfo=datetime.UTC)
    reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=start_at + datetime.timedelta(hours=1),
        created_by="operator",
        client_id=client.id,
    )
    now = start_at + datetime.timedelta(minutes=15)

    changed = await service.activate(reservation.id)
    assert changed.status is ReservationStatus.ACTIVE
    assert await service.sweep_no_shows(now) == []

    second_reservation = await service.create(
        workstation_ids=[workstation.id],
        start_at=start_at + datetime.timedelta(hours=2),
        end_at=start_at + datetime.timedelta(hours=3),
        created_by="operator",
        guest_name="Future guest",
    )
    swept = await service.sweep_no_shows(start_at + datetime.timedelta(hours=3))
    assert [item.id for item in swept] == [second_reservation.id]
    assert (await repository.get(second_reservation.id)).status is ReservationStatus.NO_SHOW
    assert await service.sweep_no_shows(start_at + datetime.timedelta(hours=3)) == []


async def test_session_lifecycle_is_idempotent_and_serializes_active_workstation() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-session-01",
        "PC-01",
    )
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("SessionFox")
    repository = InMemorySessionRepository()
    service = SessionService(
        repository,
        workstations=workstation_repository,
        clients=client_repository,
    )

    results = await asyncio.gather(
        *(
            service.start(
                workstation_id=workstation.id,
                client_id=client.id,
                created_by="operator",
                idempotency_key="session-001",
            )
            for _ in range(4)
        )
    )
    session = results[0]
    assert {item.id for item in results} == {session.id}
    assert session.status is SessionStatus.ACTIVE
    assert (await service.list(active_only=True)) == [session]

    with pytest.raises(ApplicationError) as mismatch_error:
        await service.start(
            workstation_id=workstation.id,
            client_id=client.id,
            created_by="operator",
            source="device",
            idempotency_key="session-001",
        )
    assert mismatch_error.value.code is ErrorCode.CONFLICT
    with pytest.raises(ApplicationError) as author_error:
        await service.start(
            workstation_id=workstation.id,
            client_id=client.id,
            created_by="another-operator",
            idempotency_key="session-001",
        )
    assert author_error.value.code is ErrorCode.CONFLICT

    stopped = await service.stop(session.id)
    repeated_stop = await service.stop(session.id)
    assert stopped.status is SessionStatus.COMPLETED
    assert repeated_stop == stopped

    second_session = await service.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="session-interrupt-001",
    )
    interrupted = await service.interrupt(
        second_session.id,
        interrupted_by="operator",
        reason="Клиент закончил раньше",
        idempotency_key="interrupt-001",
    )
    repeated_interrupt = await service.interrupt(
        second_session.id,
        interrupted_by="operator",
        reason="Клиент закончил раньше",
        idempotency_key="interrupt-001",
    )
    assert interrupted.status is SessionStatus.COMPLETED
    assert repeated_interrupt == interrupted


async def test_session_rejects_a_second_active_session_and_disabled_workstation() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    first = await workstation_service.register("device-session-02", "PC-01")
    disabled = await workstation_service.register("device-session-03", "PC-02")
    await workstation_service.disable(disabled.id, "Maintenance")
    client_repository = InMemoryClientRepository()
    await ClientService(client_repository).create("SecondSessionFox")
    service = SessionService(
        InMemorySessionRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )

    await service.start(first.id, created_by="operator", guest_name="Guest")
    with pytest.raises(ApplicationError) as active_error:
        await service.start(first.id, created_by="operator", guest_name="Another guest")
    with pytest.raises(ApplicationError) as disabled_error:
        await service.start(disabled.id, created_by="operator", guest_name="Guest")

    assert active_error.value.code is ErrorCode.CONFLICT
    assert disabled_error.value.code is ErrorCode.CONFLICT


async def test_entry_decision_protects_reservations_and_allows_assigned_client() -> None:
    class FixedClock:
        current = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    clock = FixedClock()
    workstations = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstations).register("entry-device", "Entry PC")
    clients = InMemoryClientRepository()
    client_service = ClientService(clients, clock=clock)
    assigned = await client_service.create("EntryAssigned")
    other = await client_service.create("EntryOther")
    reservations = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstations,
        clients=clients,
        clock=clock,
    )
    reservation = await reservations.create(
        workstation_ids=[workstation.id],
        start_at=clock.current + datetime.timedelta(minutes=20),
        end_at=clock.current + datetime.timedelta(minutes=80),
        created_by="operator",
        client_id=assigned.id,
    )

    anonymous = await reservations.check_entry(workstation.id, now=clock.current)
    assert not anonymous.allowed
    assert anonymous.reason == "reservation_client_required"
    assert anonymous.reservation_id == reservation.id

    matching = await reservations.check_entry(
        workstation.id,
        client_id=assigned.id,
        now=clock.current,
    )
    assert matching.allowed
    assert matching.reason == "allowed"

    mismatch = await reservations.check_entry(
        workstation.id,
        client_id=other.id,
        now=clock.current,
    )
    assert not mismatch.allowed
    assert mismatch.reason == "reservation_client_mismatch"


async def test_session_rejects_one_client_on_two_workstations() -> None:
    workstations = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstations)
    first = await workstation_service.register("client-session-device-1", "PC-01")
    second = await workstation_service.register("client-session-device-2", "PC-02")
    clients = InMemoryClientRepository()
    client = await ClientService(clients).create("OneSessionFox")
    service = SessionService(
        InMemorySessionRepository(),
        workstations=workstations,
        clients=clients,
    )

    await service.start(
        first.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="one-client-session-1",
    )
    with pytest.raises(ApplicationError) as error:
        await service.start(
            second.id,
            created_by="operator",
            client_id=client.id,
            idempotency_key="one-client-session-2",
        )

    assert error.value.code is ErrorCode.CONFLICT
    assert error.value.message == "Client already has an active session"


async def test_session_validates_linked_reservation_ownership() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstation_repository)
    workstation = await workstation_service.register("device-session-04", "PC-01")
    other_workstation = await workstation_service.register("device-session-05", "PC-02")
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("LinkedSessionFox")
    reservation_service = ReservationService(
        InMemoryReservationRepository(),
        workstations=workstation_repository,
        clients=client_repository,
    )
    start_at = datetime.datetime(2030, 1, 15, 18, tzinfo=datetime.UTC)
    reservation = await reservation_service.create(
        workstation_ids=[workstation.id],
        start_at=start_at,
        end_at=start_at + datetime.timedelta(hours=1),
        created_by="operator",
        client_id=client.id,
    )
    service = SessionService(
        InMemorySessionRepository(),
        workstations=workstation_repository,
        clients=client_repository,
        reservations=reservation_service,
    )

    session = await service.start(
        workstation_id=workstation.id,
        created_by="operator",
        client_id=client.id,
        reservation_id=reservation.id,
        idempotency_key="session-linked-001",
    )
    with pytest.raises(ApplicationError) as mismatch_error:
        await service.start(
            workstation_id=other_workstation.id,
            created_by="operator",
            guest_name="Wrong workstation",
            reservation_id=reservation.id,
            idempotency_key="session-linked-002",
        )

    assert session.reservation_id == reservation.id
    assert mismatch_error.value.code is ErrorCode.CONFLICT
