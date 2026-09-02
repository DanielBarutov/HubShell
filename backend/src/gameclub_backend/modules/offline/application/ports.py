from __future__ import annotations

import typing
import uuid

from gameclub_backend.modules.offline.domain import (
    OfflineOperation,
    OfflineOperationResult,
)


class OfflineReplayRepository(typing.Protocol):
    async def get_operation_by_idempotency_key(self, key: str) -> OfflineOperation | None:
        """Return the operation stored for one replay key."""

    async def get_by_idempotency_key(self, key: str) -> OfflineOperationResult | None:
        """Return the durable result for one replay key."""

    async def get_by_sequence(
        self,
        device_id: str,
        session_id: uuid.UUID,
        sequence: int,
    ) -> tuple[OfflineOperation, OfflineOperationResult] | None:
        """Return an operation already recorded at a sequence."""

    async def get_last_sequence(self, device_id: str, session_id: uuid.UUID) -> int:
        """Return the highest durable sequence for one device/session."""

    async def save(
        self,
        operation: OfflineOperation,
        result: OfflineOperationResult,
    ) -> OfflineOperationResult:
        """Persist an operation and its replay result idempotently."""
