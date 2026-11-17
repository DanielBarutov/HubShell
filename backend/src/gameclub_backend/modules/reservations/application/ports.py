from __future__ import annotations

import builtins
import datetime
import typing
import uuid

from gameclub_backend.modules.clients.domain import Client, Guest
from gameclub_backend.modules.reservations.domain import EntryDecision, Reservation
from gameclub_backend.modules.workstations.domain import Workstation


class ReservationRepository(typing.Protocol):
    def lock_workstation(self, workstation_id: uuid.UUID) -> typing.AsyncContextManager[None]:
        """Serialize the entry check with writes for this workstation."""

    async def get(self, reservation_id: uuid.UUID) -> Reservation | None:
        """Return a reservation by ID."""

    async def get_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        """Return a reservation created by the same idempotency key."""

    async def list(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> builtins.list[Reservation]:
        """Return reservations intersecting a period."""

    async def list_for_client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        limit: int,
    ) -> builtins.list[Reservation]:
        """Return future confirmed reservations assigned to one client."""

    async def list_pending_no_show(
        self,
        cutoff_at: datetime.datetime,
    ) -> builtins.list[Reservation]:
        """Return confirmed reservations whose grace-period cutoff has elapsed."""

    async def mark_no_show_if_eligible(
        self,
        reservation_id: uuid.UUID,
        now: datetime.datetime,
        grace_period_minutes: int,
    ) -> Reservation | None:
        """Atomically mark a confirmed reservation as no-show when it is eligible."""

    async def complete_expired(self, now: datetime.datetime) -> int:
        """End live reservations whose booked period has elapsed."""

    async def delete(self, reservation_id: uuid.UUID) -> bool:
        """Delete a reservation if it still exists."""

    async def save(
        self, reservation: Reservation, *, existing_required: bool = False
    ) -> Reservation:
        """Persist a reservation."""


class WorkstationLookup(typing.Protocol):
    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        """Return a workstation by ID."""


class ClientLookup(typing.Protocol):
    async def get(self, client_id: uuid.UUID) -> Client | None:
        """Return a client by ID."""


class GuestLookup(typing.Protocol):
    async def get(self, guest_id: uuid.UUID) -> Guest | None:
        """Return a guest by ID."""


class PaidSessionLookup(typing.Protocol):
    async def paid_session_ends_at(self, workstation_id: uuid.UUID) -> datetime.datetime | None: ...


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""


class ReservationEntryLookup(typing.Protocol):
    async def check_entry(
        self,
        workstation_id: uuid.UUID,
        client_id: uuid.UUID | None = None,
        guest_id: uuid.UUID | None = None,
        now: datetime.datetime | None = None,
        *,
        guest_reservation_id: uuid.UUID | None = None,
    ) -> EntryDecision:
        """Return the authoritative workstation entry decision."""


class TransferReservationEntryLookup(typing.Protocol):
    async def check_entry_for_transfer(
        self,
        workstation_id: uuid.UUID,
        client_id: uuid.UUID | None = None,
        guest_id: uuid.UUID | None = None,
    ) -> EntryDecision:
        """Check entry while holding the booking lock until the transfer transaction ends."""
