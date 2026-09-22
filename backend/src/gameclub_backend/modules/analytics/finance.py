from __future__ import annotations

import dataclasses
import datetime
import enum
import typing
import uuid
from zoneinfo import ZoneInfo

MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")
CONFIRMED_STATUSES = frozenset({"completed", "confirmed"})


class AnalyticsDataState(enum.StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    NOT_AVAILABLE = "not_available"
    NOT_CALCULATED = "not_calculated"
    ERROR = "error"


class ComparisonKind(enum.StrEnum):
    ABSOLUTE = "absolute"
    RATE = "rate"


class FinanceFactType(enum.StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class WalletFactType(enum.StrEnum):
    TOP_UP = "top_up"
    DEBIT = "debit"


@dataclasses.dataclass(frozen=True, slots=True)
class FinanceFilters:
    start_at: datetime.datetime
    end_at: datetime.datetime
    zone_key: str | None = None
    workstation_key: str | None = None
    tariff_key: str | None = None
    client_group_key: str | None = None
    payment_method_key: str | None = None
    operation_type: str | None = None
    product_key: str | None = None
    operator_key: str | None = None

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("Analytics period requires aware timestamps")
        start_at = self.start_at.astimezone(datetime.UTC)
        end_at = self.end_at.astimezone(datetime.UTC)
        if start_at >= end_at:
            raise ValueError("Analytics period must start before it ends")
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)

    def matches(self, fact: FinancialFact | WalletFact) -> bool:
        if not self.start_at <= fact.occurred_at < self.end_at:
            return False
        dimensions = (
            (self.zone_key, fact.zone_key),
            (self.workstation_key, fact.workstation_key),
            (self.tariff_key, fact.tariff_key),
            (self.client_group_key, fact.client_group_key),
            (self.payment_method_key, fact.payment_method_key),
            (self.operation_type, fact.operation_type),
            (self.product_key, fact.product_key),
            (self.operator_key, fact.operator_key),
        )
        return all(expected is None or expected == actual for expected, actual in dimensions)


@dataclasses.dataclass(frozen=True, slots=True)
class FinancialFact:
    source_id: str
    fact_type: FinanceFactType
    amount_cents: int
    occurred_at: datetime.datetime
    status: str
    source_reference: str | None = None
    payment_method_key: str | None = None
    operation_type: str | None = None
    zone_key: str | None = None
    workstation_key: str | None = None
    tariff_key: str | None = None
    client_group_key: str | None = None
    product_key: str | None = None
    operator_key: str | None = None
    cash_shift_id: str | None = None
    client_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("Financial fact source_id is required")
        if self.amount_cents < 0:
            raise ValueError("Financial fact amount cannot be negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("Financial fact timestamp requires timezone")
        if not self.status.strip():
            raise ValueError("Financial fact status is required")
        object.__setattr__(self, "fact_type", FinanceFactType(self.fact_type))
        object.__setattr__(self, "source_id", self.source_id.strip())
        object.__setattr__(self, "status", self.status.strip().lower())
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(datetime.UTC))


@dataclasses.dataclass(frozen=True, slots=True)
class WalletFact:
    source_id: str
    fact_type: WalletFactType
    amount_cents: int
    occurred_at: datetime.datetime
    status: str
    source_reference: str | None = None
    payment_method_key: str | None = None
    operation_type: str | None = None
    zone_key: str | None = None
    workstation_key: str | None = None
    tariff_key: str | None = None
    client_group_key: str | None = None
    product_key: str | None = None
    operator_key: str | None = None
    cash_shift_id: str | None = None
    client_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("Wallet fact source_id is required")
        if self.amount_cents < 0:
            raise ValueError("Wallet fact amount cannot be negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("Wallet fact timestamp requires timezone")
        if not self.status.strip():
            raise ValueError("Wallet fact status is required")
        object.__setattr__(self, "fact_type", WalletFactType(self.fact_type))
        object.__setattr__(self, "source_id", self.source_id.strip())
        object.__setattr__(self, "status", self.status.strip().lower())
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(datetime.UTC))


@dataclasses.dataclass(frozen=True, slots=True)
class MetricInfo:
    key: str
    label: str
    description: str
    formula: str
    source: str


@dataclasses.dataclass(frozen=True, slots=True)
class MetricComparison:
    current: int | float | None
    previous: int | float | None
    delta: int | float | None
    change_percent: float | None
    change_percentage_points: float | None
    state: AnalyticsDataState


@dataclasses.dataclass(frozen=True, slots=True)
class MetricResult:
    key: str
    value_cents: int | None
    state: AnalyticsDataState
    metric_info: MetricInfo
    comparison: MetricComparison | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class PeriodComparison:
    current_start_at: datetime.datetime
    current_end_at: datetime.datetime
    previous_start_at: datetime.datetime
    previous_end_at: datetime.datetime
    current_state: AnalyticsDataState


@dataclasses.dataclass(frozen=True, slots=True)
class TimeBucketBoundary:
    key: str
    label: str
    start_at: datetime.datetime
    end_at: datetime.datetime


@dataclasses.dataclass(frozen=True, slots=True)
class FinanceTotals:
    payment_received_cents: int = 0
    refunds_cents: int = 0
    deposit_top_up_revenue_cents: int = 0
    wallet_debit_cents: int = 0

    @property
    def net_cash_received_cents(self) -> int:
        return self.payment_received_cents + self.deposit_top_up_revenue_cents - self.refunds_cents

    @property
    def recognized_revenue_cents(self) -> int:
        return self.net_cash_received_cents


@dataclasses.dataclass(frozen=True, slots=True)
class FinanceFactsSnapshot:
    financial_facts: tuple[FinancialFact, ...] | None
    wallet_facts: tuple[WalletFact, ...] | None
    refunds_available: bool = False
    history_available: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class FinanceFlow:
    """Раздельные финансовые потоки с явным отсутствием источника."""

    payment_received_cents: int | None
    direct_payment_cents: int | None
    deposit_top_up_revenue_cents: int | None
    wallet_debit_cents: int | None
    recognized_revenue_cents: int | None
    refunds_cents: int | None
    adjustments_cents: int | None
    net_cash_received_cents: int | None


@dataclasses.dataclass(frozen=True, slots=True)
class PaymentMethodAggregate:
    key: str
    amount_cents: int
    operation_count: int
    share_bps: int
    average_amount_cents: int
    counter: int
    refunds_cents: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class FinanceReport:
    period: FinanceFilters
    comparison_period: PeriodComparison
    flow: FinanceFlow
    metrics: dict[str, MetricResult]
    sources: dict[str, AnalyticsDataState]
    payment_methods: tuple[PaymentMethodAggregate, ...] = ()


FINANCE_METRIC_INFO: dict[str, MetricInfo] = {
    "cash_received_cents": MetricInfo(
        key="cash_received_cents",
        label="Полученные деньги",
        description="Подтверждённые положительные платежи.",
        formula="sum(confirmed Payment.amount_cents)",
        source="FinancialFact(payment)",
    ),
    "refunds_cents": MetricInfo(
        key="refunds_cents",
        label="Возвраты",
        description="Подтверждённые возвраты отдельными финансовыми фактами.",
        formula="sum(confirmed Refund.amount_cents)",
        source="FinancialFact(refund)",
    ),
    "deposit_top_up_revenue_cents": MetricInfo(
        key="deposit_top_up_revenue_cents",
        label="Доход от пополнений",
        description="Пополнение депозита признаётся доходом один раз.",
        formula="sum(confirmed WalletFact.top_up.amount_cents)",
        source="WalletFact(top_up)",
    ),
    "wallet_debit_cents": MetricInfo(
        key="wallet_debit_cents",
        label="Расходование депозита",
        description="Списание уже признанного дохода с внутреннего баланса.",
        formula="sum(confirmed WalletFact.debit.amount_cents)",
        source="WalletFact(debit)",
    ),
    "recognized_revenue_cents": MetricInfo(
        key="recognized_revenue_cents",
        label="Признанный доход",
        description="Платежи и пополнения без повторного учёта списаний депозита.",
        formula="payments + top_ups - refunds",
        source="FinancialFact + WalletFact",
    ),
}


def is_confirmed_status(status: str | enum.StrEnum) -> bool:
    value = status.value if isinstance(status, enum.StrEnum) else status
    return value.strip().lower() in CONFIRMED_STATUSES


def _fact_key(fact: FinancialFact | WalletFact) -> str:
    return fact.source_reference or fact.source_id


def aggregate_finance_facts(
    financial_facts: typing.Iterable[FinancialFact] | None,
    wallet_facts: typing.Iterable[WalletFact] | None,
    filters: FinanceFilters,
) -> FinanceTotals:
    totals = FinanceTotals()
    seen: set[str] = set()
    facts: list[FinancialFact | WalletFact] = [
        *tuple(financial_facts or ()),
        *tuple(wallet_facts or ()),
    ]
    for fact in facts:
        if not filters.matches(fact) or not is_confirmed_status(fact.status):
            continue
        key = _fact_key(fact)
        if key in seen:
            continue
        seen.add(key)
        if isinstance(fact, FinancialFact):
            if fact.fact_type is FinanceFactType.PAYMENT:
                totals = dataclasses.replace(
                    totals,
                    payment_received_cents=totals.payment_received_cents + fact.amount_cents,
                )
            elif fact.fact_type is FinanceFactType.REFUND:
                totals = dataclasses.replace(
                    totals,
                    refunds_cents=totals.refunds_cents + fact.amount_cents,
                )
        elif fact.fact_type is WalletFactType.TOP_UP:
            totals = dataclasses.replace(
                totals,
                deposit_top_up_revenue_cents=(
                    totals.deposit_top_up_revenue_cents + fact.amount_cents
                ),
            )
        elif fact.fact_type is WalletFactType.DEBIT:
            totals = dataclasses.replace(
                totals,
                wallet_debit_cents=totals.wallet_debit_cents + fact.amount_cents,
            )
    return totals


def aggregate_payment_methods(
    financial_facts: typing.Iterable[FinancialFact] | None,
    wallet_facts: typing.Iterable[WalletFact] | None,
    filters: FinanceFilters,
) -> tuple[PaymentMethodAggregate, ...]:
    """Aggregate confirmed cash-bearing facts by configured payment method."""
    amounts: dict[str, int] = {}
    counts: dict[str, int] = {}
    refunds: dict[str, int] = {}
    seen: set[str] = set()
    facts: tuple[FinancialFact | WalletFact, ...] = (
        *tuple(financial_facts or ()),
        *tuple(wallet_facts or ()),
    )
    for fact in facts:
        if not filters.matches(fact) or not is_confirmed_status(fact.status):
            continue
        key = _fact_key(fact)
        if key in seen:
            continue
        seen.add(key)
        method = fact.payment_method_key
        if not method:
            continue
        if isinstance(fact, FinancialFact) and fact.fact_type is FinanceFactType.REFUND:
            refunds[method] = refunds.get(method, 0) + fact.amount_cents
            continue
        if isinstance(fact, WalletFact) and fact.fact_type is not WalletFactType.TOP_UP:
            continue
        amounts[method] = amounts.get(method, 0) + fact.amount_cents
        counts[method] = counts.get(method, 0) + 1
    total = sum(amounts.values())
    return tuple(
        PaymentMethodAggregate(
            key=method,
            amount_cents=amounts[method],
            operation_count=counts[method],
            share_bps=round(amounts[method] * 10_000 / total) if total else 0,
            average_amount_cents=round(amounts[method] / counts[method]),
            counter=counts[method],
            refunds_cents=refunds.get(method, 0),
        )
        for method in sorted(amounts)
    )


def build_period_comparison(
    filters: FinanceFilters,
    observed_at: datetime.datetime,
) -> PeriodComparison:
    if observed_at.tzinfo is None:
        raise ValueError("Comparison timestamp requires timezone")
    observed_at = observed_at.astimezone(datetime.UTC)
    duration = filters.end_at - filters.start_at
    return PeriodComparison(
        current_start_at=filters.start_at,
        current_end_at=filters.end_at,
        previous_start_at=filters.start_at - duration,
        previous_end_at=filters.start_at,
        current_state=(
            AnalyticsDataState.AVAILABLE
            if filters.end_at <= observed_at
            else AnalyticsDataState.PARTIAL
        ),
    )


def compare_metric(
    current: int | float | None,
    previous: int | float | None,
    kind: ComparisonKind,
) -> MetricComparison:
    if current is None or previous is None:
        return MetricComparison(
            current=current,
            previous=previous,
            delta=None,
            change_percent=None,
            change_percentage_points=None,
            state=AnalyticsDataState.NOT_AVAILABLE,
        )
    delta = current - previous
    if previous == 0:
        return MetricComparison(
            current=current,
            previous=previous,
            delta=delta,
            change_percent=None,
            change_percentage_points=delta if kind is ComparisonKind.RATE else None,
            state=AnalyticsDataState.NOT_AVAILABLE,
        )
    return MetricComparison(
        current=current,
        previous=previous,
        delta=delta,
        change_percent=round(delta / previous * 100, 2),
        change_percentage_points=delta if kind is ComparisonKind.RATE else None,
        state=AnalyticsDataState.AVAILABLE,
    )


def moscow_day_boundaries(
    start_at: datetime.datetime,
    end_at: datetime.datetime,
) -> tuple[TimeBucketBoundary, ...]:
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise ValueError("Bucket boundaries require aware timestamps")
    start_at = start_at.astimezone(datetime.UTC)
    end_at = end_at.astimezone(datetime.UTC)
    if start_at >= end_at:
        raise ValueError("Bucket period must start before it ends")
    first_local_date = start_at.astimezone(MOSCOW_TIMEZONE).date()
    last_local_date = (
        (end_at - datetime.timedelta(microseconds=1)).astimezone(MOSCOW_TIMEZONE).date()
    )
    result: list[TimeBucketBoundary] = []
    local_date = first_local_date
    while local_date <= last_local_date:
        local_start = datetime.datetime.combine(
            local_date,
            datetime.time.min,
            tzinfo=MOSCOW_TIMEZONE,
        ).astimezone(datetime.UTC)
        local_end = datetime.datetime.combine(
            local_date + datetime.timedelta(days=1),
            datetime.time.min,
            tzinfo=MOSCOW_TIMEZONE,
        ).astimezone(datetime.UTC)
        bucket_start = max(start_at, local_start)
        bucket_end = min(end_at, local_end)
        if bucket_start < bucket_end:
            result.append(
                TimeBucketBoundary(
                    key=local_date.isoformat(),
                    label=local_date.strftime("%d.%m.%Y"),
                    start_at=bucket_start,
                    end_at=bucket_end,
                )
            )
        local_date += datetime.timedelta(days=1)
    return tuple(result)
