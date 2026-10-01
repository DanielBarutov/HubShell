from __future__ import annotations

import asyncio

from gameclub_backend.modules.eventing_v2.application.ports import V2InboxRepository
from gameclub_backend.modules.eventing_v2.domain import V2Event, V2InboxResult, V2InboxStatus


class V2InboxService:
    """Classify duplicated delivery before a use case applies a V2 side effect."""

    def __init__(self, repository: V2InboxRepository, consumer_name: str) -> None:
        if not consumer_name.strip():
            raise ValueError("V2 inbox consumer name is required")
        self._repository = repository
        self._consumer_name = consumer_name.strip()
        self._lock = asyncio.Lock()

    async def accept(self, event: V2Event) -> V2InboxResult:
        """Persist one new event or return a stable duplicate/conflict result."""
        async with self._lock:
            existing = await self._repository.get(
                self._consumer_name,
                event.producer_id,
                event.operation_id,
            )
            if existing is None:
                saved = await self._repository.save_if_absent(self._consumer_name, event)
                if saved.event_id == event.event_id:
                    return V2InboxResult(
                        V2InboxStatus.ACCEPTED,
                        event.event_id,
                        event.operation_id,
                        "V2 событие принято inbox",
                    )
                existing = saved
            if self._matches(existing, event):
                return V2InboxResult(
                    V2InboxStatus.DUPLICATE,
                    existing.event_id,
                    event.operation_id,
                    "V2 операция уже была принята",
                )
            return V2InboxResult(
                V2InboxStatus.CONFLICT,
                existing.event_id,
                event.operation_id,
                "operation_id уже принадлежит другому V2 событию",
            )

    @staticmethod
    def _matches(existing: V2Event, candidate: V2Event) -> bool:
        return (
            existing.payload_hash == candidate.payload_hash
            and existing.event_type is candidate.event_type
            and existing.client_id == candidate.client_id
            and existing.session_id == candidate.session_id
            and existing.device_id == candidate.device_id
            and existing.sequence == candidate.sequence
            and existing.previous_hash == candidate.previous_hash
        )
