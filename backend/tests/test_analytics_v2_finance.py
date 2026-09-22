import dataclasses
import datetime
import uuid

import httpx
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.modules.analytics.application.finance import FinanceAnalyticsService
from gameclub_backend.modules.analytics.finance import (
    AnalyticsDataState,
    ComparisonKind,
    FinanceFactType,
    FinanceFilters,
    FinancialFact,
    WalletFact,
    WalletFactType,
    aggregate_finance_facts,
    build_period_comparison,
    compare_metric,
    moscow_day_boundaries,
)
from gameclub_backend.modules.analytics.infrastructure.finance_memory import (
    InMemoryFinanceAnalyticsRepository,
)
from gameclub_backend.presentation.http.app import create_app

UTC = datetime.UTC


def period() -> FinanceFilters:
    return FinanceFilters(
        start_at=datetime.datetime(2026, 9, 20, tzinfo=UTC),
        end_at=datetime.datetime(2026, 9, 22, tzinfo=UTC),
    )


def test_deposit_top_up_is_recognized_once_and_debit_is_consumption() -> None:
    """Проверяет, что списание депозита не создаёт повторный доход."""
    filters = period()
    result = aggregate_finance_facts(
        financial_facts=(),
        wallet_facts=(
            WalletFact(
                source_id="top-up-1000",
                fact_type=WalletFactType.TOP_UP,
                amount_cents=1_000,
                occurred_at=datetime.datetime(2026, 9, 20, 9, tzinfo=UTC),
                status="completed",
                source_reference="receipt-1000",
            ),
            WalletFact(
                source_id="debit-300",
                fact_type=WalletFactType.DEBIT,
                amount_cents=300,
                occurred_at=datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
                status="completed",
                source_reference="charge-300",
            ),
        ),
        filters=filters,
    )

    assert result.deposit_top_up_revenue_cents == 1_000
    assert result.wallet_debit_cents == 300
    assert result.recognized_revenue_cents == 1_000
    assert result.net_cash_received_cents == 1_000


def test_only_completed_and_confirmed_financial_facts_are_aggregated() -> None:
    """Проверяет включение только подтверждённых финансовых фактов."""
    filters = period()
    facts = (
        FinancialFact(
            source_id="payment-completed",
            fact_type=FinanceFactType.PAYMENT,
            amount_cents=400,
            occurred_at=datetime.datetime(2026, 9, 20, 9, tzinfo=UTC),
            status="completed",
        ),
        FinancialFact(
            source_id="payment-confirmed",
            fact_type=FinanceFactType.PAYMENT,
            amount_cents=600,
            occurred_at=datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
            status="confirmed",
        ),
        FinancialFact(
            source_id="payment-pending",
            fact_type=FinanceFactType.PAYMENT,
            amount_cents=5_000,
            occurred_at=datetime.datetime(2026, 9, 20, 11, tzinfo=UTC),
            status="pending",
        ),
        FinancialFact(
            source_id="payment-duplicate",
            fact_type=FinanceFactType.PAYMENT,
            amount_cents=600,
            occurred_at=datetime.datetime(2026, 9, 20, 12, tzinfo=UTC),
            status="confirmed",
            source_reference="payment-confirmed",
        ),
    )

    result = aggregate_finance_facts(facts, (), filters)

    assert result.payment_received_cents == 1_000
    assert result.recognized_revenue_cents == 1_000


def test_comparison_uses_equal_previous_period_and_marks_open_period_partial() -> None:
    """Проверяет равный предыдущий период и статус незавершённого периода."""
    filters = FinanceFilters(
        start_at=datetime.datetime(2026, 9, 20, 21, tzinfo=UTC),
        end_at=datetime.datetime(2026, 9, 22, 21, tzinfo=UTC),
    )

    comparison = build_period_comparison(
        filters,
        observed_at=datetime.datetime(2026, 9, 21, 12, tzinfo=UTC),
    )
    absolute = compare_metric(120, 100, ComparisonKind.ABSOLUTE)
    rate = compare_metric(65, 50, ComparisonKind.RATE)

    assert comparison.previous_start_at == datetime.datetime(2026, 9, 18, 21, tzinfo=UTC)
    assert comparison.previous_end_at == datetime.datetime(2026, 9, 20, 21, tzinfo=UTC)
    assert comparison.current_state is AnalyticsDataState.PARTIAL
    assert absolute.change_percent == 20.0
    assert rate.change_percentage_points == 15.0
    assert rate.change_percent == 30.0


def test_moscow_buckets_are_half_open_and_cross_local_midnight() -> None:
    """Проверяет границы дневных корзин в часовом поясе Москвы."""
    buckets = moscow_day_boundaries(
        datetime.datetime(2026, 9, 20, 20, 30, tzinfo=UTC),
        datetime.datetime(2026, 9, 21, 20, 30, tzinfo=UTC),
    )

    assert [bucket.key for bucket in buckets] == ["2026-09-20", "2026-09-21"]
    assert buckets[0].start_at == datetime.datetime(2026, 9, 20, 20, 30, tzinfo=UTC)
    assert buckets[0].end_at == datetime.datetime(2026, 9, 20, 21, tzinfo=UTC)
    assert buckets[1].start_at == datetime.datetime(2026, 9, 20, 21, tzinfo=UTC)
    assert buckets[1].end_at == datetime.datetime(2026, 9, 21, 20, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_finance_service_returns_metric_states_for_missing_sources() -> None:
    """Проверяет явные состояния отсутствующих источников данных."""
    service = FinanceAnalyticsService(InMemoryFinanceAnalyticsRepository())

    report = await service.finance(period(), now=datetime.datetime(2026, 9, 23, tzinfo=UTC))

    assert report.metrics["recognized_revenue_cents"].state is AnalyticsDataState.NOT_AVAILABLE
    assert report.sources["refunds"] is AnalyticsDataState.NOT_AVAILABLE
    assert report.sources["history"] is AnalyticsDataState.NOT_AVAILABLE


@pytest.mark.asyncio
async def test_finance_report_separates_cash_wallet_revenue_refunds_and_adjustments() -> None:
    """Финансовый отчёт не смешивает независимые виды денежных фактов."""
    service = FinanceAnalyticsService(
        InMemoryFinanceAnalyticsRepository(
            financial_facts=(
                FinancialFact(
                    source_id="payment-500",
                    fact_type=FinanceFactType.PAYMENT,
                    amount_cents=500,
                    occurred_at=datetime.datetime(2026, 9, 20, 9, tzinfo=UTC),
                    status="confirmed",
                ),
            ),
            wallet_facts=(
                WalletFact(
                    source_id="top-up-1000",
                    fact_type=WalletFactType.TOP_UP,
                    amount_cents=1_000,
                    occurred_at=datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
                    status="completed",
                ),
                WalletFact(
                    source_id="debit-300",
                    fact_type=WalletFactType.DEBIT,
                    amount_cents=300,
                    occurred_at=datetime.datetime(2026, 9, 20, 11, tzinfo=UTC),
                    status="completed",
                ),
            ),
        )
    )

    report = await service.finance(period(), now=datetime.datetime(2026, 9, 23, tzinfo=UTC))

    assert report.flow.payment_received_cents == 500
    assert report.flow.deposit_top_up_revenue_cents == 1_000
    assert report.flow.wallet_debit_cents == 300
    assert report.flow.refunds_cents is None
    assert report.flow.adjustments_cents is None
    assert report.flow.recognized_revenue_cents == 1_500


@pytest.mark.asyncio
async def test_finance_report_exposes_direct_cash_flow_and_payment_method_aggregates() -> None:
    """Проверяет прямые оплаты, чистый поток и разрез способов оплаты."""
    service = FinanceAnalyticsService(
        InMemoryFinanceAnalyticsRepository(
            financial_facts=(
                FinancialFact(
                    source_id="sale-500",
                    fact_type=FinanceFactType.PAYMENT,
                    amount_cents=500,
                    occurred_at=datetime.datetime(2026, 9, 20, 9, tzinfo=UTC),
                    status="confirmed",
                    payment_method_key="cash",
                    operation_type="product_sale",
                ),
            ),
            wallet_facts=(
                WalletFact(
                    source_id="top-up-1000",
                    fact_type=WalletFactType.TOP_UP,
                    amount_cents=1_000,
                    occurred_at=datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
                    status="completed",
                    payment_method_key="transfer",
                    operation_type="top_up",
                ),
            ),
        )
    )

    report = await service.finance(period(), now=datetime.datetime(2026, 9, 23, tzinfo=UTC))

    assert report.flow.direct_payment_cents == 500
    assert report.flow.net_cash_received_cents == 1_500
    assert {item.key for item in report.payment_methods} == {"cash", "transfer"}
    cash = next(item for item in report.payment_methods if item.key == "cash")
    transfer = next(item for item in report.payment_methods if item.key == "transfer")
    assert cash.amount_cents == 500
    assert cash.operation_count == 1
    assert cash.average_amount_cents == 500
    assert cash.share_bps == 3_333
    assert transfer.amount_cents == 1_000
    assert transfer.share_bps == 6_667


@pytest.mark.asyncio
async def test_finance_flow_includes_refunds_when_refund_source_is_available() -> None:
    """Проверяет уменьшение чистого денежного потока подтверждённым возвратом."""
    service = FinanceAnalyticsService(
        InMemoryFinanceAnalyticsRepository(
            financial_facts=(
                FinancialFact(
                    source_id="payment-500",
                    fact_type=FinanceFactType.PAYMENT,
                    amount_cents=500,
                    occurred_at=datetime.datetime(2026, 9, 20, 9, tzinfo=UTC),
                    status="confirmed",
                    payment_method_key="cash",
                ),
                FinancialFact(
                    source_id="refund-100",
                    fact_type=FinanceFactType.REFUND,
                    amount_cents=100,
                    occurred_at=datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
                    status="confirmed",
                    payment_method_key="cash",
                ),
            ),
            wallet_facts=(),
            refunds_available=True,
        )
    )

    report = await service.finance(period(), now=datetime.datetime(2026, 9, 23, tzinfo=UTC))

    assert report.flow.refunds_cents == 100
    assert report.flow.net_cash_received_cents == 400
    assert report.flow.recognized_revenue_cents == 400
    assert report.payment_methods[0].refunds_cents == 100


@pytest.mark.asyncio
async def test_finance_v2_endpoint_is_additive_and_explicit_about_missing_facts() -> None:
    """Проверяет новый v2 read-контракт без подмены отсутствующих фактов нулями."""
    application = create_app(
        Settings(
            jwt_secret="test-secret-with-at-least-32-bytes-long",
            dev_operator_username="operator",
            dev_operator_password="password",
        )
    )
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token = await client.post(
                "/api/v1/auth/token",
                json={"username": "operator", "password": "password"},
            )
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
            response = await client.get(
                "/api/v2/analytics/finance",
                headers=headers,
                params={
                    "start_at": "2026-09-20T00:00:00Z",
                    "end_at": "2026-09-22T00:00:00Z",
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v2"
    assert payload["sources"]["refunds"]["state"] == "not_available"
    assert payload["sources"]["history"]["state"] == "not_available"
    assert payload["metrics"]["recognized_revenue_cents"]["state"] == "not_available"
    assert payload["metrics"]["recognized_revenue_cents"]["metric_info"]["formula"]


def test_financial_fact_is_immutable() -> None:
    """Проверяет неизменяемость DTO финансового факта."""
    fact = FinancialFact(
        source_id=str(uuid.uuid4()),
        fact_type=FinanceFactType.PAYMENT,
        amount_cents=100,
        occurred_at=datetime.datetime(2026, 9, 20, tzinfo=UTC),
        status="confirmed",
        source_reference="payment-ref",
        payment_method_key="cash",
        operation_type="payment",
        operator_key="operator-1",
        cash_shift_id="shift-1",
    )

    assert fact.source_reference == "payment-ref"
    assert fact.payment_method_key == "cash"
    assert fact.operation_type == "payment"
    assert fact.operator_key == "operator-1"
    assert fact.cash_shift_id == "shift-1"

    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.amount_cents = 200  # type: ignore[misc]
