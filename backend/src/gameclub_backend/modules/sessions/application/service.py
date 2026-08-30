from __future__ import annotations

import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.reservations.domain import ReservationStatus
from gameclub_backend.modules.sessions.application.ports import (
    ClientLookup,
    Clock,
    GuestLookup,
    ReservationLookup,
    SessionRepository,
    WorkstationLookup,
)
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.workstations.domain import WorkstationStatus


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class SessionService:
    def __init__(
        self,
        repository: SessionRepository,
        workstations: WorkstationLookup,
        clients: ClientLookup,
        reservations: ReservationLookup | None = None,
        clock: Clock | None = None,
        guests: GuestLookup | None = None,
    ) -> None:
        self._repository = repository
        self._workstations = workstations
        self._clients = clients
        self._guests = guests
        self._reservations = reservations
        self._clock = clock or UtcClock()

    async def start(
        self,
        workstation_id: uuid.UUID,
        created_by: str,
        client_id: uuid.UUID | None = None,
        guest_name: str | None = None,
        source: str = "operator",
        reservation_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        device_id: str | None = None,
        guest_id: uuid.UUID | None = None,
        tariff_id: uuid.UUID | None = None,
        tariff_quantity: int = 1,
    ) -> Session:
        normalized_idempotency_key = idempotency_key.strip() if idempotency_key else None
        if idempotency_key is not None and (
            not normalized_idempotency_key or len(normalized_idempotency_key) > 128
        ):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        normalized_created_by = created_by.strip()
        if not normalized_created_by:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Session author is required")
        normalized_guest_name = guest_name.strip() if guest_name else None
        normalized_source = source.strip() or "operator"
        if tariff_quantity <= 0:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Tariff quantity must be positive")
        workstation = await self._workstations.get(workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        if workstation.status is WorkstationStatus.DISABLED:
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation is disabled")
        if device_id is not None and workstation.device_id != device_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Device identity does not match workstation",
            )
        if client_id is not None and guest_id is not None:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Client and guest cannot be used together",
            )
        if guest_id is not None:
            if self._guests is None:
                raise ApplicationError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "Guest lookup is not configured",
                )
            guest = await self._guests.get(guest_id)
            if guest is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Guest not found")
            if guest_name and guest_name.strip() != guest.nickname:
                raise ApplicationError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Guest name does not match guest profile",
                )
            normalized_guest_name = guest.nickname
        if client_id is None and guest_id is None:
            normalized_guest_name = normalized_guest_name or "Гость"
        if client_id is not None and await self._clients.get(client_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Client not found")
        if reservation_id is not None:
            if self._reservations is None:
                raise ApplicationError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "Reservation lookup is not configured",
                )
            reservation = await self._reservations.get(reservation_id)
            if reservation is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Reservation not found")
            if workstation_id not in reservation.workstation_ids or reservation.status not in {
                ReservationStatus.CONFIRMED,
                ReservationStatus.ACTIVE,
            }:
                raise ApplicationError(
                    ErrorCode.CONFLICT,
                    "Reservation cannot be used for this session",
                )
        if normalized_idempotency_key:
            existing = await self._repository.get_by_idempotency_key(normalized_idempotency_key)
            if existing is not None:
                self._validate_idempotent_session(
                    existing,
                    workstation_id=workstation_id,
                    client_id=client_id,
                    guest_id=guest_id,
                    guest_name=normalized_guest_name,
                    source=normalized_source,
                    reservation_id=reservation_id,
                    created_by=normalized_created_by,
                    tariff_id=tariff_id,
                    tariff_quantity=tariff_quantity,
                )
                return existing
        if await self._repository.get_active_for_workstation(workstation_id) is not None:
            if normalized_idempotency_key:
                repeated = await self._repository.get_by_idempotency_key(normalized_idempotency_key)
                if repeated is not None:
                    self._validate_idempotent_session(
                        repeated,
                        workstation_id=workstation_id,
                        client_id=client_id,
                        guest_id=guest_id,
                        guest_name=normalized_guest_name,
                        source=normalized_source,
                        reservation_id=reservation_id,
                        created_by=normalized_created_by,
                        tariff_id=tariff_id,
                        tariff_quantity=tariff_quantity,
                    )
                    return repeated
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation already has an active session")

        now = self._clock.now()
        session = Session(
            id=uuid.uuid4(),
            workstation_id=workstation_id,
            client_id=client_id,
            guest_name=normalized_guest_name,
            status=SessionStatus.ACTIVE,
            started_at=now,
            ended_at=None,
            source=normalized_source,
            created_by=normalized_created_by,
            created_at=now,
            reservation_id=reservation_id,
            idempotency_key=normalized_idempotency_key,
            guest_id=guest_id,
            tariff_id=tariff_id,
            tariff_quantity=tariff_quantity,
        )
        try:
            saved = await self._repository.save(session)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if saved.id != session.id and normalized_idempotency_key:
            self._validate_idempotent_session(
                saved,
                workstation_id=workstation_id,
                client_id=client_id,
                guest_id=guest_id,
                guest_name=normalized_guest_name,
                source=normalized_source,
                reservation_id=reservation_id,
                created_by=normalized_created_by,
                tariff_id=tariff_id,
                tariff_quantity=tariff_quantity,
            )
        return saved

    async def get(self, session_id: uuid.UUID) -> Session:
        session = await self._repository.get(session_id)
        if session is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Session not found")
        return session

    async def list(
        self,
        workstation_id: uuid.UUID | None = None,
        active_only: bool = False,
    ) -> list[Session]:
        return await self._repository.list(workstation_id, active_only)

    @staticmethod
    def _validate_idempotent_session(
        existing: Session,
        *,
        workstation_id: uuid.UUID,
        client_id: uuid.UUID | None,
        guest_id: uuid.UUID | None,
        guest_name: str | None,
        source: str,
        reservation_id: uuid.UUID | None,
        created_by: str,
        tariff_id: uuid.UUID | None,
        tariff_quantity: int,
    ) -> None:
        if (
            existing.workstation_id != workstation_id
            or existing.client_id != client_id
            or existing.guest_id != guest_id
            or existing.guest_name != guest_name
            or existing.source != source
            or existing.reservation_id != reservation_id
            or existing.created_by != created_by
            or existing.tariff_id != tariff_id
            or existing.tariff_quantity != tariff_quantity
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Idempotency key belongs to another session",
            )

    async def stop(self, session_id: uuid.UUID, device_id: str | None = None) -> Session:
        session = await self.get(session_id)
        if device_id is not None:
            workstation = await self._workstations.get(session.workstation_id)
            if workstation is None or workstation.device_id != device_id:
                raise ApplicationError(
                    ErrorCode.PERMISSION_DENIED,
                    "Device identity does not match workstation",
                )
        try:
            return await self._repository.save(session.stop(self._clock.now()))
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def interrupt(
        self,
        session_id: uuid.UUID,
        interrupted_by: str,
        reason: str,
        idempotency_key: str,
    ) -> Session:
        """Operator action for an early finish; repeated completion is harmless."""
        if not interrupted_by.strip():
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Session interrupter is required")
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 256:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Interruption reason is required")
        normalized_idempotency_key = idempotency_key.strip()
        if not normalized_idempotency_key or len(normalized_idempotency_key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")

        session = await self.get(session_id)
        try:
            return await self._repository.save(session.interrupt(self._clock.now()))
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
