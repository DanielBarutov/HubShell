import datetime
import uuid

from gameclub_backend.modules.analytics.application.client_analytics import ClientAnalyticsService
from gameclub_backend.modules.analytics.client_analytics import (
    ClientAnalyticsFacts,
    ClientFact,
    DepositAnalyticsFact,
    EntitlementAnalyticsFact,
    PurchaseAnalyticsFact,
    SessionAnalyticsFact,
    build_client_analytics_report,
    deposit_from_domain,
    entitlement_from_domain,
    purchase_from_domain,
    session_from_domain,
)
from gameclub_backend.modules.billing.domain import SessionCharge
from gameclub_backend.modules.clients.domain import BalanceOperation, BalanceOperationType
from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus
from gameclub_backend.modules.sales.domain import (
    ProductPaymentMethod,
    ProductSale,
    ProductSaleStatus,
)
from gameclub_backend.modules.sessions.domain import Session, SessionStatus

UTC = datetime.UTC


def test_entitlement_lifecycle_reports_utilisation_and_repeat_purchase() -> None:
    """Проверяет lifecycle пакетного времени, использование и повторную покупку."""
    client_id = uuid.uuid4()
    start = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    report = build_client_analytics_report(
        ClientAnalyticsFacts(
            clients=(ClientFact(client_id, start - datetime.timedelta(days=30), 700),),
            entitlements=(
                EntitlementAnalyticsFact(
                    "first", client_id, "3h", start, 180, 120, 60, 900, "exhausted"
                ),
                EntitlementAnalyticsFact(
                    "second",
                    client_id,
                    "3h",
                    start + datetime.timedelta(days=1),
                    180,
                    0,
                    180,
                    900,
                    "queued",
                ),
                EntitlementAnalyticsFact(
                    "other-tariff",
                    client_id,
                    "night",
                    start + datetime.timedelta(days=2),
                    60,
                    0,
                    60,
                    500,
                    "queued",
                ),
            ),
            sessions=(),
            purchases=(),
            deposits=(),
        ),
        start,
        start + datetime.timedelta(days=7),
        as_of=start + datetime.timedelta(days=7),
    )

    assert report.entitlements.purchased_count == 3
    assert report.entitlements.purchased_minutes == 420
    assert report.entitlements.used_minutes == 120
    assert report.entitlements.remaining_minutes == 300
    assert report.entitlements.utilisation_percent == 28.57
    assert report.entitlements.status_counts == {"exhausted": 1, "queued": 2}
    assert report.entitlements.repeat_purchase_count == 1


def test_client_segments_exclude_guests_and_distinguish_new_active_returning() -> None:
    """Проверяет сегменты клиентов без включения гостевых сессий."""
    first_client = uuid.uuid4()
    new_client = uuid.uuid4()
    period_start = datetime.datetime(2026, 9, 10, tzinfo=UTC)
    facts = ClientAnalyticsFacts(
        clients=(
            ClientFact(first_client, period_start - datetime.timedelta(days=40), 100),
            ClientFact(new_client, period_start + datetime.timedelta(days=1), 0),
        ),
        sessions=(
            SessionAnalyticsFact(
                "old",
                first_client,
                period_start - datetime.timedelta(days=20),
                period_start - datetime.timedelta(days=19, hours=22),
                500,
                "completed",
                "vip",
                "pc-1",
                "night",
            ),
            SessionAnalyticsFact(
                "return",
                first_client,
                period_start + datetime.timedelta(days=2),
                period_start + datetime.timedelta(days=2, hours=2),
                700,
                "completed",
                "vip",
                "pc-1",
                "night",
            ),
            SessionAnalyticsFact(
                "new",
                new_client,
                period_start + datetime.timedelta(days=1),
                period_start + datetime.timedelta(days=1, hours=1),
                300,
                "completed",
                "main",
                "pc-2",
                "day",
            ),
            SessionAnalyticsFact(
                "guest",
                None,
                period_start + datetime.timedelta(days=1),
                period_start + datetime.timedelta(days=1, hours=1),
                200,
                "completed",
                "main",
                "pc-3",
                "day",
            ),
        ),
        entitlements=(),
        purchases=(),
        deposits=(),
    )

    report = build_client_analytics_report(
        facts,
        period_start,
        period_start + datetime.timedelta(days=7),
        as_of=period_start + datetime.timedelta(days=7),
    )

    assert report.clients.active_count == 2
    assert report.clients.new_count == 1
    assert report.clients.returning_count == 1
    assert report.clients.guest_session_count == 1
    assert report.clients.registered_unique_count == 2
    assert report.clients.positive_balance_count == 1


def test_retention_marks_unmatured_cohort_and_churn_uses_registered_clients_only() -> None:
    """Проверяет незрелые когорты и churn только зарегистрированных клиентов."""
    client_id = uuid.uuid4()
    cohort_start = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    as_of = datetime.datetime(2026, 9, 20, tzinfo=UTC)
    report = build_client_analytics_report(
        ClientAnalyticsFacts(
            clients=(ClientFact(client_id, cohort_start, 0),),
            sessions=(
                SessionAnalyticsFact(
                    "s",
                    client_id,
                    cohort_start,
                    cohort_start + datetime.timedelta(hours=1),
                    400,
                    "completed",
                    "main",
                    "pc-1",
                    "day",
                ),
            ),
            purchases=(),
            entitlements=(),
            deposits=(),
        ),
        cohort_start,
        as_of,
        as_of=as_of,
    )

    retention = {cell.days: cell for cell in report.retention.cells}
    assert retention[7].state == "available"
    assert retention[7].retained_count == 0
    assert retention[30].state == "not_matured"
    assert report.churn.by_days[14].churned_count == 1


def test_arpu_arppu_ltv_include_game_and_product_revenue() -> None:
    """Проверяет ARPU, ARPPU и LTV по игровой и товарной выручке."""
    client_id = uuid.uuid4()
    start = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    report = build_client_analytics_report(
        ClientAnalyticsFacts(
            clients=(ClientFact(client_id, start - datetime.timedelta(days=3), 0),),
            sessions=(
                SessionAnalyticsFact(
                    "s",
                    client_id,
                    start,
                    start + datetime.timedelta(hours=2),
                    1_000,
                    "completed",
                    "main",
                    "pc-1",
                    "day",
                ),
            ),
            purchases=(
                PurchaseAnalyticsFact(
                    "p", client_id, start + datetime.timedelta(hours=3), 500, 2, "completed"
                ),
            ),
            entitlements=(),
            deposits=(),
        ),
        start,
        start + datetime.timedelta(days=1),
        as_of=start + datetime.timedelta(days=1),
    )

    assert report.value.period_revenue_cents == 1_500
    assert report.value.arpu_cents == 1_500
    assert report.value.arppu_cents == 1_500
    assert report.value.average_ltv_cents == 1_500


def test_deposit_fifo_aging_and_debt_are_snapshot_metrics_without_mutation() -> None:
    """Проверяет FIFO aging, долг и неизменность исходных фактов."""
    client_id = uuid.uuid4()
    start = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    debtor_id = uuid.uuid4()
    facts = ClientAnalyticsFacts(
        clients=(ClientFact(client_id, start, 100), ClientFact(debtor_id, start, -200)),
        sessions=(),
        purchases=(),
        entitlements=(),
        deposits=(
            DepositAnalyticsFact("top-1", client_id, start, 1_000, "top_up"),
            DepositAnalyticsFact(
                "spend", client_id, start + datetime.timedelta(days=2), 700, "debit"
            ),
            DepositAnalyticsFact(
                "top-2", client_id, start + datetime.timedelta(days=10), 300, "top_up"
            ),
            DepositAnalyticsFact(
                "spend-2", client_id, start + datetime.timedelta(days=11), 500, "debit"
            ),
            DepositAnalyticsFact(
                "debt", debtor_id, start + datetime.timedelta(days=11), 200, "debit"
            ),
        ),
    )

    report = build_client_analytics_report(
        facts,
        start,
        start + datetime.timedelta(days=20),
        as_of=start + datetime.timedelta(days=20),
    )

    assert report.deposits.top_up_cents == 1_300
    assert report.deposits.spent_cents == 1_400
    assert report.deposits.remaining_cents == 100
    assert report.deposits.debt_cents == 200
    assert report.deposits.aging_cents["7-30d"] == 100
    assert report.deposits.debt_aging_cents["7-30d"] == 200
    assert facts.deposits[0].amount_cents == 1_000


async def test_application_service_uses_read_only_snapshot_port() -> None:
    """Проверяет использование сервисом только read-only snapshot-порта."""
    client_id = uuid.uuid4()
    start = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    facts = ClientAnalyticsFacts(
        clients=(ClientFact(client_id, start, 0),),
        sessions=(),
        purchases=(),
        entitlements=(),
        deposits=(),
    )

    class ReadOnlyPort:
        async def snapshot(self) -> ClientAnalyticsFacts:
            return facts

    report = await ClientAnalyticsService(ReadOnlyPort()).report(
        start,
        start + datetime.timedelta(days=1),
        as_of=start + datetime.timedelta(days=1),
    )

    assert report.clients.registered_count == 1
    assert facts.clients[0].balance_cents == 0


def test_domain_adapters_copy_facts_without_mutating_producer_objects() -> None:
    """Проверяет копирование фактов без изменения объектов владельцев."""
    client_id = uuid.uuid4()
    entitlement_id = uuid.uuid4()
    tariff_id = uuid.uuid4()
    workstation_id = uuid.uuid4()
    session_id = uuid.uuid4()
    sale_id = uuid.uuid4()
    now = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    entitlement = Entitlement(
        id=entitlement_id,
        client_id=client_id,
        tariff_id=tariff_id,
        zone_id=None,
        duration_minutes=120,
        remaining_minutes=45,
        price_cents=800,
        queue_position=1,
        status=EntitlementStatus.ACTIVE,
        idempotency_key="ent-1",
        purchased_at=now,
    )
    session = Session(
        id=session_id,
        workstation_id=workstation_id,
        client_id=client_id,
        guest_name=None,
        status=SessionStatus.COMPLETED,
        started_at=now,
        ended_at=now + datetime.timedelta(hours=2),
        source="operator",
        created_by="operator",
        created_at=now,
        tariff_id=tariff_id,
    )
    charge = SessionCharge(
        id=uuid.uuid4(),
        session_id=session_id,
        client_id=client_id,
        balance_operation_id=uuid.uuid4(),
        tariff_id=tariff_id,
        duration_minutes=120,
        amount_cents=800,
        amount_before_discount_cents=800,
        discount_amount_cents=0,
        discount_percent_bps=0,
        discount_category=None,
        charged_by="operator",
        idempotency_key="charge-1",
        created_at=now,
    )
    sale = ProductSale(
        id=sale_id,
        product_id=uuid.uuid4(),
        product_name="Drink",
        client_id=client_id,
        guest_name=None,
        quantity=2,
        unit_price_cents=150,
        unit_cost_price_cents=50,
        total_price_cents=300,
        total_cost_price_cents=100,
        payment_method=ProductPaymentMethod.BALANCE,
        cash_shift_id=None,
        status=ProductSaleStatus.COMPLETED,
        sold_by="operator",
        idempotency_key="sale-1",
        created_at=now,
        completed_at=now,
    )
    operation = BalanceOperation(
        id=uuid.uuid4(),
        client_id=client_id,
        amount_cents=-300,
        bonus_amount=0,
        reason="product",
        actor_id="operator",
        idempotency_key="wallet-1",
        created_at=now,
        operation_type=BalanceOperationType.DEBIT,
    )

    entitlement_fact = entitlement_from_domain(entitlement)
    session_fact = session_from_domain(session, charge)
    purchase_fact = purchase_from_domain(sale)
    deposit_fact = deposit_from_domain(operation)

    assert entitlement_fact.used_minutes == 75
    assert session_fact.revenue_cents == 800
    assert purchase_fact.revenue_cents == 300
    assert deposit_fact.amount_cents == 300
    assert entitlement.remaining_minutes == 45
    assert sale.total_price_cents == 300
    assert operation.amount_cents == -300
