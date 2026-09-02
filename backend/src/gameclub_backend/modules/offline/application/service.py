from __future__ import annotations

import asyncio
import datetime

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.offline.application.ports import OfflineReplayRepository
from gameclub_backend.modules.offline.domain import (
    OfflineBatch,
    OfflineBatchResult,
    OfflineOperation,
    OfflineOperationKind,
    OfflineOperationResult,
    OfflineOperationStatus,
)
from gameclub_backend.modules.sessions.application.ports import SessionRepository, WorkstationLookup
from gameclub_backend.modules.sessions.application.service import SessionService


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class OfflineReplayService:
    def __init__(
        self,
        repository: OfflineReplayRepository,
        sessions: SessionService,
        session_repository: SessionRepository,
        workstations: WorkstationLookup,
        billing: BillingService,
        clock: UtcClock | None = None,
    ) -> None:
        self._repository = repository
        self._sessions = sessions
        self._session_repository = session_repository
        self._workstations = workstations
        self._billing = billing
        self._clock = clock or UtcClock()
        self._lock = asyncio.Lock()

    async def replay(
        self,
        batch: OfflineBatch,
        actor_device_id: str | None = None,
    ) -> OfflineBatchResult:
        if actor_device_id is not None and actor_device_id.strip() != batch.device_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Offline device identity does not match",
            )
        session = await self._session_repository.get(batch.session_id)
        if session is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Offline session not found")
        workstation = await self._workstations.get(session.workstation_id)
        if workstation is None or workstation.device_id != batch.device_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Offline session does not belong to device",
            )
        if session.status.value not in {"active", "completed"}:
            raise ApplicationError(ErrorCode.CONFLICT, "Offline session is not replayable")

        results: list[OfflineOperationResult] = []
        async with self._lock:
            for operation in batch.operations:
                results.append(await self._replay_operation(operation))
        snapshot = await self._sessions.snapshot(batch.session_id)
        return OfflineBatchResult(1, batch.session_id, tuple(results), snapshot)

    async def _replay_operation(self, operation: OfflineOperation) -> OfflineOperationResult:
        existing = await self._repository.get_by_idempotency_key(operation.idempotency_key)
        if existing is not None:
            recorded = await self._repository.get_operation_by_idempotency_key(
                operation.idempotency_key
            )
            if recorded is None or recorded.checksum != operation.checksum:
                conflict = OfflineOperationResult(
                    operation.id,
                    operation.sequence,
                    OfflineOperationStatus.CONFLICT,
                    "Idempotency key belongs to another offline operation",
                )
                return conflict
            return OfflineOperationResult(
                operation.id,
                operation.sequence,
                OfflineOperationStatus.DUPLICATE,
                "Операция уже подтверждена сервером",
                existing.applied_at,
            )
        previous = await self._repository.get_by_sequence(
            operation.device_id,
            operation.session_id,
            operation.sequence,
        )
        if previous is not None:
            recorded, _ = previous
            result = OfflineOperationResult(
                operation.id,
                operation.sequence,
                OfflineOperationStatus.CONFLICT,
                "Последовательность уже занята другой операцией",
            )
            await self._repository.save(operation, result)
            return result
        last_sequence = await self._repository.get_last_sequence(
            operation.device_id,
            operation.session_id,
        )
        if operation.sequence > last_sequence + 1:
            result = OfflineOperationResult(
                operation.id,
                operation.sequence,
                OfflineOperationStatus.CONFLICT,
                f"Пропущена offline sequence: ожидается {last_sequence + 1}",
            )
            await self._repository.save(operation, result)
            return result
        pending = OfflineOperationResult(
            operation.id,
            operation.sequence,
            OfflineOperationStatus.PENDING,
            "Операция принята на обработку",
        )
        await self._repository.save(operation, pending)
        try:
            message = await self._apply(operation)
        except ApplicationError as error:
            result = OfflineOperationResult(
                operation.id,
                operation.sequence,
                OfflineOperationStatus.REJECTED,
                error.message,
            )
        except (TypeError, ValueError) as error:
            result = OfflineOperationResult(
                operation.id,
                operation.sequence,
                OfflineOperationStatus.REJECTED,
                str(error),
            )
        else:
            result = OfflineOperationResult(
                operation.id,
                operation.sequence,
                OfflineOperationStatus.APPLIED,
                message,
                self._clock.now(),
            )
        return await self._repository.save(operation, result)

    async def _apply(self, operation: OfflineOperation) -> str:
        if operation.kind is OfflineOperationKind.METER_DELTA:
            minutes = operation.payload.get("minutes")
            if (
                not isinstance(minutes, int)
                or isinstance(minutes, bool)
                or minutes < 0
                or minutes > 24 * 60
            ):
                raise ApplicationError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Offline meter minutes are invalid",
                )
            await self._billing.meter_session(
                operation.session_id,
                charged_by=f"offline:{operation.device_id}",
            )
            return "Meter delta reconciled with server time"
        if operation.kind is OfflineOperationKind.STOP:
            await self._sessions.stop(operation.session_id, device_id=operation.device_id)
            return "Session stopped by offline journal"
        if operation.kind is OfflineOperationKind.LOCK:
            return "Client lock recorded"
        raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Offline operation is not allowed")
