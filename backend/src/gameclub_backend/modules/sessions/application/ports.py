from __future__ import annotations

import datetime
import typing
import uuid

from gameclub_backend.modules.clients.domain import Client, Guest
from gameclub_backend.modules.direct_payments.domain import GuestSessionPayment
from gameclub_backend.modules.entitlements.domain import Entitlement
from gameclub_backend.modules.reservations.domain import Reservation
from gameclub_backend.modules.sessions.domain import Session, SessionTransferOffer
from gameclub_backend.modules.workstations.domain import Workstation


class SessionRepository(typing.Protocol):
    async def get(self, session_id: uuid.UUID) -> Session | None:
        """Return a session by ID."""

    async def get_active_for_workstation(self, workstation_id: uuid.UUID) -> Session | None:
        """Return the active session for one workstation, if any."""

    async def get_active_for_client(self, client_id: uuid.UUID) -> Session | None:
        """Return the active session for one registered client, if any."""

    async def get_by_idempotency_key(self, idempotency_key: str) -> Session | None:
        """Return a session created by the same idempotency key."""

    async def list(
        self,
        workstation_id: uuid.UUID | None = None,
        active_only: bool = False,
    ) -> list[Session]:
        """Return sessions for operator display."""

    async def list_for_client(self, client_id: uuid.UUID, limit: int) -> list[Session]:
        """Return recent sessions belonging to one client."""

    async def save(self, session: Session) -> Session:
        """Persist a session or its lifecycle transition."""


class SessionTransferRepository(typing.Protocol):
    async def get(self, offer_id: uuid.UUID) -> SessionTransferOffer | None:
        """Return a transfer offer by ID."""

    async def get_by_idempotency_key(self, key: str) -> SessionTransferOffer | None:
        """Return an offer created by the same request key."""

    async def save(self, offer: SessionTransferOffer) -> SessionTransferOffer:
        """Persist an offer transition idempotently."""

    async def commit_transfer(
        self,
        offer: SessionTransferOffer,
        session: Session,
    ) -> tuple[SessionTransferOffer, Session]:
        """Commit offer confirmation and session ownership in one owner transaction."""


class WorkstationLookup(typing.Protocol):
    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        """Return a workstation by ID."""


class ClientLookup(typing.Protocol):
    async def get(self, client_id: uuid.UUID) -> Client | None:
        """Return a client by ID."""


class GuestLookup(typing.Protocol):
    async def get(self, guest_id: uuid.UUID) -> Guest | None:
        """Return a guest by ID."""


class GuestPaymentLookup(typing.Protocol):
    async def get(self, payment_id: uuid.UUID) -> GuestSessionPayment | None:
        """Return a confirmed direct payment for a guest session."""


class EntitlementLookup(typing.Protocol):
    async def get(self, entitlement_id: uuid.UUID) -> Entitlement | None:
        """Return one package entitlement."""

    async def get_active_for_client(self, client_id: uuid.UUID) -> Entitlement | None:
        """Return the active package for a client."""

    async def list_for_client(self, client_id: uuid.UUID) -> list[Entitlement]:
        """Return the ordered package queue for a client."""

    async def burn_active_for_client(self, client_id: uuid.UUID, reason: str) -> Entitlement | None:
        """Burn the currently active package after an explicit session stop."""


class MeterLookup(typing.Protocol):
    async def get(self, session_id: uuid.UUID):
        """Return the current session meter, if one has started."""


class ReservationLookup(typing.Protocol):
    async def get(self, reservation_id: uuid.UUID) -> Reservation:
        """Return a reservation by ID."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
