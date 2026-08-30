from __future__ import annotations

import datetime
import typing
import uuid

from gameclub_backend.modules.clients.domain import Client, Guest
from gameclub_backend.modules.reservations.domain import Reservation
from gameclub_backend.modules.sessions.domain import Session
from gameclub_backend.modules.workstations.domain import Workstation


class SessionRepository(typing.Protocol):
    async def get(self, session_id: uuid.UUID) -> Session | None:
        """Return a session by ID."""

    async def get_active_for_workstation(self, workstation_id: uuid.UUID) -> Session | None:
        """Return the active session for one workstation, if any."""

    async def get_by_idempotency_key(self, idempotency_key: str) -> Session | None:
        """Return a session created by the same idempotency key."""

    async def list(
        self,
        workstation_id: uuid.UUID | None = None,
        active_only: bool = False,
    ) -> list[Session]:
        """Return sessions for operator display."""

    async def save(self, session: Session) -> Session:
        """Persist a session or its lifecycle transition."""


class WorkstationLookup(typing.Protocol):
    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        """Return a workstation by ID."""


class ClientLookup(typing.Protocol):
    async def get(self, client_id: uuid.UUID) -> Client | None:
        """Return a client by ID."""


class GuestLookup(typing.Protocol):
    async def get(self, guest_id: uuid.UUID) -> Guest | None:
        """Return a guest by ID."""


class ReservationLookup(typing.Protocol):
    async def get(self, reservation_id: uuid.UUID) -> Reservation:
        """Return a reservation by ID."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
