from __future__ import annotations

import datetime
import re
import typing
import uuid
from dataclasses import dataclass
from enum import StrEnum

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.domain.equipment import EquipmentType
from gameclub_backend.modules.reservations.application.ports import ReservationEntryLookup
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationSessionMode, WorkstationStatus


class V2TransferStatus(StrEnum):
    PREPARING = "preparing"
    COMMITTED = "committed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class V2TransferCheckpoint:
    sequence: int
    payload_hash: str | None

    def __post_init__(self) -> None:
        if self.sequence == 0 and self.payload_hash is None:
            return
        if (
            self.sequence <= 0
            or self.sequence > 2_147_483_647
            or self.payload_hash is None
            or not re.fullmatch(r"[0-9a-f]{64}", self.payload_hash)
        ):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid transfer checkpoint")


@dataclass(frozen=True)
class V2TransferReservation:
    operation_id: uuid.UUID
    session_id: uuid.UUID
    source_workstation_id: uuid.UUID
    target_workstation_id: uuid.UUID
    status: V2TransferStatus
    expires_at: datetime.datetime
    target_ready: bool = False
    source_checkpoint: V2TransferCheckpoint | None = None
    quote_token: str | None = None


class TransferRightsWriter(typing.Protocol):
    async def __call__(
        self, operation: V2TransferReservation, source: Session
    ) -> datetime.datetime | None:
        """Persist access and return the next billing boundary if the commit must precede it."""


class ReservedTransferTargets(typing.Protocol):
    async def list_reserved_targets(self) -> set[uuid.UUID]: ...


@dataclass(frozen=True)
class V2TransferTarget:
    workstation_id: uuid.UUID
    name: str
    group_id: str | None


class V2TransferTargetService:
    def __init__(
        self,
        sessions: SessionService,
        workstations: WorkstationService,
        reservations: ReservationEntryLookup,
        transfers: ReservedTransferTargets,
    ) -> None:
        self._sessions = sessions
        self._workstations = workstations
        self._reservations = reservations
        self._transfers = transfers

    async def list_targets(self, device_id: str, session_id: uuid.UUID) -> list[V2TransferTarget]:
        source = await self._workstations.get_by_device_id(device_id)
        session = await self._sessions.get(session_id)
        if session.workstation_id != source.id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED, "Transfer requires the source device"
            )
        if (
            session.status is not SessionStatus.ACTIVE
            or session.source not in SessionService.LOCAL_SOURCES
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer requires an active V2 session")

        workstations = await self._workstations.list()
        if not any(
            item.id == source.id and item.status is WorkstationStatus.ONLINE
            for item in workstations
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer source is offline")
        occupied = {item.workstation_id for item in await self._sessions.list(active_only=True)}
        occupied.update(await self._transfers.list_reserved_targets())
        targets = []
        for item in workstations:
            if (
                item.id == source.id
                or item.id in occupied
                or not item.device_id
                or item.last_seen_at is None
                or item.equipment_type is EquipmentType.XBOX
                or item.session_mode is not WorkstationSessionMode.LOCAL_LEDGER
                or item.status is not WorkstationStatus.ONLINE
            ):
                continue
            decision = await self._reservations.check_entry(
                item.id, client_id=session.client_id, guest_id=session.guest_id
            )
            if decision.allowed:
                targets.append(V2TransferTarget(item.id, item.name, item.group_id))
        return targets


class TransferPreparationRepository(typing.Protocol):
    async def pending_for_target(
        self, target_workstation_id: uuid.UUID
    ) -> V2TransferReservation | None: ...
    async def get_for_workstation(
        self, operation_id: uuid.UUID, workstation_id: uuid.UUID
    ) -> V2TransferReservation: ...
    async def ready_target(
        self, operation_id: uuid.UUID, target_workstation_id: uuid.UUID
    ) -> V2TransferReservation: ...
    async def record_source_checkpoint(
        self,
        operation_id: uuid.UUID,
        source_workstation_id: uuid.UUID,
        checkpoint: V2TransferCheckpoint,
    ) -> V2TransferReservation: ...
    async def cancel(
        self, operation_id: uuid.UUID, source_workstation_id: uuid.UUID
    ) -> V2TransferReservation: ...


class ConfirmedTransferCheckpoint(typing.Protocol):
    async def is_confirmed(
        self,
        device_id: str,
        session_id: uuid.UUID,
        last_sequence: int,
        last_payload_hash: str | None,
    ) -> bool: ...


class V2TransferPreparationService:
    def __init__(
        self,
        workstations: WorkstationService,
        operations: TransferPreparationRepository,
        checkpoints: ConfirmedTransferCheckpoint,
    ) -> None:
        self._workstations = workstations
        self._operations = operations
        self._checkpoints = checkpoints

    async def pending_for_target(self, device_id: str) -> V2TransferReservation | None:
        workstation = await self._workstations.get_by_device_id(device_id)
        return await self._operations.pending_for_target(workstation.id)

    async def get(self, device_id: str, operation_id: uuid.UUID) -> V2TransferReservation:
        workstation = await self._workstations.get_by_device_id(device_id)
        return await self._operations.get_for_workstation(operation_id, workstation.id)

    async def ready_target(self, device_id: str, operation_id: uuid.UUID) -> V2TransferReservation:
        workstation = await self._workstations.get_by_device_id(device_id)
        return await self._operations.ready_target(operation_id, workstation.id)

    async def record_source_checkpoint(
        self, device_id: str, operation_id: uuid.UUID, checkpoint: V2TransferCheckpoint
    ) -> V2TransferReservation:
        workstation = await self._workstations.get_by_device_id(device_id)
        operation = await self._operations.get_for_workstation(operation_id, workstation.id)
        if operation.source_workstation_id != workstation.id:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Transfer operation not found")
        if operation.status != V2TransferStatus.PREPARING:
            return operation
        if not await self._checkpoints.is_confirmed(
            device_id, operation.session_id, checkpoint.sequence, checkpoint.payload_hash
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Transfer checkpoint is not confirmed")
        return await self._operations.record_source_checkpoint(
            operation_id, workstation.id, checkpoint
        )

    async def cancel(self, device_id: str, operation_id: uuid.UUID) -> V2TransferReservation:
        workstation = await self._workstations.get_by_device_id(device_id)
        return await self._operations.cancel(operation_id, workstation.id)
