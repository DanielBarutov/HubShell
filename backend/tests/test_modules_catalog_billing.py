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
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import TariffLifecycle
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)

pytestmark = pytest.mark.unit

async def test_catalog_quote_selects_the_cheapest_applicable_tariff() -> None:
    """
    Проверяет сценарий «test_catalog_quote_selects_the_cheapest_applicable_tariff» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    service = CatalogService(InMemoryCatalogRepository())
    moment = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)
    await service.create_tariff("VIP hour", "vip", 60, 500, moment, None)
    selected = await service.create_tariff("VIP two hours", "vip", 120, 800, moment, None)

    quote = await service.quote(90, "vip", moment)

    assert quote.tariff_id == selected.id
    assert quote.price_cents == 800


async def test_catalog_quote_applies_highest_priority_discount_without_float() -> None:
    """
    Проверяет сценарий «test_catalog_quote_applies_highest_priority_discount_without_float» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_billing_charges_completed_session_once_with_quote_snapshot» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_billing_reconciliation_retries_after_charge_persistence_failure» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_client_debit_rejects_insufficient_spendable_balance» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_catalog_quote_ignores_inactive_and_out_of_period_discounts» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_catalog_tariff_lifecycle_requires_publish_before_quote» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_catalog_assigns_next_version_for_same_tariff_key» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
