import datetime
import uuid

import pytest

from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.direct_payments.application.service import GuestSessionPaymentService
from gameclub_backend.modules.direct_payments.domain import DirectPaymentStatus
from gameclub_backend.modules.direct_payments.infrastructure.memory import (
    InMemoryGuestSessionPaymentRepository,
)
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository


class ToggleCashSettlement:
    def __init__(self) -> None:
        self.fail = True
        self.calls: list[dict[str, object]] = []

    async def settle(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("cash acceptance is unknown")


class FixedClock:
    def __init__(self, current: datetime.datetime) -> None:
        self.current = current

    def now(self) -> datetime.datetime:
        return self.current


class TransientCashSettlement(ToggleCashSettlement):
    async def settle(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        if self.fail:
            raise ApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE, "cash shift is unavailable")


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        return event


@pytest.mark.asyncio
async def test_guest_payment_review_requires_explicit_supervisor_retry() -> None:
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Guest hour",
        group_id="main",
        duration_minutes=60,
        price_cents=500,
        valid_from=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        valid_to=None,
        tariff_key="review-guest-hour",
    )
    cash = ToggleCashSettlement()
    repository = InMemoryGuestSessionPaymentRepository()
    service = GuestSessionPaymentService(repository, tariffs=catalog, cash=cash)
    payment_key = "guest-review-retry"

    with pytest.raises(RuntimeError, match="unknown"):
        await service.confirm(
            workstation_id=uuid.uuid4(),
            tariff_id=tariff.id,
            tariff_quantity=1,
            guest_name="Гость",
            actor_id="operator",
            idempotency_key=payment_key,
            cash_shift_id=uuid.uuid4(),
            payment_parts=[{"method": "cash", "amount_cents": 500}],
        )

    payment = await repository.get_by_idempotency_key(payment_key)
    assert payment is not None
    assert payment.status is DirectPaymentStatus.NEEDS_REVIEW
    with pytest.raises(ApplicationError) as automatic_retry:
        await service.retry_pending(payment.id)
    assert automatic_retry.value.code is ErrorCode.CONFLICT

    cash.fail = False
    retried = await service.retry_reconciliation(payment.id, "supervisor")
    assert retried.status is DirectPaymentStatus.CONFIRMED
    assert [call["payment_idempotency_key"] for call in cash.calls] == [payment_key, payment_key]


@pytest.mark.asyncio
async def test_sale_review_retry_reuses_original_cash_key_and_reserved_stock() -> None:
    catalog_repository = InMemoryCatalogRepository()
    catalog = CatalogService(catalog_repository)
    product = await catalog.create_product("Review drink", "drinks", 700, stock_quantity=2)
    cash = ToggleCashSettlement()
    sales_repository = InMemoryProductSaleRepository(catalog_repository)
    service = ProductSaleService(
        sales_repository,
        products=catalog,
        clients=ClientService(InMemoryClientRepository()),
        cash=cash,
    )

    with pytest.raises(RuntimeError, match="unknown"):
        await service.sell(
            product.id,
            quantity=1,
            client_id=None,
            payment_method="cash",
            cash_shift_id=uuid.uuid4(),
            sold_by="operator",
            idempotency_key="sale-review-retry",
        )

    review = (await service.list_sales())[0]
    assert review.status.value == "needs_review"
    assert (await catalog.get_product(product.id)).stock_quantity == 1
    cash.fail = False
    completed = await service.reconcile(review.id)
    assert completed.status.value == "completed"
    assert [call["sale_idempotency_key"] for call in cash.calls] == [
        "sale-review-retry:0",
        "sale-review-retry:0",
    ]
    assert (await catalog.get_product(product.id)).stock_quantity == 1


@pytest.mark.asyncio
async def test_guest_transient_failure_has_durable_backoff_and_settlement_audit() -> None:
    now = datetime.datetime(2026, 9, 2, 12, tzinfo=datetime.UTC)
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Guest retry",
        group_id="main",
        duration_minutes=60,
        price_cents=500,
        valid_from=now,
        valid_to=None,
        tariff_key="guest-transient-retry",
    )
    cash = TransientCashSettlement()
    audit = RecordingAudit()
    repository = InMemoryGuestSessionPaymentRepository()
    service = GuestSessionPaymentService(
        repository,
        tariffs=catalog,
        cash=cash,
        clock=FixedClock(now),
        audit=audit,
    )

    with pytest.raises(ApplicationError) as failure:
        await service.confirm(
            workstation_id=uuid.uuid4(),
            tariff_id=tariff.id,
            tariff_quantity=1,
            guest_name="Гость",
            actor_id="operator",
            idempotency_key="guest-transient-retry",
            cash_shift_id=uuid.uuid4(),
            payment_parts=[{"method": "cash", "amount_cents": 500}],
        )

    assert failure.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    payment = await repository.get_by_idempotency_key("guest-transient-retry")
    assert payment is not None
    assert payment.status is DirectPaymentStatus.PENDING
    assert payment.attempts == 1
    assert payment.next_attempt_at == now + datetime.timedelta(seconds=2)
    assert await repository.list_recoverable(now=now) == []
    assert len(await repository.list_recoverable(now=payment.next_attempt_at)) == 1
    assert audit.events[-1].outcome == "retryable"

    with pytest.raises(ApplicationError) as second_failure:
        await service.retry_pending(payment.id)
    assert second_failure.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    payment = await repository.get(payment.id)
    assert payment is not None
    assert payment.attempts == 2
    assert payment.next_attempt_at == now + datetime.timedelta(seconds=4)


@pytest.mark.asyncio
async def test_guest_payment_can_use_manual_transfer_without_cash_shift() -> None:
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Guest transfer hour",
        group_id="main",
        duration_minutes=60,
        price_cents=500,
        valid_from=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        valid_to=None,
        tariff_key="guest-transfer-hour",
    )
    cash = ToggleCashSettlement()
    repository = InMemoryGuestSessionPaymentRepository()
    service = GuestSessionPaymentService(repository, tariffs=catalog, cash=cash)

    payment = await service.confirm(
        workstation_id=uuid.uuid4(),
        tariff_id=tariff.id,
        tariff_quantity=1,
        guest_name="Гость",
        actor_id="operator",
        idempotency_key="guest-transfer-001",
        cash_shift_id=None,
        payment_parts=[{"method": "transfer", "amount_cents": 500}],
    )

    assert payment.status is DirectPaymentStatus.CONFIRMED
    assert payment.cash_shift_id is None
    assert cash.calls == []


@pytest.mark.asyncio
async def test_product_transient_failure_has_durable_backoff_and_keeps_reserved_stock() -> None:
    now = datetime.datetime(2026, 9, 2, 12, tzinfo=datetime.UTC)
    catalog_repository = InMemoryCatalogRepository()
    catalog = CatalogService(catalog_repository)
    product = await catalog.create_product("Retry drink", "drinks", 700, stock_quantity=2)
    cash = TransientCashSettlement()
    audit = RecordingAudit()
    repository = InMemoryProductSaleRepository(catalog_repository)
    service = ProductSaleService(
        repository,
        products=catalog,
        clients=ClientService(InMemoryClientRepository()),
        cash=cash,
        clock=FixedClock(now),
        audit=audit,
    )

    with pytest.raises(ApplicationError) as failure:
        await service.sell(
            product.id,
            quantity=1,
            client_id=None,
            payment_method="cash",
            cash_shift_id=uuid.uuid4(),
            sold_by="operator",
            idempotency_key="sale-transient-retry",
        )

    assert failure.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    sale = await repository.get_by_idempotency_key("sale-transient-retry")
    assert sale is not None
    assert sale.status.value == "pending"
    assert sale.attempts == 1
    assert sale.next_attempt_at == now + datetime.timedelta(seconds=2)
    assert await repository.list_recoverable(now=now) == []
    assert len(await repository.list_recoverable(now=sale.next_attempt_at)) == 1
    assert (await catalog.get_product(product.id)).stock_quantity == 1
    assert audit.events[-1].action == "product_sale.settlement"
    assert audit.events[-1].outcome == "retryable"
    assert audit.events[-1].request_id == "sale-transient-retry"
