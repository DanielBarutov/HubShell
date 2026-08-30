import dataclasses
import datetime
import enum
import typing
import uuid


class ReservationStatus(enum.StrEnum):
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


@dataclasses.dataclass(frozen=True)
class ReservationAvailability:
    available: bool
    conflicting_reservation_ids: tuple[uuid.UUID, ...] = ()
    reason: str | None = None


@dataclasses.dataclass(frozen=True)
class Reservation:
    id: uuid.UUID
    workstation_ids: tuple[uuid.UUID, ...]
    client_id: uuid.UUID | None
    guest_name: str | None
    start_at: datetime.datetime
    end_at: datetime.datetime
    status: ReservationStatus
    notes: str | None
    tariff_id: uuid.UUID | None
    created_by: str
    created_at: datetime.datetime
    cancelled_at: datetime.datetime | None = None
    idempotency_key: str | None = None
    guest_id: uuid.UUID | None = None

    def cancel(self, now: datetime.datetime) -> "Reservation":
        if self.status in {
            ReservationStatus.CANCELLED,
            ReservationStatus.COMPLETED,
            ReservationStatus.NO_SHOW,
        }:
            raise ValueError("Reservation cannot be cancelled in its current state")
        return dataclasses.replace(
            self,
            status=ReservationStatus.CANCELLED,
            cancelled_at=now,
        )

    def activate(self) -> "Reservation":
        if self.status is not ReservationStatus.CONFIRMED:
            raise ValueError("Only confirmed reservation can be activated")
        return dataclasses.replace(self, status=ReservationStatus.ACTIVE)

    def complete(self) -> "Reservation":
        if self.status is not ReservationStatus.ACTIVE:
            raise ValueError("Only active reservation can be completed")
        return dataclasses.replace(self, status=ReservationStatus.COMPLETED)

    def mark_no_show(
        self,
        now: datetime.datetime,
        grace_period_minutes: int,
    ) -> "Reservation":
        if self.status is not ReservationStatus.CONFIRMED:
            raise ValueError("Only confirmed reservation can be marked as no-show")
        if grace_period_minutes < 0:
            raise ValueError("Grace period cannot be negative")
        if now.tzinfo is None or now < self.start_at + datetime.timedelta(
            minutes=grace_period_minutes
        ):
            raise ValueError("Reservation grace period has not elapsed")
        return dataclasses.replace(self, status=ReservationStatus.NO_SHOW)

    def update_details(
        self,
        workstation_ids: typing.Sequence[uuid.UUID],
        start_at: datetime.datetime,
        end_at: datetime.datetime,
        client_id: uuid.UUID | None,
        guest_name: str | None,
        notes: str | None,
        tariff_id: uuid.UUID | None,
        guest_id: uuid.UUID | None = None,
    ) -> "Reservation":
        if self.status is not ReservationStatus.CONFIRMED:
            raise ValueError("Only confirmed reservation can be updated")
        resource_ids = tuple(dict.fromkeys(workstation_ids))
        normalized_guest_name = guest_name.strip() if guest_name else None
        if not resource_ids:
            raise ValueError("At least one workstation is required")
        if start_at.tzinfo is None or end_at.tzinfo is None or end_at <= start_at:
            raise ValueError("Reservation period is invalid")
        if client_id is None and guest_id is None:
            normalized_guest_name = normalized_guest_name or "Гость"
        return dataclasses.replace(
            self,
            workstation_ids=resource_ids,
            client_id=client_id,
            guest_name=normalized_guest_name,
            guest_id=guest_id,
            start_at=start_at,
            end_at=end_at,
            notes=notes.strip() if notes else None,
            tariff_id=tariff_id,
        )

    def overlaps(self, start_at: datetime.datetime, end_at: datetime.datetime) -> bool:
        return self.start_at < end_at and start_at < self.end_at
