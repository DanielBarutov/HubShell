from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, Text, select, text, update
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2OutgoingEventStatus,
    V2OutgoingServerEvent,
    V2SessionChain,
)


class V2EventingBase(DeclarativeBase):
    pass


class V2EventInboxModel(V2EventingBase):
    """PostgreSQL inbox row; the unique operation key is the idempotency guard."""

    __tablename__ = "v2_event_inbox"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(64))
    producer_id: Mapped[str] = mapped_column(String(128))
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    device_id: Mapped[str] = mapped_column(String(128), index=True)
    sequence: Mapped[int] = mapped_column(Integer())
    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    causation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    traceparent: Mapped[str] = mapped_column(String(55))
    payload_json: Mapped[str] = mapped_column(Text())
    payload_hash: Mapped[str] = mapped_column(String(64))
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer())
    accepted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> V2Event:
        return V2Event(
            event_id=self.event_id,
            operation_id=self.operation_id,
            event_type=V2EventType(self.event_type),
            producer_id=self.producer_id,
            client_id=self.client_id,
            session_id=self.session_id,
            device_id=self.device_id,
            sequence=self.sequence,
            occurred_at=self.occurred_at,
            causation_id=self.causation_id,
            correlation_id=self.correlation_id,
            traceparent=self.traceparent,
            payload_json=self.payload_json,
            payload_hash=self.payload_hash,
            previous_hash=self.previous_hash,
            schema_version=self.schema_version,
        )

    @classmethod
    def values_from_domain(cls, consumer_name: str, event: V2Event) -> dict[str, object]:
        return {
            "event_id": event.event_id,
            "consumer_name": consumer_name,
            "operation_id": event.operation_id,
            "event_type": event.event_type.value,
            "producer_id": event.producer_id,
            "client_id": event.client_id,
            "session_id": event.session_id,
            "device_id": event.device_id,
            "sequence": event.sequence,
            "occurred_at": event.occurred_at,
            "causation_id": event.causation_id,
            "correlation_id": event.correlation_id,
            "traceparent": event.traceparent,
            "payload_json": event.payload_json,
            "payload_hash": event.payload_hash,
            "previous_hash": event.previous_hash,
            "schema_version": event.schema_version,
            "accepted_at": datetime.datetime.now(datetime.UTC),
        }


class V2ServerOutboxModel(V2EventingBase):
    """Подтверждённое серверное сообщение, которое ещё нужно отправить в Kafka."""

    __tablename__ = "v2_server_outbox"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(64))
    producer_id: Mapped[str] = mapped_column(String(128))
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    device_id: Mapped[str] = mapped_column(String(128), index=True)
    sequence: Mapped[int] = mapped_column(Integer())
    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    causation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    traceparent: Mapped[str] = mapped_column(String(55))
    payload_json: Mapped[str] = mapped_column(Text())
    payload_hash: Mapped[str] = mapped_column(String(64))
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer())
    topic: Mapped[str] = mapped_column(String(255))
    partition_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), index=True)
    attempts: Mapped[int] = mapped_column(Integer())
    last_error: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_domain(self) -> V2OutgoingServerEvent:
        event = V2Event(
            event_id=self.event_id,
            operation_id=self.operation_id,
            event_type=V2EventType(self.event_type),
            producer_id=self.producer_id,
            client_id=self.client_id,
            session_id=self.session_id,
            device_id=self.device_id,
            sequence=self.sequence,
            occurred_at=self.occurred_at,
            causation_id=self.causation_id,
            correlation_id=self.correlation_id,
            traceparent=self.traceparent,
            payload_json=self.payload_json,
            payload_hash=self.payload_hash,
            previous_hash=self.previous_hash,
            schema_version=self.schema_version,
        )
        return V2OutgoingServerEvent(
            event=event,
            topic=self.topic,
            partition_key=self.partition_key,
            created_at=self.created_at,
            status=V2OutgoingEventStatus(self.status),
            attempts=self.attempts,
            last_error=self.last_error,
            published_at=self.published_at,
        )

    @classmethod
    def values_from_domain(cls, outgoing: V2OutgoingServerEvent) -> dict[str, object]:
        event = outgoing.event
        return {
            "event_id": event.event_id,
            "operation_id": event.operation_id,
            "event_type": event.event_type.value,
            "producer_id": event.producer_id,
            "client_id": event.client_id,
            "session_id": event.session_id,
            "device_id": event.device_id,
            "sequence": event.sequence,
            "occurred_at": event.occurred_at,
            "causation_id": event.causation_id,
            "correlation_id": event.correlation_id,
            "traceparent": event.traceparent,
            "payload_json": event.payload_json,
            "payload_hash": event.payload_hash,
            "previous_hash": event.previous_hash,
            "schema_version": event.schema_version,
            "topic": outgoing.topic,
            "partition_key": outgoing.partition_key,
            "status": outgoing.status.value,
            "attempts": outgoing.attempts,
            "last_error": outgoing.last_error,
            "created_at": outgoing.created_at,
            "published_at": outgoing.published_at,
        }


class V2SessionChainModel(V2EventingBase):
    """Последняя серверная точка sequence/hash-chain V2-сессии."""

    __tablename__ = "v2_session_chains"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    device_id: Mapped[str] = mapped_column(String(128), index=True)
    producer_id: Mapped[str] = mapped_column(String(128))
    last_sequence: Mapped[int] = mapped_column(Integer())
    last_payload_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> V2SessionChain:
        return V2SessionChain(
            client_id=self.client_id,
            session_id=self.session_id,
            device_id=self.device_id,
            producer_id=self.producer_id,
            last_sequence=self.last_sequence,
            last_payload_hash=self.last_payload_hash,
        )

    @classmethod
    def values_from_domain(cls, chain: V2SessionChain) -> dict[str, object]:
        return {
            "client_id": chain.client_id,
            "session_id": chain.session_id,
            "device_id": chain.device_id,
            "producer_id": chain.producer_id,
            "last_sequence": chain.last_sequence,
            "last_payload_hash": chain.last_payload_hash,
            "updated_at": datetime.datetime.now(datetime.UTC),
        }


class PostgresV2InboxRepository:
    """Durable V2 inbox; later use cases share its transaction with side effects."""

    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(
        self,
        consumer_name: str,
        producer_id: str,
        operation_id: uuid.UUID,
    ) -> V2Event | None:
        async with open_session(self._engine_provider) as session:
            item = await session.scalar(
                select(V2EventInboxModel).where(
                    V2EventInboxModel.consumer_name == consumer_name,
                    V2EventInboxModel.producer_id == producer_id,
                    V2EventInboxModel.operation_id == operation_id,
                )
            )
            return item.to_domain() if item else None

    async def save_if_absent(self, consumer_name: str, event: V2Event) -> V2Event:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                statement = (
                    insert(V2EventInboxModel)
                    .values(**V2EventInboxModel.values_from_domain(consumer_name, event))
                    .on_conflict_do_nothing(
                        constraint="uq_v2_event_inbox_consumer_producer_operation"
                    )
                    .returning(V2EventInboxModel.event_id)
                )
                event_id = await session.scalar(statement)
                if event_id == event.event_id:
                    return event
                stored = await session.scalar(
                    select(V2EventInboxModel)
                    .where(
                        V2EventInboxModel.consumer_name == consumer_name,
                        V2EventInboxModel.producer_id == event.producer_id,
                        V2EventInboxModel.operation_id == event.operation_id,
                    )
                    .with_for_update()
                )
                if stored is None:
                    raise RuntimeError("V2 inbox conflict did not return a durable event")
                return stored.to_domain()


class PostgresV2ServerOutboxRepository:
    """Постоянная очередь server-to-client сообщений для FastStream publisher."""

    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def append_if_absent(
        self,
        outgoing: V2OutgoingServerEvent,
    ) -> V2OutgoingServerEvent:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                statement = (
                    insert(V2ServerOutboxModel)
                    .values(**V2ServerOutboxModel.values_from_domain(outgoing))
                    .on_conflict_do_nothing()
                    .returning(V2ServerOutboxModel.event_id)
                )
                event_id = await session.scalar(statement)
                if event_id == outgoing.event.event_id:
                    return outgoing
                stored = await session.scalar(
                    select(V2ServerOutboxModel)
                    .where(V2ServerOutboxModel.event_id == outgoing.event.event_id)
                    .with_for_update()
                )
                if stored is None:
                    raise RuntimeError("V2 outbox conflict did not return a durable event")
                return stored.to_domain()

    async def list_pending(self, limit: int) -> tuple[V2OutgoingServerEvent, ...]:
        async with open_session(self._engine_provider) as session:
            items = await session.scalars(
                select(V2ServerOutboxModel)
                .where(V2ServerOutboxModel.status == V2OutgoingEventStatus.PENDING.value)
                .order_by(V2ServerOutboxModel.created_at, V2ServerOutboxModel.event_id)
                .limit(limit)
            )
            return tuple(item.to_domain() for item in items)

    async def list_published_for_device(
        self,
        device_id: str,
        limit: int,
    ) -> tuple[V2OutgoingServerEvent, ...]:
        async with open_session(self._engine_provider) as session:
            active_session_id = await session.scalar(
                text("""
                    SELECT session_id
                    FROM v2_session_leases
                    WHERE device_id = :device_id AND status = 'active'
                    ORDER BY issued_at DESC
                    LIMIT 1
                """),
                {"device_id": device_id},
            )
            if active_session_id is None:
                return ()
            items = await session.scalars(
                select(V2ServerOutboxModel)
                .where(
                    V2ServerOutboxModel.device_id == device_id,
                    V2ServerOutboxModel.session_id == active_session_id,
                    V2ServerOutboxModel.topic == "v2.server-events",
                    V2ServerOutboxModel.event_type == V2EventType.BALANCE_CREDIT_APPLIED.value,
                    V2ServerOutboxModel.status == V2OutgoingEventStatus.PUBLISHED.value,
                )
                .order_by(V2ServerOutboxModel.created_at, V2ServerOutboxModel.event_id)
                .limit(limit)
            )
            return tuple(item.to_domain() for item in items)

    async def acknowledge(
        self,
        event_id: uuid.UUID,
        device_id: str,
    ) -> V2OutgoingServerEvent | None:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                stored = await session.scalar(
                    select(V2ServerOutboxModel)
                    .where(
                        V2ServerOutboxModel.event_id == event_id,
                        V2ServerOutboxModel.device_id == device_id,
                    )
                    .with_for_update()
                )
                if stored is None:
                    return None
                if stored.status == V2OutgoingEventStatus.ACKNOWLEDGED.value:
                    return stored.to_domain()
                if stored.status != V2OutgoingEventStatus.PUBLISHED.value:
                    return stored.to_domain()
                stored.status = V2OutgoingEventStatus.ACKNOWLEDGED.value
                return stored.to_domain()

    async def save(self, outgoing: V2OutgoingServerEvent) -> V2OutgoingServerEvent:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                stored = await session.scalar(
                    select(V2ServerOutboxModel)
                    .where(V2ServerOutboxModel.event_id == outgoing.event.event_id)
                    .with_for_update()
                )
                if stored is None:
                    raise KeyError("V2 outgoing event is not in outbox")
                if stored.status != V2OutgoingEventStatus.PENDING.value:
                    return stored.to_domain()
                stored.status = outgoing.status.value
                stored.attempts = outgoing.attempts
                stored.last_error = outgoing.last_error
                stored.published_at = outgoing.published_at
                return stored.to_domain()


class PostgresV2SessionChainRepository:
    """PostgreSQL compare-and-save для одной упорядоченной V2-сессии."""

    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, session_id: uuid.UUID) -> V2SessionChain | None:
        async with open_session(self._engine_provider) as session:
            item = await session.scalar(
                select(V2SessionChainModel).where(V2SessionChainModel.session_id == session_id)
            )
            return item.to_domain() if item else None

    async def save_if_current(
        self,
        chain: V2SessionChain,
        expected_last_sequence: int | None,
    ) -> bool:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                values = V2SessionChainModel.values_from_domain(chain)
                if expected_last_sequence is None:
                    statement = (
                        insert(V2SessionChainModel)
                        .values(**values)
                        .on_conflict_do_nothing()
                        .returning(V2SessionChainModel.session_id)
                    )
                    return await session.scalar(statement) == chain.session_id
                statement = (
                    update(V2SessionChainModel)
                    .where(
                        V2SessionChainModel.session_id == chain.session_id,
                        V2SessionChainModel.last_sequence == expected_last_sequence,
                    )
                    .values(**values)
                )
                result = await session.execute(statement)
                return result.rowcount == 1
