from __future__ import annotations

import datetime
import uuid

from gameclub_backend.modules.eventing_v2.application.ports import V2ServerOutboxRepository
from gameclub_backend.modules.eventing_v2.domain import V2OutgoingServerEvent


class V2ServerOutboxService:
    """Явная граница между подтверждённым фактом и его отправкой в Kafka."""

    def __init__(self, repository: V2ServerOutboxRepository) -> None:
        self._repository = repository

    async def enqueue(self, event: V2OutgoingServerEvent) -> V2OutgoingServerEvent:
        """Не создавать второй исходящий event при повторном бизнес-сценарии."""
        return await self._repository.append_if_absent(event)

    async def pending(self, limit: int = 100) -> tuple[V2OutgoingServerEvent, ...]:
        """Взять следующую ограниченную порцию для фонового отправителя."""
        if limit < 1 or limit > 1_000:
            raise ValueError("V2 outbox limit must be between 1 and 1000")
        return await self._repository.list_pending(limit)

    async def published_for_device(
        self,
        device_id: str,
        limit: int = 100,
    ) -> tuple[V2OutgoingServerEvent, ...]:
        """Получить client-applicable события активной V2-сессии до ack."""
        if not device_id.strip():
            raise ValueError("V2 server event device id is required")
        if limit < 1 or limit > 1_000:
            raise ValueError("V2 outbox limit must be between 1 and 1000")
        return await self._repository.list_published_for_device(device_id, limit)

    async def acknowledge(
        self,
        event_id: uuid.UUID,
        device_id: str,
    ) -> V2OutgoingServerEvent | None:
        """Подтвердить только опубликованное событие нужного устройства."""
        if not device_id.strip():
            raise ValueError("V2 server event device id is required")
        return await self._repository.acknowledge(event_id, device_id)

    async def mark_published(
        self,
        event: V2OutgoingServerEvent,
        published_at: datetime.datetime,
    ) -> V2OutgoingServerEvent:
        """Сохранить подтверждение Kafka после успешной публикации."""
        return await self._repository.save(event.record_published(published_at))

    async def record_publish_failure(
        self,
        event: V2OutgoingServerEvent,
        error: str,
    ) -> V2OutgoingServerEvent:
        """Записать ошибку и оставить event для повторной отправки."""
        return await self._repository.save(event.record_publish_failure(error))
