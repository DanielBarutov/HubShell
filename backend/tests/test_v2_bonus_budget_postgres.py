import asyncio
import dataclasses
import datetime
import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from bonus_cleanup import clear_client_bonus_records
from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.infrastructure.database import application_transaction
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.domain import BalanceOperation, BalanceOperationType
from gameclub_backend.modules.clients.infrastructure.balance_transaction import (
    PostgresClientBalanceTransactionWriter,
)
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository
from gameclub_backend.modules.eventing_v2.application.analytics import (
    V2ConfirmedEventAnalyticsService,
)
from gameclub_backend.modules.eventing_v2.application.bonus_budget import (
    BonusBudgetRequest,
    BonusBudgetService,
)
from gameclub_backend.modules.eventing_v2.application.reconciliation import V2ClientFactStatus
from gameclub_backend.modules.eventing_v2.domain import V2Event, V2EventType
from gameclub_backend.modules.eventing_v2.infrastructure.bonus_budget_postgres import (
    PostgresBonusBudgetRepository,
    V2BonusBudgetModel,
)
from gameclub_backend.modules.eventing_v2.infrastructure.lease_postgres import V2SessionLeaseModel
from gameclub_backend.modules.eventing_v2.infrastructure.reconciliation_postgres import (
    PostgresV2ClientFactReconciliationRepository,
    confirmed_per_minute_debit_event,
)
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionRepository,
    PostgresSessionTransactionWriter,
)

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


async def test_pre_program_lease_cannot_silently_enable_new_bonus_policy(budget_context):
    """Действующий старый lease без исходного снимка не разрешает новый бонусный бюджет."""
    service, clients, request, principal, _, provider = budget_context
    async with application_transaction(provider) as transaction:
        await transaction.execute(
            text("DELETE FROM client_bonus_sessions WHERE session_id=:id"),
            {"id": request.session_id},
        )
    assert not (await service.quote(request, principal)).bonus_allowed
    with pytest.raises(ApplicationError, match="disabled"):
        await service.issue(request, principal)
    assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0


async def test_minute_quote_includes_own_reserve_and_fractional_source_carry(budget_context):
    """Расчёт минуты учитывает резерв и доли начисления, пакет использует свободные бонусы."""
    service, clients, request, principal, _, provider = budget_context
    await service.issue(request, principal)
    operation = BalanceOperation(
        uuid.uuid4(),
        request.client_id,
        -19,
        0,
        "Previous minutes",
        "device",
        f"carry:{request.client_id}",
        datetime.datetime.now(datetime.UTC),
        BalanceOperationType.DEBIT,
    )
    writer = PostgresClientBalanceTransactionWriter()
    async with application_transaction(provider) as transaction:
        lease = await transaction.get(V2SessionLeaseModel, request.session_id)
        snapshot = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload()
        snapshot.ParseFromString(lease.snapshot_payload)
        snapshot.tariffs[0].per_minute_price_cents = 101
        lease.snapshot_payload = snapshot.SerializeToString(deterministic=True)
        assert await writer.apply(transaction, operation) is not None
        await writer.confirm_minute(
            transaction,
            request.client_id,
            request.session_id,
            operation.id,
            uuid.uuid4(),
            "device",
            operation.created_at,
        )
    quote = await service.quote(
        dataclasses.replace(request, idempotency_key="quote-carry"), principal
    )
    assert (quote.price_cents, quote.bonus_cents, quote.money_cents, quote.earned_bonus_cents) == (
        101,
        20,
        81,
        5,
    )
    assert quote.available_bonus_cents == 0
    package_quote = await clients.quote_bonus_game(request.client_id, 101, True, request.session_id)
    assert package_quote.bonus_cents == 0
    assert package_quote.earned_bonus_cents == 5


@pytest.mark.parametrize("enable_first", [False, True])
async def test_cancel_budget_survives_delayed_enable_and_preserves_newer_budget(
    budget_context, enable_first
):
    """Отмена закрывает поздний запрос и не освобождает резерв нового разрешения при повторе."""
    service, clients, request, principal, _, provider = budget_context
    if enable_first:
        await service.issue(request, principal)
    await service.cancel(request, principal)
    async with application_transaction(provider) as transaction:
        audit = (
            await transaction.execute(
                text(
                    "SELECT actor_id, created_at FROM audit_events "
                    "WHERE action='v2.minute_bonus.cancelled' "
                    "AND request_id=:key AND actor_id=:actor"
                ),
                {"key": request.idempotency_key, "actor": f"client:{request.client_id}"},
            )
        ).one()
        assert audit.actor_id == f"client:{request.client_id}"
        assert audit.created_at is not None
    assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0
    with pytest.raises(ApplicationError, match="cancelled"):
        await service.issue(request, principal)
    next_grant = await service.issue(
        dataclasses.replace(request, idempotency_key="new-enable"), principal
    )
    assert next_grant.budget_cents == 10000
    await service.cancel(request, principal)
    assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 10000


async def test_budget_cancel_waits_for_confirmed_checkpoint(budget_context):
    """Отмена не освобождает резерв, пока локальная цепочка ещё не подтверждена."""
    service, clients, request, principal, _, _ = budget_context
    await service.issue(request, principal)
    with pytest.raises(ApplicationError, match="подтверждения"):
        await service.cancel(
            dataclasses.replace(request, last_sequence=1, last_payload_hash="a" * 64), principal
        )
    assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 10000


async def test_pending_budget_refresh_preserves_old_offline_budget_until_disable(budget_context):
    """Потеря ответа на увеличение не запрещает расход прежнего подписанного бюджета."""
    service, clients, request, principal, _, provider = budget_context
    old = await service.issue(request, principal)
    await service.issue(dataclasses.replace(request, idempotency_key="increase"), principal)
    repo = PostgresV2ClientFactReconciliationRepository(
        provider, clients=PostgresClientBalanceTransactionWriter()
    )
    first = minute_fact(
        request,
        V2EventType.PER_MINUTE_DEBIT,
        {
            "tariff_id": "minute",
            "price_cents": 100,
            "amount_cents": 80,
            "bonus_amount_cents": 20,
            "bonus_grant_id": str(old.id),
        },
    )
    assert (await repo.accept(first)).status is V2ClientFactStatus.ACCEPTED
    cancelled = dataclasses.replace(
        request, idempotency_key="increase", last_sequence=1, last_payload_hash=first.payload_hash
    )
    await service.cancel(cancelled, principal)
    assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0
    late = minute_fact(
        request,
        V2EventType.PER_MINUTE_DEBIT,
        {
            "tariff_id": "minute",
            "price_cents": 100,
            "amount_cents": 80,
            "bonus_amount_cents": 20,
            "bonus_grant_id": str(old.id),
        },
        2,
        first.payload_hash,
    )
    assert (await repo.accept(late)).status is V2ClientFactStatus.CONFLICT


@pytest.fixture
async def budget_context(request):
    test_limit = getattr(request.node, "callspec", None)
    test_limit = test_limit.params.get("limit") if test_limit is not None else None
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN for bonus budget checks")
    engine = create_async_engine(dsn)

    def provider():
        return engine

    clients = ClientService(PostgresClientRepository(provider))
    client = await clients.create(f"Budget{uuid.uuid4().hex[:20]}")
    initial_policy = await clients.get_bonus_policy()
    settings_actor = Principal(
        "owner", SubjectType.OPERATOR, frozenset(), frozenset({"settings.manage"})
    )
    request = BonusBudgetRequest(
        client.id, uuid.uuid4(), "budget-device", uuid.uuid4(), 1, 0, None, "enable"
    )
    repository = PostgresBonusBudgetRepository(provider)
    service = BonusBudgetService(repository, clients, lambda: application_transaction(provider))
    principal = Principal(
        str(client.id),
        SubjectType.CLIENT,
        frozenset({"client"}),
        frozenset({"client.portal"}),
        request.device_id,
    )
    try:
        if test_limit is not None:
            await clients.update_bonus_policy(
                dataclasses.replace(initial_policy, payment_limit_bps=test_limit),
                settings_actor,
                f"{client.id}:fixture-limit",
            )
        await clients.top_up(client.id, 10000, 100, "Opening", "owner", f"opening:{client.id}")
        now = datetime.datetime.now(datetime.UTC)
        await PostgresSessionRepository(provider).save(
            Session(
                id=request.session_id,
                workstation_id=uuid.uuid4(),
                client_id=client.id,
                guest_name=None,
                status=SessionStatus.ACTIVE,
                started_at=now,
                ended_at=None,
                source="local_ledger",
                created_by="test",
                created_at=now,
            )
        )
        await clients.begin_bonus_session(client.id, request.session_id)
        snapshot = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload()
        snapshot.tariffs.add(tariff_id="minute", is_per_minute=True, per_minute_price_cents=100)
        async with application_transaction(provider) as transaction:
            transaction.add(
                V2SessionLeaseModel(
                    session_id=request.session_id,
                    client_id=client.id,
                    device_id=request.device_id,
                    snapshot_id=request.snapshot_id,
                    snapshot_version=1,
                    policy_version="test",
                    status="active",
                    issued_at=datetime.datetime.now(datetime.UTC),
                    snapshot_payload=snapshot.SerializeToString(deterministic=True),
                )
            )
        yield service, clients, request, principal, repository, provider
    finally:
        if test_limit is not None:
            await clients.update_bonus_policy(
                initial_policy, settings_actor, f"{client.id}:fixture-restore"
            )
        async with engine.begin() as connection:
            for table in (
                "v2_confirmed_client_facts",
                "v2_event_inbox",
                "v2_server_outbox",
                "v2_session_chains",
                "gaming_sessions",
            ):
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE client_id=:id"), {"id": client.id}
                )
            await connection.execute(
                text("DELETE FROM v2_bonus_budgets WHERE client_id=:id"), {"id": client.id}
            )
            await connection.execute(
                text("DELETE FROM v2_session_leases WHERE client_id=:id"), {"id": client.id}
            )
            await clear_client_bonus_records(connection, client.id)
            await connection.execute(
                text("DELETE FROM audit_events WHERE resource_path LIKE :prefix"),
                {"prefix": f"clients/{client.id}/%"},
            )
            await connection.execute(
                text("DELETE FROM client_bonus_program_changes WHERE idempotency_key LIKE :prefix"),
                {"prefix": f"{client.id}:%"},
            )
            await connection.execute(
                text("DELETE FROM balance_operations WHERE client_id=:id"), {"id": client.id}
            )
            await connection.execute(text("DELETE FROM clients WHERE id=:id"), {"id": client.id})
        await engine.dispose()


def minute_fact(request, kind, payload, sequence=1, previous_hash=None):
    return V2Event.create(
        operation_id=uuid.uuid4(),
        event_type=kind,
        producer_id=f"workstation:{request.device_id}",
        client_id=request.client_id,
        session_id=request.session_id,
        device_id=request.device_id,
        sequence=sequence,
        previous_hash=previous_hash,
        occurred_at=datetime.datetime.now(datetime.UTC),
        payload={
            "snapshot_id": str(request.snapshot_id),
            "snapshot_version": request.snapshot_version,
            **payload,
        },
    )


@pytest.mark.parametrize("limit", [2000, 10000])
async def test_bonus_minute_split_disable_release_and_confirmed_money(budget_context, limit):
    """Подтверждает 20/100% бонусной минуты и освобождает остаток только после её факта."""
    service, clients, request, principal, _, provider = budget_context
    original = await clients.get_bonus_policy()
    admin = Principal("owner", SubjectType.OPERATOR, frozenset(), frozenset({"settings.manage"}))
    try:
        await clients.update_bonus_policy(
            dataclasses.replace(original, payment_limit_bps=limit),
            admin,
            f"{request.client_id}:limit",
        )
        quote = await service.quote(request, principal)
        assert quote.price_cents == 100
        assert quote.bonus_cents == limit // 100
        assert quote.money_cents == 100 - limit // 100
        assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0
        grant = await service.issue(request, principal)
        repo = PostgresV2ClientFactReconciliationRepository(
            provider,
            PostgresSessionTransactionWriter(),
            clients=PostgresClientBalanceTransactionWriter(),
        )
        bonus = limit // 100
        first = minute_fact(
            request,
            V2EventType.PER_MINUTE_DEBIT,
            {
                "tariff_id": "minute",
                "price_cents": 100,
                "amount_cents": 100 - bonus,
                "bonus_amount_cents": bonus,
                "bonus_grant_id": str(grant.id),
            },
        )
        accepted, duplicate = await asyncio.gather(repo.accept(first), repo.accept(first))
        assert {accepted.status, duplicate.status} == {
            V2ClientFactStatus.ACCEPTED,
            V2ClientFactStatus.DUPLICATE,
        }
        assert (await clients.get(request.client_id)).balance_cents == 10000 - (100 - bonus)
        assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 10000 - bonus
        confirmed = confirmed_per_minute_debit_event(first, datetime.datetime.now(datetime.UTC))
        financial = V2ConfirmedEventAnalyticsService.events_for(confirmed)
        assert len(financial) == (0 if limit == 10000 else 1)
        disabled = minute_fact(
            request,
            V2EventType.BONUS_PAYMENT_DISABLED,
            {"bonus_grant_id": str(grant.id)},
            2,
            first.payload_hash,
        )
        next_minute = minute_fact(
            request,
            V2EventType.PER_MINUTE_DEBIT,
            {"tariff_id": "minute", "amount_cents": 100},
            3,
            disabled.payload_hash,
        )
        assert (await repo.accept(next_minute)).status is V2ClientFactStatus.GAP
        assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 10000 - bonus
        assert (await repo.accept(disabled)).status is V2ClientFactStatus.ACCEPTED
        assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0
        assert (await repo.accept(next_minute)).status is V2ClientFactStatus.ACCEPTED
        stopped = minute_fact(
            request, V2EventType.SESSION_STOPPED, {"reason": "test"}, 4, next_minute.payload_hash
        )
        assert (await repo.accept(stopped)).status is V2ClientFactStatus.ACCEPTED
        assert await clients.get_pending_bonus_cents(request.client_id) == 0
        assert (await clients.get_bonus_wallet(request.client_id)).total_cents == 10000 - bonus + (
            200 - bonus
        ) * original.game_rate_bps // 10000
    finally:
        await clients.update_bonus_policy(original, admin, f"{request.client_id}:restore")


async def test_bonus_minute_rejects_forged_price_and_rolls_back_after_wallet_write(budget_context):
    """Подмена signed цены не проходит, а сбой после списания откатывает обе части и grant."""
    service, clients, request, principal, _, provider = budget_context
    grant = await service.issue(request, principal)
    payload = {
        "tariff_id": "minute",
        "price_cents": 100,
        "amount_cents": 80,
        "bonus_amount_cents": 20,
        "bonus_grant_id": str(grant.id),
    }
    repo = PostgresV2ClientFactReconciliationRepository(
        provider, clients=PostgresClientBalanceTransactionWriter()
    )
    forged = minute_fact(
        request, V2EventType.PER_MINUTE_DEBIT, {**payload, "price_cents": 200, "amount_cents": 180}
    )
    assert (await repo.accept(forged)).status is V2ClientFactStatus.CONFLICT

    class FailingWriter(PostgresClientBalanceTransactionWriter):
        async def apply_bonus_minute(self, transaction, payment):
            assert await super().apply_bonus_minute(transaction, payment)
            raise RuntimeError("after minute wallet write")

    failing = PostgresV2ClientFactReconciliationRepository(provider, clients=FailingWriter())
    event = minute_fact(request, V2EventType.PER_MINUTE_DEBIT, payload)
    with pytest.raises(RuntimeError, match="after minute wallet write"):
        await failing.accept(event)
    assert (await clients.get(request.client_id)).balance_cents == 10000
    assert (await clients.get_bonus_wallet(request.client_id)).total_cents == 10000
    async with application_transaction(provider) as transaction:
        assert (await transaction.get(V2BonusBudgetModel, grant.id)).spent_cents == 0
    assert (await repo.accept(event)).status is V2ClientFactStatus.ACCEPTED


async def test_bonus_budget_reserves_all_and_retries_immutably(budget_context):
    """Резервирует весь остаток один раз и возвращает прежнее разрешение при повторе."""
    service, clients, request, principal, _, provider = budget_context
    first, repeated = await asyncio.gather(
        service.issue(request, principal), service.issue(request, principal)
    )
    assert first == repeated
    assert first.budget_cents == 10000
    assert first.version == 1
    wallet = await clients.get_bonus_wallet(request.client_id)
    assert wallet.reserved_cents == 10000
    assert wallet.available_cents == 0
    with pytest.raises(ApplicationError, match="another request"):
        await service.issue(
            dataclasses.replace(request, last_sequence=1, last_payload_hash="a" * 64), principal
        )
    async with application_transaction(provider) as transaction:
        rows = (
            await transaction.scalars(
                select(V2BonusBudgetModel).where(
                    V2BonusBudgetModel.session_id == request.session_id
                )
            )
        ).all()
        assert len(rows) == 1


async def test_bonus_budget_requires_matching_confirmed_checkpoint_and_device(budget_context):
    """Неподтверждённые списания и чужая идентичность не разрешают резерв."""
    service, clients, request, principal, _, _ = budget_context
    with pytest.raises(ApplicationError, match="подтверждения"):
        await service.issue(
            dataclasses.replace(request, last_sequence=1, last_payload_hash="a" * 64), principal
        )
    with pytest.raises(ApplicationError, match="authorized"):
        await service.issue(request, dataclasses.replace(principal, device_id="another-device"))
    with pytest.raises(ApplicationError, match="lease"):
        await service.issue(dataclasses.replace(request, snapshot_id=uuid.uuid4()), principal)
    assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0


async def test_bonus_budget_save_failure_rolls_back_reserve_and_previous_grant(
    budget_context, monkeypatch
):
    """Сбой сохранения разрешения откатывает резерв и замену прежней версии."""
    service, clients, request, principal, repository, provider = budget_context
    save = repository.save

    async def fail_after_save(grant):
        await save(grant)
        raise RuntimeError("grant save failure")

    monkeypatch.setattr(repository, "save", fail_after_save)
    with pytest.raises(RuntimeError, match="grant save failure"):
        await service.issue(request, principal)
    assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0
    async with application_transaction(provider) as transaction:
        assert (
            await transaction.scalar(
                select(V2BonusBudgetModel.id).where(
                    V2BonusBudgetModel.session_id == request.session_id
                )
            )
            is None
        )
    monkeypatch.setattr(repository, "save", save)
    first = await service.issue(request, principal)
    monkeypatch.setattr(repository, "save", fail_after_save)
    with pytest.raises(RuntimeError, match="grant save failure"):
        await service.issue(dataclasses.replace(request, idempotency_key="increase"), principal)
    async with application_transaction(provider) as transaction:
        active = await transaction.scalar(
            select(V2BonusBudgetModel).where(
                V2BonusBudgetModel.session_id == request.session_id,
                V2BonusBudgetModel.active.is_(True),
            )
        )
        assert active.id == first.id


@pytest.mark.parametrize("limit", [2000, 10000])
async def test_kafka_worker_confirms_bonus_minute_once_and_releases_reserve(budget_context, limit):
    """Реальный Kafka worker однократно списывает бонусы и завершает резерв после stop."""
    from aiokafka import AIOKafkaProducer

    from gameclub_backend.modules.eventing_v2.infrastructure.protobuf import event_to_protobuf

    bootstrap = os.getenv("GAMECLUB_TEST_KAFKA_BOOTSTRAP_SERVERS")
    if not bootstrap:
        pytest.skip("Set GAMECLUB_TEST_KAFKA_BOOTSTRAP_SERVERS and run V2 client facts worker")
    service, clients, request, principal, _, provider = budget_context
    grant = await service.issue(request, principal)
    bonus = limit // 100
    minute = minute_fact(
        request,
        V2EventType.PER_MINUTE_DEBIT,
        {
            "tariff_id": "minute",
            "price_cents": 100,
            "amount_cents": 100 - bonus,
            "bonus_amount_cents": bonus,
            "bonus_grant_id": str(grant.id),
        },
    )
    disabled = minute_fact(
        request,
        V2EventType.BONUS_PAYMENT_DISABLED,
        {"bonus_grant_id": str(grant.id)},
        2,
        minute.payload_hash,
    )
    stop = minute_fact(
        request,
        V2EventType.SESSION_STOPPED,
        {"reason": "bonus-kafka-test"},
        3,
        disabled.payload_hash,
    )
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap, acks="all")
    try:
        await producer.start()
        for event in (minute, minute, disabled, stop):
            await producer.send_and_wait(
                "v2.client-events",
                event_to_protobuf(event).SerializeToString(),
                key=str(request.session_id).encode(),
            )
        confirmed = 0
        for _ in range(100):
            async with application_transaction(provider) as transaction:
                confirmed = await transaction.scalar(
                    text("SELECT count(*) FROM v2_confirmed_client_facts WHERE session_id=:id"),
                    {"id": request.session_id},
                )
            if confirmed == 3:
                break
            await asyncio.sleep(0.1)
        assert confirmed == 3
        assert (await clients.get(request.client_id)).balance_cents == 10000 - (100 - bonus)
        wallet = await clients.get_bonus_wallet(request.client_id)
        assert wallet.reserved_cents == 0
        assert wallet.total_cents == 10000 - bonus + (100 - bonus) * 500 // 10000
        assert await clients.get_pending_bonus_cents(request.client_id) == 0
    finally:
        await producer.stop()


async def test_logout_before_package_facts_releases_bonus_reserve(budget_context):
    """Выход до доставки фактов пакета не разрывает цепочку и освобождает бонусный резерв."""
    from types import SimpleNamespace

    from gameclub_backend.modules.entitlements.application.service import EntitlementService
    from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus
    from gameclub_backend.modules.entitlements.infrastructure.postgres import (
        PostgresEntitlementRepository,
        PostgresEntitlementTransactionWriter,
    )
    from gameclub_backend.modules.sessions.application.service import SessionService

    service, clients, request, principal, _, provider = budget_context
    await service.issue(request, principal)
    packages = PostgresEntitlementRepository(provider)
    package_id, tariff_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.datetime.now(datetime.UTC)
    await packages.create(
        Entitlement(
            id=package_id,
            client_id=request.client_id,
            tariff_id=tariff_id,
            zone_id=None,
            duration_minutes=3,
            remaining_minutes=3,
            price_cents=5000,
            queue_position=1,
            status=EntitlementStatus.ACTIVE,
            idempotency_key=str(package_id),
            purchased_at=now,
            activated_at=now,
        )
    )
    try:
        consumed = minute_fact(
            request,
            V2EventType.PACKAGE_CONSUMED,
            {
                "package_id": str(package_id),
                "tariff_id": str(tariff_id),
                "remaining_minutes": 2,
            },
        )
        burned = minute_fact(
            request,
            V2EventType.PACKAGE_BURNED,
            {
                "package_id": str(package_id),
                "tariff_id": str(tariff_id),
                "remaining_minutes": 2,
            },
            2,
            consumed.payload_hash,
        )
        stopped = minute_fact(
            request, V2EventType.SESSION_STOPPED, {"reason": "logout"}, 3, burned.payload_hash
        )
        sessions = SessionService(
            PostgresSessionRepository(provider),
            SimpleNamespace(),
            clients,
            entitlements=EntitlementService(packages, SimpleNamespace(), clients),
            bonuses=clients,
        )
        await sessions.stop(request.session_id)
        assert (await packages.get(package_id)).status is EntitlementStatus.BURNED
        assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 10000
        repo = PostgresV2ClientFactReconciliationRepository(
            provider,
            PostgresSessionTransactionWriter(),
            entitlement_writer=PostgresEntitlementTransactionWriter(),
            clients=PostgresClientBalanceTransactionWriter(),
        )
        for payload in (
            {"package_id": str(package_id), "tariff_id": str(tariff_id), "remaining_minutes": 1},
            {"package_id": str(package_id), "tariff_id": str(uuid.uuid4()), "remaining_minutes": 2},
        ):
            invalid = minute_fact(request, V2EventType.PACKAGE_CONSUMED, payload)
            assert (await repo.accept(invalid)).status is V2ClientFactStatus.CONFLICT
        late = minute_fact(
            request,
            V2EventType.PACKAGE_CONSUMED,
            {
                "package_id": str(package_id),
                "tariff_id": str(tariff_id),
                "remaining_minutes": 2,
            },
        )
        assert (await repo.accept(late)).status is V2ClientFactStatus.CONFLICT
        for event in (consumed, burned, stopped):
            result = await repo.accept(event)
            assert result.status is V2ClientFactStatus.ACCEPTED, result.message
            assert (await repo.accept(event)).status is V2ClientFactStatus.DUPLICATE
            assert (await packages.get(package_id)).status is EntitlementStatus.BURNED
        assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0
        assert (await clients.get_bonus_wallet(request.client_id)).total_cents == 10000
    finally:
        async with application_transaction(provider) as transaction:
            await transaction.execute(
                text("DELETE FROM client_entitlements WHERE id=:id"), {"id": package_id}
            )


@pytest.mark.parametrize("limit", [10000])
async def test_bonus_can_enable_again_after_disable_in_same_session(budget_context, limit):
    """Повторное включение после минуты без бонусов не требует новой сессии и не тратит деньги."""
    service, clients, request, principal, _, provider = budget_context
    first = await service.issue(request, principal)
    repo = PostgresV2ClientFactReconciliationRepository(
        provider,
        PostgresSessionTransactionWriter(),
        clients=PostgresClientBalanceTransactionWriter(),
    )
    event = minute_fact(
        request,
        V2EventType.PER_MINUTE_DEBIT,
        {
            "tariff_id": "minute",
            "price_cents": 100,
            "amount_cents": 0,
            "bonus_amount_cents": 100,
            "bonus_grant_id": str(first.id),
        },
    )
    assert (await repo.accept(event)).status is V2ClientFactStatus.ACCEPTED
    disabled = minute_fact(
        request,
        V2EventType.BONUS_PAYMENT_DISABLED,
        {"bonus_grant_id": str(first.id)},
        2,
        event.payload_hash,
    )
    assert (await repo.accept(disabled)).status is V2ClientFactStatus.ACCEPTED
    assert (await clients.get_bonus_wallet(request.client_id)).reserved_cents == 0
    ordinary = minute_fact(
        request,
        V2EventType.PER_MINUTE_DEBIT,
        {"tariff_id": "minute", "amount_cents": 100},
        3,
        disabled.payload_hash,
    )
    assert (await repo.accept(ordinary)).status is V2ClientFactStatus.ACCEPTED
    again = dataclasses.replace(
        request,
        idempotency_key="enable-again",
        last_sequence=3,
        last_payload_hash=ordinary.payload_hash,
    )
    quote = await service.quote(again, principal)
    assert quote.bonus_allowed and quote.can_pay
    assert quote.money_cents == 0
    second = await service.issue(again, principal)
    assert second.id != first.id and second.version > first.version
    next_minute = minute_fact(
        request,
        V2EventType.PER_MINUTE_DEBIT,
        {
            "tariff_id": "minute",
            "price_cents": 100,
            "amount_cents": 0,
            "bonus_amount_cents": 100,
            "bonus_grant_id": str(second.id),
        },
        4,
        ordinary.payload_hash,
    )
    assert (await repo.accept(next_minute)).status is V2ClientFactStatus.ACCEPTED
    assert (await clients.get(request.client_id)).balance_cents == 9900
    assert (await clients.get_bonus_wallet(request.client_id)).total_cents == 9800
