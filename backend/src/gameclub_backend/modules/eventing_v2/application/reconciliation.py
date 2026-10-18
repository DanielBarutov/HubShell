"""Принятие клиентских V2-фактов без server minute confirmation."""

from __future__ import annotations

import dataclasses
import enum
import typing
import uuid

from gameclub_backend.modules.eventing_v2.domain import V2Event


class V2ClientFactStatus(enum.StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    GAP = "gap"
    CONFLICT = "conflict"


@dataclasses.dataclass(frozen=True)
class V2ClientFactResult:
    status: V2ClientFactStatus
    event_id: uuid.UUID
    operation_id: uuid.UUID
    message: str
    result_event_id: uuid.UUID | None = None


class V2ClientFactReconciliationRepository(typing.Protocol):
    async def accept(self, event: V2Event) -> V2ClientFactResult:
        """Atomically deduplicate, check chain and queue a server result."""


class V2ClientFactReconciliationService:
    """Application boundary; it never recalculates already consumed minutes."""

    def __init__(self, repository: V2ClientFactReconciliationRepository) -> None:
        self._repository = repository

    async def accept(self, event: V2Event) -> V2ClientFactResult:
        return await self._repository.accept(event)
