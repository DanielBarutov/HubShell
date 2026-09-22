from __future__ import annotations

import collections
import dataclasses
import datetime
import typing
import uuid

CONFIRMED_STATUSES = frozenset({"completed", "confirmed"})


@dataclasses.dataclass(frozen=True, slots=True)
class ClientFact:
    client_id: uuid.UUID
    registered_at: datetime.datetime
    balance_cents: int


@dataclasses.dataclass(frozen=True, slots=True)
class SessionAnalyticsFact:
    session_id: str
    client_id: uuid.UUID | None
    started_at: datetime.datetime
    ended_at: datetime.datetime
    revenue_cents: int
    status: str
    zone_key: str | None
    workstation_key: str | None
    tariff_key: str | None

    @property
    def duration_minutes(self) -> int:
        return max(0, int((self.ended_at - self.started_at).total_seconds() // 60))


@dataclasses.dataclass(frozen=True, slots=True)
class PurchaseAnalyticsFact:
    purchase_id: str
    client_id: uuid.UUID | None
    occurred_at: datetime.datetime
    revenue_cents: int
    units: int
    status: str


@dataclasses.dataclass(frozen=True, slots=True)
class EntitlementAnalyticsFact:
    entitlement_id: str
    client_id: uuid.UUID
    tariff_key: str
    purchased_at: datetime.datetime
    purchased_minutes: int
    used_minutes: int
    remaining_minutes: int
    price_cents: int
    status: str


@dataclasses.dataclass(frozen=True, slots=True)
class DepositAnalyticsFact:
    transaction_id: str
    client_id: uuid.UUID
    occurred_at: datetime.datetime
    amount_cents: int
    operation_type: str


@dataclasses.dataclass(frozen=True, slots=True)
class ClientAnalyticsFacts:
    clients: tuple[ClientFact, ...]
    sessions: tuple[SessionAnalyticsFact, ...]
    purchases: tuple[PurchaseAnalyticsFact, ...]
    entitlements: tuple[EntitlementAnalyticsFact, ...]
    deposits: tuple[DepositAnalyticsFact, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class EntitlementMetrics:
    purchased_count: int
    purchased_minutes: int
    used_minutes: int
    remaining_minutes: int
    burned_minutes: int
    utilisation_percent: float
    status_counts: dict[str, int]
    repeat_purchase_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class ClientMetrics:
    registered_count: int
    registered_unique_count: int
    active_count: int
    new_count: int
    returning_count: int
    guest_session_count: int
    positive_balance_count: int
    zero_balance_count: int
    negative_balance_count: int
    visit_count: int
    average_session_minutes: float
    average_check_cents: int
    average_visit_interval_days: float | None
    favorite_zone: str | None
    favorite_workstation: str | None
    favorite_tariff: str | None
    peak_visit_hour: int | None


@dataclasses.dataclass(frozen=True, slots=True)
class RetentionCell:
    cohort_key: str
    days: int
    cohort_size: int
    retained_count: int | None
    retention_percent: float | None
    state: str


@dataclasses.dataclass(frozen=True, slots=True)
class RetentionMetrics:
    cells: tuple[RetentionCell, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class ChurnBucket:
    days: int
    eligible_count: int
    churned_count: int
    churn_percent: float | None
    lifetime_revenue_cents: int


@dataclasses.dataclass(frozen=True, slots=True)
class ChurnMetrics:
    by_days: dict[int, ChurnBucket]


@dataclasses.dataclass(frozen=True, slots=True)
class ValueMetrics:
    period_revenue_cents: int
    active_client_count: int
    paying_client_count: int
    arpu_cents: int | None
    arppu_cents: int | None
    average_ltv_cents: int | None
    lifetime_revenue_by_client: dict[uuid.UUID, int]


@dataclasses.dataclass(frozen=True, slots=True)
class DepositMetrics:
    balance_cents: int
    top_up_cents: int
    spent_cents: int
    returned_cents: int
    remaining_cents: int
    debt_cents: int
    clients_with_balance_count: int
    zero_balance_count: int
    debtors_count: int
    aging_cents: dict[str, int]
    debt_aging_cents: dict[str, int]


@dataclasses.dataclass(frozen=True, slots=True)
class ClientAnalyticsReport:
    entitlements: EntitlementMetrics
    clients: ClientMetrics
    retention: RetentionMetrics
    churn: ChurnMetrics
    value: ValueMetrics
    deposits: DepositMetrics


def _normalise_status(status: str) -> str:
    return status.strip().lower()


def _is_confirmed(status: str) -> bool:
    return _normalise_status(status) in CONFIRMED_STATUSES


def _require_aware(moment: datetime.datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError("Analytics timestamps require timezone")


def _utc(moment: datetime.datetime) -> datetime.datetime:
    _require_aware(moment)
    return moment.astimezone(datetime.UTC)


def _in_period(
    moment: datetime.datetime, start_at: datetime.datetime, end_at: datetime.datetime
) -> bool:
    moment = _utc(moment)
    return start_at <= moment < end_at


def _period(
    start_at: datetime.datetime, end_at: datetime.datetime
) -> tuple[datetime.datetime, datetime.datetime]:
    start_at = _utc(start_at)
    end_at = _utc(end_at)
    if start_at >= end_at:
        raise ValueError("Analytics period must start before it ends")
    return start_at, end_at


def _round_percent(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 2)


def _average_cents(total: int, count: int) -> int | None:
    return round(total / count) if count else None


def _mode(values: typing.Iterable[str | None]) -> str | None:
    counts = collections.Counter(value for value in values if value is not None)
    if not counts:
        return None
    return min(counts, key=lambda value: (-counts[value], value))


def _adapted_session_facts(
    facts: ClientAnalyticsFacts,
    start_at: datetime.datetime,
    end_at: datetime.datetime,
) -> tuple[SessionAnalyticsFact, ...]:
    return tuple(
        session
        for session in facts.sessions
        if _in_period(session.started_at, start_at, end_at) and _is_confirmed(session.status)
    )


def _adapted_purchase_facts(
    facts: ClientAnalyticsFacts,
    start_at: datetime.datetime,
    end_at: datetime.datetime,
) -> tuple[PurchaseAnalyticsFact, ...]:
    return tuple(
        purchase
        for purchase in facts.purchases
        if _in_period(purchase.occurred_at, start_at, end_at) and _is_confirmed(purchase.status)
    )


def calculate_entitlement_metrics(
    entitlements: typing.Iterable[EntitlementAnalyticsFact],
    start_at: datetime.datetime,
    end_at: datetime.datetime,
) -> EntitlementMetrics:
    selected = tuple(
        entitlement
        for entitlement in entitlements
        if _in_period(entitlement.purchased_at, start_at, end_at)
    )
    status_counts = dict(collections.Counter(_normalise_status(item.status) for item in selected))
    purchased_minutes = sum(item.purchased_minutes for item in selected)
    used_minutes = sum(item.used_minutes for item in selected)
    remaining_minutes = sum(item.remaining_minutes for item in selected)
    burned_minutes = sum(
        item.remaining_minutes for item in selected if _normalise_status(item.status) == "burned"
    )
    by_client_and_tariff = collections.Counter(
        (item.client_id, item.tariff_key) for item in selected
    )
    repeat_purchase_count = sum(max(0, count - 1) for count in by_client_and_tariff.values())
    return EntitlementMetrics(
        purchased_count=len(selected),
        purchased_minutes=purchased_minutes,
        used_minutes=used_minutes,
        remaining_minutes=remaining_minutes,
        burned_minutes=burned_minutes,
        utilisation_percent=_round_percent(used_minutes, purchased_minutes),
        status_counts=status_counts,
        repeat_purchase_count=repeat_purchase_count,
    )


def _activity_times(
    client_id: uuid.UUID,
    sessions: typing.Iterable[SessionAnalyticsFact],
    purchases: typing.Iterable[PurchaseAnalyticsFact],
) -> tuple[datetime.datetime, ...]:
    return tuple(
        sorted(
            [
                _utc(session.started_at)
                for session in sessions
                if session.client_id == client_id and _is_confirmed(session.status)
            ]
            + [
                _utc(purchase.occurred_at)
                for purchase in purchases
                if purchase.client_id == client_id and _is_confirmed(purchase.status)
            ]
        )
    )


def calculate_client_metrics(
    facts: ClientAnalyticsFacts,
    start_at: datetime.datetime,
    end_at: datetime.datetime,
) -> ClientMetrics:
    clients = {client.client_id: client for client in facts.clients}
    sessions = _adapted_session_facts(facts, start_at, end_at)
    purchases = _adapted_purchase_facts(facts, start_at, end_at)
    client_sessions = tuple(session for session in sessions if session.client_id in clients)
    active_ids: set[uuid.UUID] = set()
    for session in client_sessions:
        if session.client_id is not None:
            active_ids.add(session.client_id)
    active_ids.update(
        purchase.client_id
        for purchase in purchases
        if purchase.client_id is not None and purchase.client_id in clients
    )
    new_ids = {
        client.client_id
        for client in facts.clients
        if client.client_id in active_ids and _in_period(client.registered_at, start_at, end_at)
    }
    returning_ids = {
        client_id
        for client_id in active_ids
        if clients[client_id].registered_at < start_at
        and any(
            moment < start_at
            for moment in _activity_times(client_id, facts.sessions, facts.purchases)
        )
    }
    durations = [session.duration_minutes for session in client_sessions]
    visits = sorted(session.started_at for session in client_sessions)
    intervals = [
        (later - earlier).total_seconds() / 86_400
        for earlier, later in zip(visits, visits[1:], strict=False)
    ]
    period_revenue = sum(session.revenue_cents for session in client_sessions) + sum(
        purchase.revenue_cents for purchase in purchases if purchase.client_id in clients
    )
    peak_visit_hour = _mode(str(_utc(session.started_at).hour) for session in client_sessions)
    return ClientMetrics(
        registered_count=len(clients),
        registered_unique_count=len(active_ids),
        active_count=len(active_ids),
        new_count=len(new_ids),
        returning_count=len(returning_ids),
        guest_session_count=sum(1 for session in sessions if session.client_id is None),
        positive_balance_count=sum(1 for client in facts.clients if client.balance_cents > 0),
        zero_balance_count=sum(1 for client in facts.clients if client.balance_cents == 0),
        negative_balance_count=sum(1 for client in facts.clients if client.balance_cents < 0),
        visit_count=len(client_sessions),
        average_session_minutes=round(sum(durations) / len(durations), 2) if durations else 0.0,
        average_check_cents=_average_cents(period_revenue, len(client_sessions)) or 0,
        average_visit_interval_days=round(sum(intervals) / len(intervals), 2)
        if intervals
        else None,
        favorite_zone=_mode(session.zone_key for session in client_sessions),
        favorite_workstation=_mode(session.workstation_key for session in client_sessions),
        favorite_tariff=_mode(session.tariff_key for session in client_sessions),
        peak_visit_hour=int(peak_visit_hour) if peak_visit_hour is not None else None,
    )


def calculate_retention(
    facts: ClientAnalyticsFacts,
    as_of: datetime.datetime,
    days: tuple[int, ...] = (7, 30, 60, 90),
) -> RetentionMetrics:
    as_of = _utc(as_of)
    activities = {
        client.client_id: _activity_times(client.client_id, facts.sessions, facts.purchases)
        for client in facts.clients
    }
    cohorts: dict[str, list[ClientFact]] = collections.defaultdict(list)
    for client in facts.clients:
        registered_at = _utc(client.registered_at)
        cohorts[f"{registered_at.year:04d}-{registered_at.month:02d}"].append(client)
    cells: list[RetentionCell] = []
    for cohort_key in sorted(cohorts):
        cohort = cohorts[cohort_key]
        for threshold in days:
            matured = [
                client
                for client in cohort
                if as_of >= _utc(client.registered_at) + datetime.timedelta(days=threshold)
            ]
            if len(matured) != len(cohort):
                cells.append(
                    RetentionCell(cohort_key, threshold, len(cohort), None, None, "not_matured")
                )
                continue
            retained = sum(
                any(
                    _utc(client.registered_at) + datetime.timedelta(days=threshold)
                    <= moment
                    < as_of
                    for moment in activities[client.client_id]
                )
                for client in cohort
            )
            cells.append(
                RetentionCell(
                    cohort_key,
                    threshold,
                    len(cohort),
                    retained,
                    _round_percent(retained, len(cohort)),
                    "available",
                )
            )
    return RetentionMetrics(tuple(cells))


def calculate_churn(
    facts: ClientAnalyticsFacts,
    as_of: datetime.datetime,
    days: tuple[int, ...] = (14, 30, 60, 90),
) -> ChurnMetrics:
    as_of = _utc(as_of)
    activity = {
        client.client_id: _activity_times(client.client_id, facts.sessions, facts.purchases)
        for client in facts.clients
    }
    lifetime_revenue = _lifetime_revenue(facts, as_of)
    result: dict[int, ChurnBucket] = {}
    for threshold in days:
        cutoff = as_of - datetime.timedelta(days=threshold)
        eligible = [
            client
            for client in facts.clients
            if any(moment < cutoff for moment in activity[client.client_id])
        ]
        churned = [
            client
            for client in eligible
            if not any(cutoff <= moment < as_of for moment in activity[client.client_id])
        ]
        result[threshold] = ChurnBucket(
            days=threshold,
            eligible_count=len(eligible),
            churned_count=len(churned),
            churn_percent=(_round_percent(len(churned), len(eligible)) if eligible else None),
            lifetime_revenue_cents=sum(lifetime_revenue[client.client_id] for client in churned),
        )
    return ChurnMetrics(result)


def _lifetime_revenue(
    facts: ClientAnalyticsFacts,
    as_of: datetime.datetime,
) -> dict[uuid.UUID, int]:
    as_of = _utc(as_of)
    result = {client.client_id: 0 for client in facts.clients}
    for session in facts.sessions:
        if (
            session.client_id in result
            and _utc(session.started_at) < as_of
            and _is_confirmed(session.status)
        ):
            result[typing.cast(uuid.UUID, session.client_id)] += session.revenue_cents
    for purchase in facts.purchases:
        if (
            purchase.client_id in result
            and _utc(purchase.occurred_at) < as_of
            and _is_confirmed(purchase.status)
        ):
            result[typing.cast(uuid.UUID, purchase.client_id)] += purchase.revenue_cents
    return result


def calculate_value_metrics(
    facts: ClientAnalyticsFacts,
    start_at: datetime.datetime,
    end_at: datetime.datetime,
    as_of: datetime.datetime,
) -> ValueMetrics:
    clients = {client.client_id for client in facts.clients}
    sessions = tuple(
        session
        for session in _adapted_session_facts(facts, start_at, end_at)
        if session.client_id in clients
    )
    purchases = tuple(
        purchase
        for purchase in _adapted_purchase_facts(facts, start_at, end_at)
        if purchase.client_id in clients
    )
    revenue = sum(session.revenue_cents for session in sessions) + sum(
        purchase.revenue_cents for purchase in purchases
    )
    active_ids = {session.client_id for session in sessions} | {
        purchase.client_id for purchase in purchases
    }
    by_client = _lifetime_revenue(facts, as_of)
    paying_ids = {
        client_id
        for client_id in active_ids
        if by_client.get(typing.cast(uuid.UUID, client_id), 0) > 0
    }
    return ValueMetrics(
        period_revenue_cents=revenue,
        active_client_count=len(active_ids),
        paying_client_count=len(paying_ids),
        arpu_cents=_average_cents(revenue, len(active_ids)),
        arppu_cents=_average_cents(revenue, len(paying_ids)),
        average_ltv_cents=_average_cents(sum(by_client.values()), len(by_client)),
        lifetime_revenue_by_client=by_client,
    )


@dataclasses.dataclass
class _DepositLot:
    amount_cents: int
    occurred_at: datetime.datetime


def _age_bucket(age_days: int, debt: bool = False) -> str:
    if age_days < 7:
        return "<7d"
    if age_days < 30:
        return "7-30d"
    if age_days < 60:
        return "30-60d"
    if debt:
        return "60+d"
    if age_days < 90:
        return "60-90d"
    return "90+d"


def calculate_deposit_metrics(
    facts: ClientAnalyticsFacts,
    as_of: datetime.datetime,
) -> DepositMetrics:
    as_of = _utc(as_of)
    top_up_cents = spent_cents = returned_cents = 0
    positive_lots: dict[uuid.UUID, list[_DepositLot]] = collections.defaultdict(list)
    debt_lots: dict[uuid.UUID, list[_DepositLot]] = collections.defaultdict(list)
    transactions = sorted(
        (transaction for transaction in facts.deposits if _utc(transaction.occurred_at) < as_of),
        key=lambda transaction: (_utc(transaction.occurred_at), transaction.transaction_id),
    )
    for transaction in transactions:
        kind = _normalise_status(transaction.operation_type)
        amount = transaction.amount_cents
        if kind == "top_up":
            top_up_cents += amount
            remaining = amount
            debts = debt_lots[transaction.client_id]
            while remaining and debts:
                consumed = min(remaining, debts[0].amount_cents)
                debts[0].amount_cents -= consumed
                remaining -= consumed
                if debts[0].amount_cents == 0:
                    debts.pop(0)
            if remaining:
                positive_lots[transaction.client_id].append(
                    _DepositLot(remaining, _utc(transaction.occurred_at))
                )
        elif kind in {"debit", "spend", "spent"}:
            spent_cents += amount
            _consume_deposit_lots(
                positive_lots[transaction.client_id],
                debt_lots[transaction.client_id],
                amount,
                _utc(transaction.occurred_at),
            )
        elif kind == "refund":
            returned_cents += amount
            positive_lots[transaction.client_id].append(
                _DepositLot(amount, _utc(transaction.occurred_at))
            )
    remaining_cents = sum(lot.amount_cents for lots in positive_lots.values() for lot in lots)
    ledger_debt_cents = sum(lot.amount_cents for lots in debt_lots.values() for lot in lots)
    snapshot_balance = sum(client.balance_cents for client in facts.clients)
    debt_cents = max(
        ledger_debt_cents, -sum(min(0, client.balance_cents) for client in facts.clients)
    )
    aging: collections.defaultdict[str, int] = collections.defaultdict(int)
    for lots in positive_lots.values():
        for lot in lots:
            aging[_age_bucket((as_of - lot.occurred_at).days)] += lot.amount_cents
    debt_aging: collections.defaultdict[str, int] = collections.defaultdict(int)
    for lots in debt_lots.values():
        for lot in lots:
            debt_aging[_age_bucket((as_of - lot.occurred_at).days, debt=True)] += lot.amount_cents
    return DepositMetrics(
        balance_cents=snapshot_balance,
        top_up_cents=top_up_cents,
        spent_cents=spent_cents,
        returned_cents=returned_cents,
        remaining_cents=remaining_cents,
        debt_cents=debt_cents,
        clients_with_balance_count=sum(1 for client in facts.clients if client.balance_cents != 0),
        zero_balance_count=sum(1 for client in facts.clients if client.balance_cents == 0),
        debtors_count=sum(1 for client in facts.clients if client.balance_cents < 0),
        aging_cents=dict(aging),
        debt_aging_cents=dict(debt_aging),
    )


def _consume_deposit_lots(
    lots: list[_DepositLot],
    debts: list[_DepositLot],
    amount_cents: int,
    occurred_at: datetime.datetime,
) -> None:
    remaining = amount_cents
    while remaining and lots:
        consumed = min(remaining, lots[0].amount_cents)
        lots[0].amount_cents -= consumed
        remaining -= consumed
        if lots[0].amount_cents == 0:
            lots.pop(0)
    if remaining:
        debts.append(_DepositLot(remaining, occurred_at))


def build_client_analytics_report(
    facts: ClientAnalyticsFacts,
    start_at: datetime.datetime,
    end_at: datetime.datetime,
    *,
    as_of: datetime.datetime,
) -> ClientAnalyticsReport:
    start_at, end_at = _period(start_at, end_at)
    as_of = _utc(as_of)
    return ClientAnalyticsReport(
        entitlements=calculate_entitlement_metrics(facts.entitlements, start_at, end_at),
        clients=calculate_client_metrics(facts, start_at, end_at),
        retention=calculate_retention(facts, as_of),
        churn=calculate_churn(facts, as_of),
        value=calculate_value_metrics(facts, start_at, end_at, as_of),
        deposits=calculate_deposit_metrics(facts, as_of),
    )


# Read-only adapters from existing domain facts. They copy facts into analytics DTOs;
# no producer object is mutated and no current balance is used for historical revenue.
def entitlement_from_domain(entitlement: typing.Any) -> EntitlementAnalyticsFact:
    return EntitlementAnalyticsFact(
        entitlement_id=str(entitlement.id),
        client_id=entitlement.client_id,
        tariff_key=str(entitlement.tariff_id),
        purchased_at=entitlement.purchased_at,
        purchased_minutes=entitlement.duration_minutes,
        used_minutes=entitlement.duration_minutes - entitlement.remaining_minutes,
        remaining_minutes=entitlement.remaining_minutes,
        price_cents=entitlement.price_cents,
        status=str(entitlement.status),
    )


def session_from_domain(
    session: typing.Any, charge: typing.Any | None = None
) -> SessionAnalyticsFact:
    return SessionAnalyticsFact(
        session_id=str(session.id),
        client_id=session.client_id,
        started_at=session.started_at,
        ended_at=session.ended_at or session.started_at,
        revenue_cents=charge.amount_cents if charge is not None else 0,
        status=str(session.status),
        zone_key=None,
        workstation_key=str(session.workstation_id),
        tariff_key=str(session.tariff_id) if session.tariff_id is not None else None,
    )


def purchase_from_domain(sale: typing.Any) -> PurchaseAnalyticsFact:
    occurred_at = sale.completed_at or sale.created_at
    return PurchaseAnalyticsFact(
        purchase_id=str(sale.id),
        client_id=sale.client_id,
        occurred_at=occurred_at,
        revenue_cents=sale.total_price_cents,
        units=sale.quantity,
        status=str(sale.status),
    )


def deposit_from_domain(operation: typing.Any) -> DepositAnalyticsFact:
    return DepositAnalyticsFact(
        transaction_id=str(operation.id),
        client_id=operation.client_id,
        occurred_at=operation.created_at,
        amount_cents=abs(operation.amount_cents),
        operation_type=str(operation.operation_type),
    )
