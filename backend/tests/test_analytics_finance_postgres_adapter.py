import datetime
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.bootstrap import build_application_services
from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.resources import InfrastructureResources
from gameclub_backend.modules.analytics.finance import (
    FinanceFactType,
    FinanceFilters,
    WalletFactType,
)
from gameclub_backend.modules.analytics.infrastructure.finance_postgres import (
    PostgresFinanceAnalyticsRepository,
    build_finance_snapshot,
)

UTC = datetime.UTC


def test_postgres_source_rows_keep_deposit_debit_separate_from_direct_payment_parts() -> None:
    """Проверяет раздельное представление пополнения, списания и прямого платежа."""
    sale_id = uuid.uuid4()
    balance_operation_id = uuid.uuid4()
    snapshot = build_finance_snapshot(
        balance_rows=[
            {
                "id": balance_operation_id,
                "client_id": uuid.uuid4(),
                "amount_cents": 1_000,
                "operation_type": "top_up",
                "created_at": datetime.datetime(2026, 9, 20, 9, tzinfo=UTC),
                "actor_id": "operator",
                "payment_parts": [{"method": "cash", "amount_cents": 1_000}],
            },
            {
                "id": uuid.uuid4(),
                "client_id": uuid.uuid4(),
                "amount_cents": 300,
                "operation_type": "debit",
                "created_at": datetime.datetime(2026, 9, 20, 10, tzinfo=UTC),
                "actor_id": "system",
                "payment_parts": [],
            },
        ],
        sale_rows=[
            {
                "id": sale_id,
                "client_id": uuid.uuid4(),
                "total_price_cents": 700,
                "payment_method": "mixed",
                "status": "completed",
                "created_at": datetime.datetime(2026, 9, 20, 11, tzinfo=UTC),
                "sold_by": "operator",
                "payment_parts": [
                    {"method": "balance", "amount_cents": 300},
                    {"method": "transfer", "amount_cents": 400},
                ],
            }
        ],
        guest_payment_rows=[],
        entitlement_rows=[],
    )

    assert len(snapshot.wallet_facts or ()) == 2
    assert {fact.fact_type for fact in snapshot.wallet_facts or ()} == {
        WalletFactType.TOP_UP,
        WalletFactType.DEBIT,
    }
    assert len(snapshot.financial_facts or ()) == 1
    financial_facts = snapshot.financial_facts
    assert financial_facts is not None
    assert financial_facts[0].fact_type is FinanceFactType.PAYMENT
    assert financial_facts[0].amount_cents == 400
    assert snapshot.refunds_available is False
    assert snapshot.history_available is False


def test_postgres_source_rows_exclude_unconfirmed_guest_payment_and_keep_part_references() -> None:
    """Проверяет отбор подтверждённого гостевого платежа и ссылку его части."""
    payment_id = uuid.uuid4()
    snapshot = build_finance_snapshot(
        balance_rows=[],
        sale_rows=[],
        guest_payment_rows=[
            {
                "id": payment_id,
                "guest_id": uuid.uuid4(),
                "total_price_cents": 500,
                "status": "pending",
                "created_at": datetime.datetime(2026, 9, 20, 12, tzinfo=UTC),
                "created_by": "operator",
                "payment_parts": [{"method": "cash", "amount_cents": 500}],
            },
            {
                "id": payment_id,
                "guest_id": uuid.uuid4(),
                "total_price_cents": 500,
                "status": "confirmed",
                "created_at": datetime.datetime(2026, 9, 20, 13, tzinfo=UTC),
                "created_by": "operator",
                "payment_parts": [{"method": "cash", "amount_cents": 500}],
            },
        ],
        entitlement_rows=[],
    )

    assert len(snapshot.financial_facts or ()) == 1
    financial_facts = snapshot.financial_facts
    assert financial_facts is not None
    fact = financial_facts[0]
    assert fact.amount_cents == 500
    assert fact.payment_method_key == "cash"
    assert fact.source_reference == f"guest_session_payment:{payment_id}:0"


def test_postgres_config_uses_postgres_finance_read_adapter() -> None:
    """Проверяет выбор PostgreSQL-адаптера финансовой аналитики в сборке."""
    services = build_application_services(
        Settings(postgres_dsn="postgresql+asyncpg://analytics:test@localhost/gameclub"),
        InfrastructureResources(checks={}),
    )

    assert isinstance(services.finance_analytics._repository, PostgresFinanceAnalyticsRepository)


def test_settled_entitlement_is_normalized_to_confirmed_payment_fact() -> None:
    """Проверяет нормализацию settled-права в подтверждённый финансовый факт."""
    snapshot = build_finance_snapshot(
        balance_rows=[],
        sale_rows=[],
        guest_payment_rows=[],
        entitlement_rows=[
            {
                "id": uuid.uuid4(),
                "client_id": uuid.uuid4(),
                "price_cents": 1_200,
                "settlement_status": "settled",
                "purchased_at": datetime.datetime(2026, 9, 20, 14, tzinfo=UTC),
                "payment_parts": [{"method": "transfer", "amount_cents": 1_200}],
            }
        ],
    )

    assert len(snapshot.financial_facts or ()) == 1
    financial_facts = snapshot.financial_facts
    assert financial_facts is not None
    assert financial_facts[0].status == "confirmed"


@pytest.mark.integration
@pytest.mark.postgres
async def test_postgres_finance_repository_reads_seeded_rows() -> None:
    """Проверяет чтение посеянных финансовых фактов из настоящего PostgreSQL."""
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run PostgreSQL finance integration test")

    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        repository = PostgresFinanceAnalyticsRepository(lambda: engine)
        snapshot = await repository.snapshot(
            FinanceFilters(
                start_at=datetime.datetime(2026, 9, 20, tzinfo=UTC),
                end_at=datetime.datetime(2026, 9, 21, tzinfo=UTC),
            )
        )
    finally:
        await engine.dispose()

    assert {fact.amount_cents for fact in snapshot.wallet_facts or ()} == {300, 1000}
    assert len(snapshot.financial_facts or ()) == 3
    assert {fact.payment_method_key for fact in snapshot.financial_facts or ()} == {
        "cash",
        "transfer",
    }
    assert all(fact.fact_type is FinanceFactType.PAYMENT for fact in snapshot.financial_facts or ())
