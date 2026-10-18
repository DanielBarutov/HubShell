from __future__ import annotations

import typing
import uuid

from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2OutgoingServerEvent,
    V2SessionChain,
)


class V2InboxRepository(typing.Protocol):
    """Durable idempotency boundary for one producer operation."""

    async def get(
        self,
        consumer_name: str,
        producer_id: str,
        operation_id: uuid.UUID,
    ) -> V2Event | None:
        """Return the event previously accepted for the producer operation."""

    async def save_if_absent(self, consumer_name: str, event: V2Event) -> V2Event:
        """Persist an event or return the durable winner for its operation key."""


class V2ServerOutboxRepository(typing.Protocol):
    """Постоянная очередь подтверждённых сообщений сервера."""

    async def append_if_absent(self, event: V2OutgoingServerEvent) -> V2OutgoingServerEvent:
        """Сохранить исходящее событие или вернуть уже существующую запись."""

    async def list_pending(self, limit: int) -> tuple[V2OutgoingServerEvent, ...]:
        """Вернуть ограниченную порцию ещё не подтверждённых Kafka записей."""

    async def list_published_for_device(
        self,
        device_id: str,
        limit: int,
    ) -> tuple[V2OutgoingServerEvent, ...]:
        """Вернуть только применимые клиентом события активной V2-сессии."""

    async def acknowledge(
        self,
        event_id: uuid.UUID,
        device_id: str,
    ) -> V2OutgoingServerEvent | None:
        """Подтвердить событие только от устройства, которому оно адресовано."""

    async def save(self, event: V2OutgoingServerEvent) -> V2OutgoingServerEvent:
        """Сохранить число попыток или подтверждение публикации."""


class V2SessionChainRepository(typing.Protocol):
    """Постоянный checkpoint порядка фактов одной автономной сессии."""

    async def get(self, session_id: uuid.UUID) -> V2SessionChain | None:
        """Вернуть последнюю подтверждённую точку цепочки сессии."""

    async def save_if_current(
        self,
        chain: V2SessionChain,
        expected_last_sequence: int | None,
    ) -> bool:
        """Сохранить checkpoint, только если предыдущая точка не изменилась."""
