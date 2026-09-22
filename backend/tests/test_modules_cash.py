import asyncio
import datetime

import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
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
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository

pytestmark = pytest.mark.unit


class AdvancingClock:
    """Выдаёт следующий момент времени для детерминированного порядка операций."""

    def __init__(self) -> None:
        self.current = datetime.datetime(2026, 9, 18, 12, 0, tzinfo=datetime.UTC)

    def now(self) -> datetime.datetime:
        value = self.current
        self.current += datetime.timedelta(microseconds=1)
        return value


async def test_cash_shift_schedule_opens_and_closes_idempotently() -> None:
    """
    Проверяет сценарий «test_cash_shift_schedule_opens_and_closes_idempotently» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """

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
    """
    Проверяет сценарий «test_client_operation_history_is_scoped_and_limited» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    repository = InMemoryClientRepository()
    service = ClientService(repository, clock=AdvancingClock())
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
    """
    Проверяет сценарий «test_cash_shift_lifecycle_is_idempotent_and_tracks_expected_difference»
    и подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_cash_shift_preserves_concurrent_distinct_movements» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_cash_movement_reference_is_required_as_a_pair_and_is_unique» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_cash_producers_require_finalized_sources_and_are_idempotent» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_cash_risk_operation_requires_matching_supervisor_approval» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_client_top_up_is_idempotent_under_concurrent_retries» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_client_top_up_preserves_concurrent_distinct_operations» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_client_top_up_rejects_racing_key_reused_for_another_client» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
