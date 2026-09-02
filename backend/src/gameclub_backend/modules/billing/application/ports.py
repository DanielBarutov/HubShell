import contextlib
import datetime
import typing
import uuid

from gameclub_backend.modules.billing.domain import (
    ChargeReconciliation,
    RevenueSummary,
    SessionCharge,
    SessionMeter,
)
from gameclub_backend.modules.catalog.domain import Quote
from gameclub_backend.modules.clients.domain import BalanceOperation, Client
from gameclub_backend.modules.sessions.domain import Session
from gameclub_backend.modules.workstations.domain import Workstation


class ChargeRepository(typing.Protocol):
    async def get_by_session_id(self, session_id: uuid.UUID) -> SessionCharge | None:
        """Return the charge recorded for one session."""

    async def get_by_idempotency_key(self, idempotency_key: str) -> SessionCharge | None:
        """Return a charge created by the same request key."""

    async def list_for_client(self, client_id: uuid.UUID, limit: int) -> list[SessionCharge]:
        """Return recent session charges belonging to one client."""

    async def save(self, charge: SessionCharge) -> SessionCharge:
        """Persist a charge or return a concurrently created equivalent."""

    async def revenue_between(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> RevenueSummary:
        """Aggregate persisted charges inside a half-open UTC period."""


class ChargeReconciliationRepository(typing.Protocol):
    async def get_by_session_id(self, session_id: uuid.UUID) -> ChargeReconciliation | None:
        """Return the durable reconciliation record for a session."""

    async def ensure_pending(self, item: ChargeReconciliation) -> ChargeReconciliation:
        """Create one pending record or return the existing session record."""

    async def save(self, item: ChargeReconciliation) -> ChargeReconciliation:
        """Persist a state transition without downgrading a completed record."""

    async def list_due(
        self,
        now: datetime.datetime,
        limit: int,
    ) -> list[ChargeReconciliation]:
        """Return pending/retryable records ready for another attempt."""

    async def list_recent(self, limit: int) -> list[ChargeReconciliation]:
        """Return records for operator diagnostics."""


class MeterRepository(typing.Protocol):
    def acquire(self, session_id: uuid.UUID) -> contextlib.AbstractAsyncContextManager[None]:
        """Serialize the complete debit-and-save cycle for one session."""

    async def get(self, session_id: uuid.UUID) -> SessionMeter | None:
        """Return the meter for one session."""

    async def ensure(self, meter: SessionMeter) -> SessionMeter:
        """Create a meter or return the already existing one."""

    async def save(self, meter: SessionMeter) -> SessionMeter:
        """Persist monotonic meter progress."""


class SessionLookup(typing.Protocol):
    async def get(self, session_id: uuid.UUID) -> Session | None:
        """Return a session by ID."""


class WorkstationLookup(typing.Protocol):
    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        """Return a workstation by ID."""


class ClientBilling(typing.Protocol):
    async def get(self, client_id: uuid.UUID) -> Client:
        """Return a client or raise a not-found application error."""

    async def debit(
        self,
        client_id: uuid.UUID,
        amount_cents: int,
        reason: str,
        actor_id: str,
        idempotency_key: str,
    ) -> tuple[Client, BalanceOperation]:
        """Debit the client's spendable balance atomically."""


class CatalogQuoter(typing.Protocol):
    async def get_tariff(self, tariff_id: uuid.UUID):
        """Return the selected tariff for lifecycle-specific billing."""

    async def quote(
        self,
        duration_minutes: int,
        group_id: str | None,
        moment: datetime.datetime,
        discount_category: str | None = None,
    ) -> Quote:
        """Calculate the immutable price snapshot for a session."""

    async def quote_for_tariff(
        self,
        tariff_id: uuid.UUID,
        group_id: str | None,
        moment: datetime.datetime,
        discount_category: str | None = None,
        duration_minutes: int | None = None,
        quantity: int = 1,
    ) -> Quote:
        """Calculate a quote for the tariff explicitly selected at session start."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
