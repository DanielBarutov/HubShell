from __future__ import annotations

import datetime
import typing
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.reservations.application.ports import (
    ClientLookup,
    Clock,
    GuestLookup,
    ReservationRepository,
    WorkstationLookup,
)
from gameclub_backend.modules.reservations.domain import (
    Reservation,
    ReservationAvailability,
    ReservationStatus,
)
from gameclub_backend.modules.workstations.domain import WorkstationStatus


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class ReservationService:
    def __init__(
        self,
        repository: ReservationRepository,
        workstations: WorkstationLookup,
        clients: ClientLookup,
        clock: Clock | None = None,
        grace_period_minutes: int = 15,
        guests: GuestLookup | None = None,
    ) -> None:
        if grace_period_minutes < 0:
            raise ValueError("Grace period cannot be negative")
        self._repository = repository
        self._workstations = workstations
        self._clients = clients
        self._guests = guests
        self._clock = clock or UtcClock()
        self._grace_period_minutes = grace_period_minutes

    async def list(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> list[Reservation]:
        self._validate_period(start_at, end_at)
        return await self._repository.list(start_at, end_at)

    async def get(self, reservation_id: uuid.UUID) -> Reservation:
        reservation = await self._repository.get(reservation_id)
        if reservation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Reservation not found")
        return reservation

    async def check_availability(
        self,
        workstation_ids: typing.Sequence[uuid.UUID],
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> ReservationAvailability:
        self._validate_period(start_at, end_at)
        resource_ids = self._normalize_resource_ids(workstation_ids)
        availability = await self._check_availability(
            resource_ids,
            start_at,
            end_at,
        )
        return availability

    async def create(
        self,
        workstation_ids: typing.Sequence[uuid.UUID],
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        created_by: str,
        client_id: uuid.UUID | None = None,
        guest_name: str | None = None,
        notes: str | None = None,
        tariff_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        guest_id: uuid.UUID | None = None,
    ) -> Reservation:
        self._validate_period(start_at, end_at)
        resource_ids = tuple(dict.fromkeys(workstation_ids))
        if not resource_ids:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "At least one workstation is required",
            )
        normalized_key = idempotency_key.strip() if idempotency_key is not None else None
        if idempotency_key is not None:
            if not normalized_key or len(normalized_key) > 128:
                raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        normalized_created_by = created_by.strip()
        if not normalized_created_by:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Reservation author is required")
        normalized_guest_name = guest_name.strip() if guest_name else None
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
            if normalized_guest_name and normalized_guest_name != guest.nickname:
                raise ApplicationError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Guest name does not match guest profile",
                )
            normalized_guest_name = guest.nickname
        if client_id is None and guest_id is None:
            normalized_guest_name = normalized_guest_name or "Гость"
        if client_id is not None and await self._clients.get(client_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Client not found")
        if normalized_key:
            existing = await self._repository.get_by_idempotency_key(normalized_key)
            if existing is not None:
                self._validate_idempotent_reservation(
                    existing,
                    workstation_ids=resource_ids,
                    start_at=start_at,
                    end_at=end_at,
                    client_id=client_id,
                    guest_id=guest_id,
                    guest_name=normalized_guest_name,
                    notes=notes,
                    tariff_id=tariff_id,
                    created_by=normalized_created_by,
                )
                return existing

        availability = await self._check_availability(resource_ids, start_at, end_at)
        self._raise_if_unavailable(availability)

        reservation = Reservation(
            id=uuid.uuid4(),
            workstation_ids=resource_ids,
            client_id=client_id,
            guest_name=normalized_guest_name,
            start_at=start_at,
            end_at=end_at,
            status=ReservationStatus.CONFIRMED,
            notes=notes.strip() if notes else None,
            tariff_id=tariff_id,
            created_by=normalized_created_by,
            created_at=self._clock.now(),
            idempotency_key=normalized_key,
            guest_id=guest_id,
        )
        try:
            saved = await self._repository.save(reservation)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if saved.id != reservation.id and normalized_key:
            self._validate_idempotent_reservation(
                saved,
                workstation_ids=resource_ids,
                start_at=start_at,
                end_at=end_at,
                client_id=client_id,
                guest_id=guest_id,
                guest_name=normalized_guest_name,
                notes=notes,
                tariff_id=tariff_id,
                created_by=normalized_created_by,
            )
        return saved

    async def update(
        self,
        reservation_id: uuid.UUID,
        workstation_ids: typing.Sequence[uuid.UUID],
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        client_id: uuid.UUID | None = None,
        guest_name: str | None = None,
        notes: str | None = None,
        tariff_id: uuid.UUID | None = None,
        guest_id: uuid.UUID | None = None,
    ) -> Reservation:
        self._validate_period(start_at, end_at)
        reservation = await self.get(reservation_id)
        normalized_guest_name = guest_name.strip() if guest_name else None
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
            if normalized_guest_name and normalized_guest_name != guest.nickname:
                raise ApplicationError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Guest name does not match guest profile",
                )
            normalized_guest_name = guest.nickname
        if client_id is None and guest_id is None:
            normalized_guest_name = normalized_guest_name or "Гость"
        if client_id is not None and await self._clients.get(client_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Client not found")

        resource_ids = tuple(dict.fromkeys(workstation_ids))
        if not resource_ids:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "At least one workstation is required",
            )
        availability = await self._check_availability(
            resource_ids,
            start_at,
            end_at,
            excluded_reservation_id=reservation.id,
        )
        self._raise_if_unavailable(availability)

        try:
            updated = reservation.update_details(
                workstation_ids=resource_ids,
                start_at=start_at,
                end_at=end_at,
                client_id=client_id,
                guest_name=normalized_guest_name,
                notes=notes,
                tariff_id=tariff_id,
                guest_id=guest_id,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

        try:
            return await self._repository.save(updated)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def cancel(self, reservation_id: uuid.UUID) -> Reservation:
        reservation = await self.get(reservation_id)
        try:
            cancelled = reservation.cancel(self._clock.now())
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        return await self._repository.save(cancelled)

    async def activate(self, reservation_id: uuid.UUID) -> Reservation:
        reservation = await self.get(reservation_id)
        try:
            return await self._repository.save(reservation.activate())
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def complete(self, reservation_id: uuid.UUID) -> Reservation:
        reservation = await self.get(reservation_id)
        try:
            return await self._repository.save(reservation.complete())
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def mark_no_show(self, reservation_id: uuid.UUID) -> Reservation:
        reservation = await self.get(reservation_id)
        try:
            return await self._repository.save(
                reservation.mark_no_show(self._clock.now(), self._grace_period_minutes)
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error

    async def sweep_no_shows(
        self,
        now: datetime.datetime | None = None,
    ) -> list[Reservation]:
        """Mark eligible reservations without overwriting a concurrent state change."""
        current_time = now or self._clock.now()
        if current_time.tzinfo is None:
            raise ValueError("Sweep time must include timezone")
        cutoff_at = current_time - datetime.timedelta(minutes=self._grace_period_minutes)
        candidates = await self._repository.list_pending_no_show(cutoff_at)
        updated: list[Reservation] = []
        for candidate in candidates:
            reservation = await self._repository.mark_no_show_if_eligible(
                candidate.id,
                current_time,
                self._grace_period_minutes,
            )
            if reservation is not None:
                updated.append(reservation)
        return updated

    @staticmethod
    def _validate_period(start_at: datetime.datetime, end_at: datetime.datetime) -> None:
        if start_at.tzinfo is None or end_at.tzinfo is None:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Reservation dates must include timezone",
            )
        if end_at <= start_at:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Reservation period is invalid")

    async def _check_availability(
        self,
        resource_ids: tuple[uuid.UUID, ...],
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        excluded_reservation_id: uuid.UUID | None = None,
    ) -> ReservationAvailability:
        for workstation_id in resource_ids:
            workstation = await self._workstations.get(workstation_id)
            if workstation is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
            if workstation.status is WorkstationStatus.DISABLED:
                return ReservationAvailability(
                    available=False,
                    reason="workstation_disabled",
                )

        existing = await self._repository.list(start_at, end_at)
        conflicts = tuple(
            item.id
            for item in existing
            if item.id != excluded_reservation_id
            and item.status in {ReservationStatus.CONFIRMED, ReservationStatus.ACTIVE}
            and set(item.workstation_ids).intersection(resource_ids)
            and item.overlaps(start_at, end_at)
        )
        return ReservationAvailability(
            available=not conflicts,
            conflicting_reservation_ids=conflicts,
            reason="workstation_reserved" if conflicts else None,
        )

    @staticmethod
    def _normalize_resource_ids(
        workstation_ids: typing.Sequence[uuid.UUID],
    ) -> tuple[uuid.UUID, ...]:
        resource_ids = tuple(dict.fromkeys(workstation_ids))
        if not resource_ids:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "At least one workstation is required",
            )
        return resource_ids

    @staticmethod
    def _raise_if_unavailable(availability: ReservationAvailability) -> None:
        if availability.available:
            return
        messages = {
            "workstation_disabled": "Workstation is disabled",
            "workstation_reserved": "Workstation is already reserved for this period",
        }
        raise ApplicationError(
            ErrorCode.CONFLICT,
            messages.get(availability.reason or "", "Workstation is unavailable"),
        )

    @staticmethod
    def _validate_idempotent_reservation(
        existing: Reservation,
        *,
        workstation_ids: tuple[uuid.UUID, ...],
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        client_id: uuid.UUID | None,
        guest_id: uuid.UUID | None,
        guest_name: str | None,
        notes: str | None,
        tariff_id: uuid.UUID | None,
        created_by: str,
    ) -> None:
        normalized_guest_name = guest_name.strip() if guest_name else None
        normalized_notes = notes.strip() if notes else None
        if (
            existing.workstation_ids != workstation_ids
            or existing.start_at != start_at
            or existing.end_at != end_at
            or existing.client_id != client_id
            or existing.guest_id != guest_id
            or existing.guest_name != normalized_guest_name
            or existing.notes != normalized_notes
            or existing.tariff_id != tariff_id
            or existing.created_by != created_by
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Idempotency key belongs to another reservation",
            )
