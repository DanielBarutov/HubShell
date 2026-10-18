import asyncio
import base64
import datetime
import uuid

import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.jobs.v2_event_transport import publish_server_outbox_until_stopped
from gameclub_backend.modules.eventing_v2.application.chain import V2SessionChainService
from gameclub_backend.modules.eventing_v2.application.outbox import V2ServerOutboxService
from gameclub_backend.modules.eventing_v2.application.reconciliation import (
    V2ClientFactResult,
    V2ClientFactStatus,
)
from gameclub_backend.modules.eventing_v2.application.service import V2InboxService
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2InboxStatus,
    V2OutgoingEventStatus,
    V2OutgoingServerEvent,
    V2SessionChain,
    V2SessionChainStatus,
    event_to_transport_payload,
)
from gameclub_backend.modules.eventing_v2.infrastructure.faststream import (
    FastStreamV2EventPublisher,
    V2ClientFactsConsumer,
    V2ServerOutboxPublisher,
)
from gameclub_backend.modules.eventing_v2.infrastructure.memory import (
    InMemoryV2InboxRepository,
    InMemoryV2ServerOutboxRepository,
    InMemoryV2SessionChainRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.protobuf import (
    event_from_protobuf,
    event_from_protobuf_bytes,
    event_to_protobuf,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    serialize_snapshot_payload,
    sign_offline_session_snapshot,
)

CLIENT_SESSION_FACTS = "client_session_facts"


def make_event(
    *,
    operation_id: uuid.UUID | None = None,
    sequence: int = 1,
    event_type: V2EventType = V2EventType.PER_MINUTE_DEBIT,
    payload: dict[str, object] | None = None,
    previous_hash: str | None = None,
) -> V2Event:
    return V2Event.create(
        operation_id=operation_id or uuid.uuid4(),
        event_type=event_type,
        producer_id="workstation:vip-01",
        client_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        session_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        device_id="vip-01-device",
        sequence=sequence,
        occurred_at=datetime.datetime(2026, 9, 27, 12, tzinfo=datetime.UTC),
        payload=payload or {"amount_cents": 100, "tariff_id": "per-minute-test"},
        previous_hash=previous_hash,
    )


def make_outgoing(
    event: V2Event | None = None,
    *,
    topic: str = "v2.server-events",
) -> V2OutgoingServerEvent:
    return V2OutgoingServerEvent(
        event=event or make_event(),
        topic=topic,
        partition_key="client-session:00000000-0000-0000-0000-000000000002",
        created_at=datetime.datetime(2026, 9, 27, 12, tzinfo=datetime.UTC),
    )


def test_v2_event_uses_canonical_payload_hash() -> None:
    """Одинаковый payload с другим порядком ключей имеет тот же V2 hash."""
    first = make_event(payload={"amount_cents": 100, "tariff_id": "per-minute-test"})
    second = make_event(payload={"tariff_id": "per-minute-test", "amount_cents": 100})

    assert first.payload_hash == second.payload_hash


def test_v2_event_rejects_tampered_payload_hash() -> None:
    """Изменённый payload нельзя выдать за исходный V2 event."""
    event = make_event()

    with pytest.raises(ValueError, match="payload hash"):
        V2Event(
            event_id=event.event_id,
            operation_id=event.operation_id,
            event_type=event.event_type,
            producer_id=event.producer_id,
            client_id=event.client_id,
            session_id=event.session_id,
            device_id=event.device_id,
            sequence=event.sequence,
            occurred_at=event.occurred_at,
            payload_json='{"amount_cents":101,"tariff_id":"per-minute-test"}',
            payload_hash=event.payload_hash,
            previous_hash=event.previous_hash,
            causation_id=event.causation_id,
            correlation_id=event.correlation_id,
            traceparent=event.traceparent,
        )


def test_v2_session_chain_accepts_contiguous_events_with_matching_hash() -> None:
    """Проверяет заявленное поведение backend."""
    first = make_event()
    second = make_event(sequence=2, previous_hash=first.payload_hash)

    chain = V2SessionChain.from_first_event(first)
    status, updated = chain.accept(second)

    assert status is V2SessionChainStatus.ACCEPTED
    assert updated is not None
    assert updated.last_sequence == 2
    assert updated.last_payload_hash == second.payload_hash


def test_v2_session_chain_rejects_gap_and_previous_hash_conflict() -> None:
    """Проверяет заявленное поведение backend."""
    first = make_event()
    chain = V2SessionChain.from_first_event(first)

    gap_status, gap = chain.accept(make_event(sequence=3, previous_hash=first.payload_hash))
    conflict_status, conflict = chain.accept(make_event(sequence=2, previous_hash="0" * 64))

    assert gap_status is V2SessionChainStatus.GAP
    assert gap is None
    assert conflict_status is V2SessionChainStatus.CONFLICT
    assert conflict is None


@pytest.mark.asyncio
async def test_v2_inbox_accepts_duplicate_without_second_side_effect() -> None:
    """Повтор Kafka delivery возвращает duplicate для того же operation id."""
    inbox = V2InboxService(InMemoryV2InboxRepository(), CLIENT_SESSION_FACTS)
    operation_id = uuid.uuid4()
    first = make_event(operation_id=operation_id)
    duplicate = make_event(operation_id=operation_id)

    accepted = await inbox.accept(first)
    repeated = await inbox.accept(duplicate)

    assert accepted.status is V2InboxStatus.ACCEPTED
    assert repeated.status is V2InboxStatus.DUPLICATE
    assert repeated.event_id == first.event_id


@pytest.mark.asyncio
async def test_v2_inbox_rejects_reused_operation_id_with_other_payload() -> None:
    """Один operation id с другим payload становится явным conflict."""
    inbox = V2InboxService(InMemoryV2InboxRepository(), CLIENT_SESSION_FACTS)
    operation_id = uuid.uuid4()

    await inbox.accept(make_event(operation_id=operation_id))
    conflict = await inbox.accept(
        make_event(
            operation_id=operation_id, payload={"amount_cents": 200, "tariff_id": "per-minute-test"}
        )
    )

    assert conflict.status is V2InboxStatus.CONFLICT


@pytest.mark.asyncio
async def test_v2_inbox_repository_elects_one_winner_between_consumers() -> None:
    """Параллельные consumers сохраняют один факт, второй получает duplicate."""
    repository = InMemoryV2InboxRepository()
    operation_id = uuid.uuid4()
    first = make_event(operation_id=operation_id)
    second = make_event(operation_id=operation_id)

    first_result, second_result = await asyncio.gather(
        V2InboxService(repository, CLIENT_SESSION_FACTS).accept(first),
        V2InboxService(repository, CLIENT_SESSION_FACTS).accept(second),
    )

    assert {first_result.status, second_result.status} == {
        V2InboxStatus.ACCEPTED,
        V2InboxStatus.DUPLICATE,
    }


@pytest.mark.asyncio
async def test_v2_event_is_processed_once_for_each_logical_consumer() -> None:
    """Один факт допустим один раз для сессии и один раз для аналитики."""
    repository = InMemoryV2InboxRepository()
    event = make_event()
    session_facts = V2InboxService(repository, CLIENT_SESSION_FACTS)
    analytics = V2InboxService(repository, "analytics_projection")

    first = await session_facts.accept(event)
    second = await analytics.accept(event)
    repeated = await session_facts.accept(event)

    assert first.status is V2InboxStatus.ACCEPTED
    assert second.status is V2InboxStatus.ACCEPTED
    assert repeated.status is V2InboxStatus.DUPLICATE


@pytest.mark.asyncio
async def test_v2_session_chain_service_persists_only_contiguous_facts() -> None:
    """Проверяет заявленное поведение backend."""
    service = V2SessionChainService(InMemoryV2SessionChainRepository())
    first = make_event()
    second = make_event(sequence=2, previous_hash=first.payload_hash)

    assert await service.accept(first) is V2SessionChainStatus.ACCEPTED
    assert await service.accept(second) is V2SessionChainStatus.ACCEPTED
    assert await service.accept(second) is V2SessionChainStatus.GAP


@pytest.mark.asyncio
async def test_v2_server_outbox_retries_before_kafka_confirmation() -> None:
    """Ошибка отправки остаётся в постоянной очереди до подтверждения Kafka."""
    outbox = V2ServerOutboxService(InMemoryV2ServerOutboxRepository())
    outgoing = make_outgoing()

    first = await outbox.enqueue(outgoing)
    duplicate = await outbox.enqueue(outgoing)
    failed = await outbox.record_publish_failure(first, "Kafka временно недоступна")
    pending = await outbox.pending()
    published = await outbox.mark_published(
        failed,
        datetime.datetime(2026, 9, 27, 12, 1, tzinfo=datetime.UTC),
    )

    assert duplicate == first
    assert failed.status is V2OutgoingEventStatus.PENDING
    assert failed.attempts == 1
    assert pending == (failed,)
    assert published.status is V2OutgoingEventStatus.PUBLISHED
    assert await outbox.pending() == ()


@pytest.mark.asyncio
async def test_v2_server_event_ack_is_device_scoped_and_idempotent() -> None:
    """Клиентский ack завершает доставку только для адресованного устройства."""
    repository = InMemoryV2ServerOutboxRepository()
    outbox = V2ServerOutboxService(repository)
    outgoing = await outbox.enqueue(
        make_outgoing(
            make_event(
                event_type=V2EventType.BALANCE_CREDIT_APPLIED,
                payload={"amount_delta_cents": 200, "currency": "RUB"},
            )
        )
    )
    published = await outbox.mark_published(
        outgoing,
        datetime.datetime(2026, 9, 27, 12, 1, tzinfo=datetime.UTC),
    )

    assert await outbox.published_for_device("another-device") == ()
    assert await outbox.acknowledge(published.event.event_id, "another-device") is None
    acknowledged = await outbox.acknowledge(published.event.event_id, published.event.device_id)
    repeated = await outbox.acknowledge(published.event.event_id, published.event.device_id)

    assert acknowledged is not None
    assert acknowledged.status is V2OutgoingEventStatus.ACKNOWLEDGED
    assert repeated == acknowledged
    assert await outbox.published_for_device(published.event.device_id) == ()


@pytest.mark.asyncio
async def test_v2_server_event_poll_returns_only_client_balance_credits() -> None:
    """Скрывает из client poll внутренние reconciliation и analytics events."""
    repository = InMemoryV2ServerOutboxRepository()
    outbox = V2ServerOutboxService(repository)
    outgoing_events = (
        make_outgoing(
            make_event(event_type=V2EventType.BALANCE_CREDIT_APPLIED),
        ),
        make_outgoing(
            make_event(event_type=V2EventType.RECONCILIATION_COMPLETED),
        ),
        make_outgoing(
            make_event(event_type=V2EventType.BALANCE_CREDIT_APPLIED),
            topic="v2.confirmed-domain-events",
        ),
    )
    for event in outgoing_events:
        pending = await outbox.enqueue(event)
        await outbox.mark_published(
            pending,
            datetime.datetime(2026, 9, 27, 12, 1, tzinfo=datetime.UTC),
        )

    published = await outbox.published_for_device("vip-01-device")

    assert len(published) == 1
    assert published[0].event.event_type is V2EventType.BALANCE_CREDIT_APPLIED
    assert published[0].topic == "v2.server-events"


@pytest.mark.asyncio
async def test_v2_outbox_delivery_loop_stops_without_losing_control() -> None:
    """Настоящий worker не ждёт следующего интервала после сигнала остановки."""

    stop_requested = asyncio.Event()

    class OnePassPublisher:
        calls = 0

        async def publish_pending(self) -> int:
            self.calls += 1
            stop_requested.set()
            return 0

    publisher = OnePassPublisher()
    await publish_server_outbox_until_stopped(  # type: ignore[arg-type]
        publisher,
        stop_requested,
        poll_interval_seconds=60,
    )

    assert publisher.calls == 1


@pytest.mark.asyncio
async def test_client_facts_consumer_confirms_offset_only_after_transaction_or_dlq() -> None:
    """Ошибочный Kafka факт переносится в DLQ, а временная ошибка handler не скрывается."""

    class RecordingRejectedEvents:
        items: list[tuple[bytes, str]] = []

        async def publish_rejected(self, payload: bytes, reason_code: str) -> None:
            self.items.append((payload, reason_code))

    class ResultHandler:
        def __init__(self, result: V2ClientFactResult) -> None:
            self.result = result

        async def accept(self, event: V2Event) -> V2ClientFactResult:
            assert event == source
            return self.result

    source = make_event()
    payload = event_to_protobuf(source).SerializeToString()
    rejected = RecordingRejectedEvents()
    accepted = V2ClientFactsConsumer(
        ResultHandler(
            V2ClientFactResult(
                V2ClientFactStatus.ACCEPTED,
                source.event_id,
                source.operation_id,
                "accepted",
            )
        ),
        rejected,
    )

    result = await accepted.accept_payload(payload)

    assert result is not None and result.status is V2ClientFactStatus.ACCEPTED
    assert rejected.items == []

    conflict = V2ClientFactsConsumer(
        ResultHandler(
            V2ClientFactResult(
                V2ClientFactStatus.CONFLICT,
                source.event_id,
                source.operation_id,
                "conflict",
            )
        ),
        rejected,
    )
    await conflict.accept_payload(payload)
    invalid = await conflict.accept_payload(b"not-protobuf")

    assert invalid is None
    assert rejected.items == [
        (payload, "reconciliation_conflict"),
        (b"not-protobuf", "invalid_envelope"),
    ]


def test_v2_transport_payload_keeps_immutable_event_envelope() -> None:
    """Проверяет заявленное поведение backend."""
    event = make_event()

    assert event_to_transport_payload(event) == {
        "event_id": str(event.event_id),
        "operation_id": str(event.operation_id),
        "event_type": event.event_type.value,
        "schema_version": 1,
        "producer_id": event.producer_id,
        "client_id": str(event.client_id),
        "session_id": str(event.session_id),
        "device_id": event.device_id,
        "sequence": event.sequence,
        "occurred_at": event.occurred_at.isoformat(),
        "causation_id": None,
        "correlation_id": str(event.correlation_id),
        "traceparent": event.traceparent,
        "payload_hash": event.payload_hash,
        "previous_hash": event.previous_hash,
        "payload": {"amount_cents": 100, "tariff_id": "per-minute-test"},
    }


def test_v2_transport_payload_round_trip_validates_the_same_event() -> None:
    """Проверяет заявленное поведение backend."""
    event = make_event()

    restored = V2Event.from_transport_payload(event_to_transport_payload(event))

    assert restored == event


def test_v2_transport_payload_rejects_missing_traceparent() -> None:
    """Проверяет заявленное поведение backend."""
    message = event_to_transport_payload(make_event())
    message.pop("traceparent")

    with pytest.raises(ValueError, match="traceparent"):
        V2Event.from_transport_payload(message)


def test_v2_transport_payload_rejects_tampered_payload_hash() -> None:
    """Проверяет заявленное поведение backend."""
    message = event_to_transport_payload(make_event())
    message["payload"] = {"amount_cents": 999, "tariff_id": "per-minute-test"}

    with pytest.raises(ValueError, match="payload hash"):
        V2Event.from_transport_payload(message)


def test_v2_protobuf_round_trip_keeps_the_same_event() -> None:
    """Проверяет заявленное поведение backend."""
    event = make_event()

    restored = event_from_protobuf_bytes(event_to_protobuf(event).SerializeToString())

    assert restored == event


def test_v2_protobuf_rejects_tampered_payload_hash() -> None:
    """Проверяет заявленное поведение backend."""
    message = event_to_protobuf(make_event())
    message.payload_json = '{"amount_cents":999,"tariff_id":"per-minute-test"}'

    with pytest.raises(ValueError, match="payload hash"):
        event_from_protobuf(message)


def test_v2_snapshot_payload_has_cross_language_deterministic_bytes() -> None:
    """Проверяет заявленное поведение backend."""
    payload = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload(
        snapshot_id="00000000-0000-0000-0000-000000000010",
        schema_version=1,
        snapshot_version=7,
        issued_at=Timestamp(seconds=1_790_510_400),
        client_id="00000000-0000-0000-0000-000000000001",
        session_id="00000000-0000-0000-0000-000000000002",
        device_id="device-01",
        balance_cents=1_000,
        debt_limit_cents=50,
        login_grant_remaining_minutes=5,
        policy_version="policy-2026-09",
    )
    payload.tariffs.add(
        tariff_id="minute",
        name="Поминутный",
        per_minute_price_cents=60,
    )

    encoded = base64.b64encode(payload.SerializeToString(deterministic=True)).decode()

    assert encoded == (
        "CiQwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMTAQARgHIgYIwIrk1QYq"
        "JDAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMTIkMDAwMDAwMDAtMDAw"
        "MC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAyOglkZXZpY2UtMDFI0A9QZFgFaiAKBm1pbnV0"
        "ZRIU0J/QvtC80LjQvdGD0YLQvdGL0LkweHIOcG9saWN5LTIwMjYtMDk="
    )


def test_v2_snapshot_signer_receives_only_deterministic_payload_bytes() -> None:
    """Проверяет заявленное поведение backend."""
    payload = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload(
        snapshot_id="00000000-0000-0000-0000-000000000010",
        schema_version=1,
        snapshot_version=1,
    )
    signer = _SnapshotSigner()

    signed = sign_offline_session_snapshot(payload, "club-key-1", signer)

    assert signer.payload == serialize_snapshot_payload(payload)
    assert signed.signing_key_id == "club-key-1"
    assert signed.signature == b"signature"


class _SnapshotSigner:
    def __init__(self) -> None:
        self.payload: bytes | None = None

    def sign(self, payload: bytes) -> bytes:
        self.payload = payload
        return b"signature"


class _RecordingPublisher:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.events: list[V2OutgoingServerEvent] = []

    async def publish(self, event: V2OutgoingServerEvent) -> None:
        self.events.append(event)
        if self.failure is not None:
            raise self.failure


@pytest.mark.asyncio
async def test_faststream_outbox_publisher_marks_only_confirmed_event_published() -> None:
    """Проверяет заявленное поведение backend."""
    repository = InMemoryV2ServerOutboxRepository()
    outbox = V2ServerOutboxService(repository)
    event = await outbox.enqueue(make_outgoing())
    publisher = _RecordingPublisher()

    sent = await V2ServerOutboxPublisher(outbox, publisher).publish_pending()

    assert sent == 1
    assert publisher.events == [event]
    assert await outbox.pending() == ()


@pytest.mark.asyncio
async def test_faststream_outbox_publisher_keeps_event_after_transport_error() -> None:
    """Проверяет заявленное поведение backend."""
    repository = InMemoryV2ServerOutboxRepository()
    outbox = V2ServerOutboxService(repository)
    event = await outbox.enqueue(make_outgoing())
    publisher = _RecordingPublisher(RuntimeError("Kafka is unavailable"))

    sent = await V2ServerOutboxPublisher(outbox, publisher).publish_pending()

    assert sent == 0
    pending = await outbox.pending()
    assert pending[0].event.event_id == event.event.event_id
    assert pending[0].attempts == 1
    assert pending[0].last_error == "Kafka is unavailable"


class _RecordingBroker:
    def __init__(self) -> None:
        self.message: bytes | None = None
        self.topic: str | None = None
        self.key: bytes | None = None
        self.correlation_id: str | None = None
        self.headers: dict[str, str] | None = None

    async def publish(
        self,
        message: bytes,
        topic: str,
        *,
        key: bytes,
        correlation_id: str,
        headers: dict[str, str],
    ) -> None:
        self.message = message
        self.topic = topic
        self.key = key
        self.correlation_id = correlation_id
        self.headers = headers


@pytest.mark.asyncio
async def test_faststream_adapter_publishes_protobuf_envelope_and_trace_context() -> None:
    """Проверяет заявленное поведение backend."""
    broker = _RecordingBroker()
    outgoing = make_outgoing()

    await FastStreamV2EventPublisher(broker).publish(outgoing)  # type: ignore[arg-type]

    assert broker.message is not None
    assert event_from_protobuf_bytes(broker.message) == outgoing.event
    assert broker.topic == outgoing.topic
    assert broker.key == outgoing.partition_key.encode("utf-8")
    assert broker.correlation_id == str(outgoing.event.operation_id)
    assert broker.headers == {
        "event_id": str(outgoing.event.event_id),
        "event_type": outgoing.event.event_type.value,
        "schema_version": "1",
        "traceparent": outgoing.event.traceparent,
    }
