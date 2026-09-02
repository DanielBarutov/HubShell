from __future__ import annotations

import asyncio
import uuid

from gameclub_backend.modules.offline.domain import (
    OfflineOperation,
    OfflineOperationResult,
    OfflineOperationStatus,
)


class InMemoryOfflineReplayRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, tuple[OfflineOperation, OfflineOperationResult]] = {}
        self._by_key: dict[str, uuid.UUID] = {}
        self._by_sequence: dict[tuple[str, uuid.UUID, int], uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get_by_idempotency_key(self, key: str) -> OfflineOperationResult | None:
        operation_id = self._by_key.get(key)
        item = self._items.get(operation_id) if operation_id else None
        return item[1] if item else None

    async def get_operation_by_idempotency_key(self, key: str) -> OfflineOperation | None:
        operation_id = self._by_key.get(key)
        item = self._items.get(operation_id) if operation_id else None
        return item[0] if item else None

    async def get_by_sequence(
        self,
        device_id: str,
        session_id: uuid.UUID,
        sequence: int,
    ) -> tuple[OfflineOperation, OfflineOperationResult] | None:
        operation_id = self._by_sequence.get((device_id, session_id, sequence))
        return self._items.get(operation_id) if operation_id else None

    async def get_last_sequence(self, device_id: str, session_id: uuid.UUID) -> int:
        sequences = [
            operation.sequence
            for operation, _result in self._items.values()
            if operation.device_id == device_id and operation.session_id == session_id
        ]
        return max(sequences, default=0)

    async def save(
        self,
        operation: OfflineOperation,
        result: OfflineOperationResult,
    ) -> OfflineOperationResult:
        async with self._lock:
            existing_id = self._by_key.get(operation.idempotency_key)
            if existing_id is not None and existing_id != operation.id:
                return self._items[existing_id][1]
            current = self._items.get(operation.id)
            if current is not None and current[1].status is not OfflineOperationStatus.PENDING:
                return current[1]
            self._items[operation.id] = (operation, result)
            self._by_key[operation.idempotency_key] = operation.id
            self._by_sequence[(operation.device_id, operation.session_id, operation.sequence)] = (
                operation.id
            )
            return result
