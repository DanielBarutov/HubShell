from __future__ import annotations

import asyncio
import uuid

from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2OutgoingEventStatus,
    V2OutgoingServerEvent,
    V2SessionChain,
)


class InMemoryV2InboxRepository:
    """Test adapter; production acceptance needs a PostgreSQL unique constraint."""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str, uuid.UUID], V2Event] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        consumer_name: str,
        producer_id: str,
        operation_id: uuid.UUID,
    ) -> V2Event | None:
        return self._events.get((consumer_name, producer_id, operation_id))

    async def save_if_absent(self, consumer_name: str, event: V2Event) -> V2Event:
        async with self._lock:
            key = (consumer_name, event.producer_id, event.operation_id)
            existing = self._events.get(key)
            if existing is not None:
                return existing
            self._events[key] = event
            return event


class InMemoryV2ServerOutboxRepository:
    """Тестовая постоянная очередь исходящих серверных сообщений."""

    def __init__(self) -> None:
        self._events: dict[uuid.UUID, V2OutgoingServerEvent] = {}
        self._lock = asyncio.Lock()

    async def append_if_absent(self, event: V2OutgoingServerEvent) -> V2OutgoingServerEvent:
        async with self._lock:
            return self._events.setdefault(event.event.event_id, event)

    async def list_pending(self, limit: int) -> tuple[V2OutgoingServerEvent, ...]:
        pending = [
            event
            for event in self._events.values()
            if event.status is V2OutgoingEventStatus.PENDING
        ]
        pending.sort(key=lambda event: (event.created_at, event.event.event_id))
        return tuple(pending[:limit])

    async def list_published_for_device(
        self,
        device_id: str,
        limit: int,
    ) -> tuple[V2OutgoingServerEvent, ...]:
        published = [
            event
            for event in self._events.values()
            if event.event.device_id == device_id
            and event.status is V2OutgoingEventStatus.PUBLISHED
        ]
        published.sort(key=lambda event: (event.created_at, event.event.event_id))
        return tuple(published[:limit])

    async def acknowledge(
        self,
        event_id: uuid.UUID,
        device_id: str,
    ) -> V2OutgoingServerEvent | None:
        async with self._lock:
            existing = self._events.get(event_id)
            if existing is None or existing.event.device_id != device_id:
                return None
            if existing.status is V2OutgoingEventStatus.ACKNOWLEDGED:
                return existing
            if existing.status is not V2OutgoingEventStatus.PUBLISHED:
                return existing
            acknowledged = existing.record_acknowledged()
            self._events[event_id] = acknowledged
            return acknowledged

    async def save(self, event: V2OutgoingServerEvent) -> V2OutgoingServerEvent:
        async with self._lock:
            existing = self._events.get(event.event.event_id)
            if existing is None:
                raise KeyError("V2 outgoing event is not in outbox")
            if existing.status is not V2OutgoingEventStatus.PENDING:
                return existing
            self._events[event.event.event_id] = event
            return event


class InMemoryV2SessionChainRepository:
    """Тестовый compare-and-save checkpoint без Kafka или PostgreSQL."""

    def __init__(self) -> None:
        self._chains: dict[uuid.UUID, V2SessionChain] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: uuid.UUID) -> V2SessionChain | None:
        async with self._lock:
            return self._chains.get(session_id)

    async def save_if_current(
        self,
        chain: V2SessionChain,
        expected_last_sequence: int | None,
    ) -> bool:
        async with self._lock:
            current = self._chains.get(chain.session_id)
            if expected_last_sequence is None:
                if current is not None:
                    return False
            elif current is None or current.last_sequence != expected_last_sequence:
                return False
            self._chains[chain.session_id] = chain
            return True
