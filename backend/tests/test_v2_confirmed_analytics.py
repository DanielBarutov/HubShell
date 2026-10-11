import asyncio
import datetime
import os
import uuid

import pytest
from aiokafka import AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.jobs.reports import project_analytics_events
from gameclub_backend.modules.analytics.heavy_memory import InMemoryAnalyticsHeavyRepository
from gameclub_backend.modules.analytics.projection import AnalyticsProjectionService
from gameclub_backend.modules.eventing_v2.application.analytics import (
    V2ConfirmedAnalyticsInboxService,
    V2ConfirmedEventAnalyticsService,
)
from gameclub_backend.modules.eventing_v2.application.deposit import V2DepositCreditCommand
from gameclub_backend.modules.eventing_v2.application.service import V2InboxService
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2InboxResult,
    V2InboxStatus,
)
from gameclub_backend.modules.eventing_v2.infrastructure.confirmed_analytics_postgres import (
    PostgresV2ConfirmedAnalyticsRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.deposit_postgres import (
    PostgresV2DepositCreditRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.faststream import (
    V2ConfirmedAnalyticsConsumer,
)
from gameclub_backend.modules.eventing_v2.infrastructure.memory import InMemoryV2InboxRepository
from gameclub_backend.modules.eventing_v2.infrastructure.protobuf import event_to_protobuf
from gameclub_backend.modules.eventing_v2.infrastructure.reconciliation_postgres import (
    V2ConfirmedClientFactModel,
)
from gameclub_backend.modules.eventing_v2.infrastructure.reconciliation_postgres import (
    confirmed_per_minute_debit_event as build_confirmed_per_minute_debit_event,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart


def confirmed_deposit_event():
    command = V2DepositCreditCommand(
        payment_operation_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        device_id="v2-analytics-test",
        amount_delta_cents=500,
        currency="RUB",
        reason="V2 analytics test",
        actor_id="operator:test",
        payment_parts=(PaymentPart("cash", 200), PaymentPart("transfer", 300)),
        cash_shift_id=uuid.uuid4(),
    )
    return PostgresV2DepositCreditRepository._confirmed_domain_event(
        command, datetime.datetime(2026, 9, 28, tzinfo=datetime.UTC)
    )


def confirmed_per_minute_debit_event() -> V2Event:
    source = V2Event.create(
        event_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        operation_id=uuid.uuid4(),
        event_type=V2EventType.PER_MINUTE_DEBIT,
        producer_id="workstation:v2-analytics-test",
        client_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        device_id="v2-analytics-test",
        sequence=1,
        occurred_at=datetime.datetime(2026, 9, 28, 12, tzinfo=datetime.UTC),
        payload={
            "amount_cents": 125,
            "balance_after_cents": 875,
            "tariff_id": "per-minute-vip",
            "snapshot_id": str(uuid.uuid4()),
            "snapshot_version": 1,
        },
    )
    confirmed = build_confirmed_per_minute_debit_event(
        source,
        datetime.datetime(2026, 9, 28, 12, 1, tzinfo=datetime.UTC),
    )
    assert confirmed is not None
    return confirmed


@pytest.mark.asyncio
async def test_confirmed_deposit_is_split_by_payment_method_and_replay_is_idempotent() -> None:
    """Проверяет заявленное поведение backend."""
    projection = AnalyticsProjectionService(InMemoryAnalyticsHeavyRepository())
    service = V2ConfirmedAnalyticsInboxService(
        V2InboxService(InMemoryV2InboxRepository(), "confirmed_analytics"),
        V2ConfirmedEventAnalyticsService(projection),
    )
    event = confirmed_deposit_event()

    first = await service.accept(event)
    second = await service.accept(event)

    assert first.status.value == "accepted"
    assert second.status.value == "duplicate"
    assert await projection.consume_once() == 2
    assert await projection.read_total("deposit_income_cents") == 500


@pytest.mark.asyncio
async def test_client_event_cannot_enter_confirmed_analytics() -> None:
    """Проверяет заявленное поведение backend."""
    projection = AnalyticsProjectionService(InMemoryAnalyticsHeavyRepository())
    service = V2ConfirmedEventAnalyticsService(projection)
    event = confirmed_deposit_event()
    client_event = event.__class__.create(
        operation_id=event.operation_id,
        event_type=event.event_type,
        producer_id="client:untrusted",
        client_id=event.client_id,
        session_id=event.session_id,
        device_id=event.device_id,
        sequence=event.sequence,
        occurred_at=event.occurred_at,
        payload={"amount_delta_cents": 500},
    )

    with pytest.raises(ValueError, match="server-confirmed"):
        await service.ingest(client_event)


@pytest.mark.asyncio
async def test_confirmed_per_minute_debit_is_deposit_spending_not_new_revenue() -> None:
    """Проверяет заявленное поведение backend."""
    projection = AnalyticsProjectionService(InMemoryAnalyticsHeavyRepository())
    event = confirmed_per_minute_debit_event()

    await V2ConfirmedEventAnalyticsService(projection).ingest(event)

    assert await projection.consume_once() == 1
    assert await projection.read_total("wallet_debit_cents") == 125
    assert await projection.read_total("revenue_cents") == 0
    stored = await projection.read("wallet_debit_cents")
    assert stored[0]["dimensions"] == {"tariff": "per-minute-vip"}


def test_confirmed_per_minute_debit_does_not_expose_client_balance() -> None:
    """Проверяет заявленное поведение backend."""
    event = confirmed_per_minute_debit_event()

    assert "balance_after_cents" not in event.payload_json
    assert event.producer_id == "server:reconciliation"
    assert event.causation_id is not None


@pytest.mark.asyncio
async def test_confirmed_analytics_consumer_commits_or_moves_invalid_event_to_dlq() -> None:
    """Kafka offset допустим только после analytics commit либо записи в DLQ."""

    class RecordingRejectedEvents:
        items: list[tuple[bytes, str]] = []

        async def publish_rejected(self, payload: bytes, reason_code: str) -> None:
            self.items.append((payload, reason_code))

    source = confirmed_deposit_event()
    accepted_service = V2ConfirmedAnalyticsInboxService(
        V2InboxService(InMemoryV2InboxRepository(), "confirmed_analytics"),
        V2ConfirmedEventAnalyticsService(
            AnalyticsProjectionService(InMemoryAnalyticsHeavyRepository())
        ),
    )
    rejected = RecordingRejectedEvents()
    consumer = V2ConfirmedAnalyticsConsumer(accepted_service, rejected)
    payload = event_to_protobuf(source).SerializeToString()

    accepted = await consumer.accept_payload(payload)
    invalid = await consumer.accept_payload(b"not-protobuf")

    assert accepted is not None and accepted.status is V2InboxStatus.ACCEPTED
    assert invalid is None
    assert rejected.items == [(b"not-protobuf", "invalid_confirmed_event")]


@pytest.mark.asyncio
async def test_confirmed_analytics_consumer_moves_conflict_to_dlq() -> None:
    """Конфликт operation id не подтверждается как нормальная analytics доставка."""

    class RecordingRejectedEvents:
        items: list[tuple[bytes, str]] = []

        async def publish_rejected(self, payload: bytes, reason_code: str) -> None:
            self.items.append((payload, reason_code))

    class ConflictHandler:
        async def accept(self, event) -> V2InboxResult:
            return V2InboxResult(
                V2InboxStatus.CONFLICT,
                event.event_id,
                event.operation_id,
                "conflict",
            )

    source = confirmed_deposit_event()
    payload = event_to_protobuf(source).SerializeToString()
    rejected = RecordingRejectedEvents()
    result = await V2ConfirmedAnalyticsConsumer(ConflictHandler(), rejected).accept_payload(payload)

    assert result is not None and result.status is V2InboxStatus.CONFLICT
    assert rejected.items == [(payload, "confirmed_analytics_conflict")]


@pytest.mark.asyncio
async def test_postgres_confirmed_analytics_inbox_and_outbox_commit_together() -> None:
    """Проверяет заявленное поведение backend."""
    postgres_dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not postgres_dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN for confirmed analytics PostgreSQL test")
    engine = create_async_engine(postgres_dsn)
    event = confirmed_deposit_event()
    repository = PostgresV2ConfirmedAnalyticsRepository(lambda: engine)
    try:
        accepted = await repository.accept(event)
        duplicate = await repository.accept(event)
        async with engine.connect() as connection:
            inbox_count = await connection.scalar(
                text("SELECT count(*) FROM v2_event_inbox WHERE event_id = :event_id"),
                {"event_id": event.event_id},
            )
            outbox_count = await connection.scalar(
                text("SELECT count(*) FROM analytics_outbox_events WHERE aggregate_id = :id"),
                {"id": str(event.operation_id)},
            )
        assert accepted.status.value == "accepted"
        assert duplicate.status.value == "duplicate"
        assert inbox_count == 1
        assert outbox_count == 2
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM analytics_outbox_events WHERE aggregate_id = :id"),
                {"id": str(event.operation_id)},
            )
            await connection.execute(
                text("DELETE FROM v2_event_inbox WHERE event_id = :event_id"),
                {"event_id": event.event_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_rebuilds_analytics_only_from_confirmed_current_debit_fact() -> None:
    """Проверяет заявленное поведение backend."""
    postgres_dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not postgres_dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN for V2 analytics backfill test")
    engine = create_async_engine(postgres_dsn)
    source = V2Event.create(
        event_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        operation_id=uuid.uuid4(),
        event_type=V2EventType.PER_MINUTE_DEBIT,
        producer_id="workstation:v2-backfill-test",
        client_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        device_id="v2-backfill-test",
        sequence=1,
        occurred_at=datetime.datetime(2026, 9, 28, 12, tzinfo=datetime.UTC),
        payload={
            "amount_cents": 225,
            "balance_after_cents": 775,
            "tariff_id": "per-minute-backfill",
            "snapshot_id": str(uuid.uuid4()),
            "snapshot_version": 1,
        },
    )
    legacy = V2Event.create(
        event_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        operation_id=uuid.uuid4(),
        event_type=V2EventType.PER_MINUTE_DEBIT,
        producer_id="workstation:v2-backfill-test",
        client_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        device_id="v2-backfill-test-legacy",
        sequence=1,
        occurred_at=datetime.datetime(2026, 9, 28, 12, tzinfo=datetime.UTC),
        payload={
            "debit_delta_cents": 225,
            "tariff_id": "per-minute-legacy",
            "snapshot_id": str(uuid.uuid4()),
            "snapshot_version": 1,
        },
    )
    confirmed_at = datetime.datetime(2026, 9, 28, 12, 1, tzinfo=datetime.UTC)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM v2_analytics_backfill_runs "
                    "WHERE name = 'v2_confirmed_per_minute_debits_v1'"
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO v2_confirmed_client_facts
                      (event_id, operation_id, event_type, producer_id, client_id, session_id,
                       device_id, sequence, occurred_at, causation_id, correlation_id, traceparent,
                       payload_json, payload_hash, previous_hash, schema_version, confirmed_at)
                    VALUES
                      (:event_id, :operation_id, :event_type, :producer_id, :client_id, :session_id,
                       :device_id, :sequence, :occurred_at, :causation_id, :correlation_id,
                       :traceparent,
                       :payload_json, :payload_hash, :previous_hash, :schema_version, :confirmed_at)
                    """
                ),
                V2ConfirmedClientFactModel.values_from_event(source, confirmed_at),
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO v2_confirmed_client_facts
                      (event_id, operation_id, event_type, producer_id, client_id, session_id,
                       device_id, sequence, occurred_at, causation_id, correlation_id,
                       traceparent, payload_json, payload_hash, previous_hash, schema_version,
                       confirmed_at)
                    VALUES
                      (:event_id, :operation_id, :event_type, :producer_id, :client_id, :session_id,
                       :device_id, :sequence, :occurred_at, :causation_id, :correlation_id,
                       :traceparent, :payload_json, :payload_hash, :previous_hash, :schema_version,
                       :confirmed_at)
                    """
                ),
                V2ConfirmedClientFactModel.values_from_event(legacy, confirmed_at),
            )

        repository = PostgresV2ConfirmedAnalyticsRepository(lambda: engine)
        first = await repository.backfill_per_minute_debits(limit=1)
        second = await repository.backfill_per_minute_debits(limit=1)
        third = await repository.backfill_per_minute_debits(limit=1)
        async with engine.connect() as connection:
            outbox_count = await connection.scalar(
                text(
                    """
                    SELECT count(*) FROM analytics_outbox_events
                    WHERE aggregate_type = 'v2_per_minute_debit' AND aggregate_id = :aggregate_id
                    """
                ),
                {"aggregate_id": str(source.operation_id)},
            )
            metric = await connection.scalar(
                text(
                    """
                    SELECT payload ->> 'metric_key' FROM analytics_outbox_events
                    WHERE aggregate_type = 'v2_per_minute_debit' AND aggregate_id = :aggregate_id
                    """
                ),
                {"aggregate_id": str(source.operation_id)},
            )
            skip_reason = await connection.scalar(
                text(
                    """
                    SELECT reason FROM v2_analytics_backfill_skips
                    WHERE backfill_name = 'v2_confirmed_per_minute_debits_v1'
                      AND source_event_id = :event_id
                    """
                ),
                {"event_id": legacy.event_id},
            )
        assert first.skipped_count == 1
        assert first.completed is False
        assert second.accepted_count == 1
        assert first.duplicate_count == 0
        assert third.accepted_count == third.duplicate_count == third.skipped_count == 0
        assert third.completed is True
        assert outbox_count == 1
        assert metric == "wallet_debit_cents"
        assert skip_reason == "legacy_or_invalid_per_minute_payload"
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    DELETE FROM analytics_projection_events
                    WHERE event_id IN (
                        SELECT id FROM analytics_outbox_events WHERE aggregate_id = :aggregate_id
                    )
                    """
                ),
                {"aggregate_id": str(source.operation_id)},
            )
            await connection.execute(
                text("DELETE FROM analytics_outbox_events WHERE aggregate_id = :aggregate_id"),
                {"aggregate_id": str(source.operation_id)},
            )
            await connection.execute(
                text(
                    """
                    DELETE FROM v2_event_inbox
                    WHERE producer_id = 'server:reconciliation' AND operation_id = :operation_id
                    """
                ),
                {"operation_id": source.operation_id},
            )
            await connection.execute(
                text(
                    """
                    DELETE FROM v2_analytics_backfill_skips
                    WHERE backfill_name = 'v2_confirmed_per_minute_debits_v1'
                    """
                )
            )
            await connection.execute(
                text(
                    "DELETE FROM v2_analytics_backfill_runs "
                    "WHERE name = 'v2_confirmed_per_minute_debits_v1'"
                )
            )
            await connection.execute(
                text(
                    "DELETE FROM v2_confirmed_client_facts "
                    "WHERE event_id IN (:source_id, :legacy_id)"
                ),
                {"source_id": source.event_id, "legacy_id": legacy.event_id},
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_faststream_confirmed_analytics_worker_consumes_server_event() -> None:
    """Проверяет Kafka → analytics outbox → projection без write-path денег."""

    postgres_dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    kafka_bootstrap_servers = os.getenv("GAMECLUB_TEST_KAFKA_BOOTSTRAP_SERVERS")
    redis_url = os.getenv("GAMECLUB_REDIS_URL")
    if not postgres_dsn or not kafka_bootstrap_servers or not redis_url:
        pytest.skip("Set PostgreSQL, Kafka and Redis settings for confirmed analytics worker test")

    engine = create_async_engine(postgres_dsn, pool_pre_ping=True)
    producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap_servers, acks="all")
    event = confirmed_deposit_event()
    try:
        await producer.start()
        await producer.send_and_wait(
            "v2.confirmed-domain-events",
            event_to_protobuf(event).SerializeToString(),
            key=f"{event.client_id}:{event.session_id}".encode(),
        )

        processed = False
        for _ in range(50):
            async with engine.connect() as connection:
                inbox_count = await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM v2_event_inbox
                        WHERE consumer_name = 'confirmed_analytics' AND event_id = :event_id
                        """
                    ),
                    {"event_id": event.event_id},
                )
                outbox_count = await connection.scalar(
                    text("SELECT count(*) FROM analytics_outbox_events WHERE aggregate_id = :id"),
                    {"id": str(event.operation_id)},
                )
            if inbox_count == 1 and outbox_count == 2:
                processed = True
                break
            await asyncio.sleep(0.1)

        assert processed, "V2 confirmed analytics worker did not process the Kafka event in time"

        # Scheduler вызывает тот же actor периодически; здесь явно ставим его в
        # очередь, чтобы живой тест не зависел от текущей минуты расписания.
        project_analytics_events.send()

        projected = False
        for _ in range(50):
            async with engine.connect() as connection:
                projection_count = await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM analytics_projection_events
                        WHERE event_id IN (
                            SELECT id FROM analytics_outbox_events WHERE aggregate_id = :id
                        )
                        """
                    ),
                    {"id": str(event.operation_id)},
                )
            if projection_count == 2:
                projected = True
                break
            await asyncio.sleep(0.1)

        assert projected, "Analytics projection worker did not apply the confirmed event in time"
    finally:
        await producer.stop()
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    DELETE FROM analytics_projection_events
                    WHERE event_id IN (
                        SELECT id FROM analytics_outbox_events WHERE aggregate_id = :id
                    )
                    """
                ),
                {"id": str(event.operation_id)},
            )
            await connection.execute(
                text("DELETE FROM analytics_outbox_events WHERE aggregate_id = :id"),
                {"id": str(event.operation_id)},
            )
            await connection.execute(
                text("DELETE FROM v2_event_inbox WHERE event_id = :event_id"),
                {"event_id": event.event_id},
            )
        await engine.dispose()
