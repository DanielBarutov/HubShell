import datetime
import typing
import uuid

from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus


class EntitlementTransactionWriter(typing.Protocol):
    async def apply_local_usage(
        self,
        transaction: typing.Any,
        client_id: uuid.UUID,
        package_id: uuid.UUID,
        tariff_id: uuid.UUID,
        remaining_minutes: int,
        occurred_at: datetime.datetime,
        *,
        burned: bool,
        purchase_idempotency_key: str | None,
        purchased_since: datetime.datetime,
    ) -> bool:
        """Project a validated local package fact in the caller's transaction."""


class EntitlementRepository(typing.Protocol):
    async def get(self, entitlement_id: uuid.UUID) -> Entitlement | None:
        """Return one entitlement by ID."""

    async def get_by_idempotency_key(self, key: str) -> Entitlement | None:
        """Return the entitlement created by the same purchase request."""

    async def list_for_client(self, client_id: uuid.UUID) -> list[Entitlement]:
        """Return the ordered entitlement queue for a client."""

    async def get_active_for_client(self, client_id: uuid.UUID) -> Entitlement | None:
        """Return the one active entitlement for a client, if any."""

    async def create(self, entitlement: Entitlement) -> Entitlement:
        """Persist a new queue item and enforce its idempotency key."""

    async def save(self, entitlement: Entitlement) -> Entitlement:
        """Persist an entitlement state transition."""

    async def next_compatible(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        statuses: tuple[EntitlementStatus, ...] = (EntitlementStatus.QUEUED,),
        now: datetime.datetime | None = None,
    ) -> Entitlement | None:
        """Return the first compatible queue item in stable order."""

    async def activate_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        now: datetime.datetime,
        zone_id: str | None = None,
    ) -> Entitlement:
        """Atomically activate one entitlement for a client."""

    async def consume_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        minutes: int,
        now: datetime.datetime,
    ) -> tuple[Entitlement, int]:
        """Atomically consume minutes and return the actual consumed delta."""

    async def burn_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        reason: str,
        now: datetime.datetime,
    ) -> Entitlement:
        """Atomically burn an already started entitlement."""

    async def list_recoverable_settlements(
        self,
        limit: int = 100,
        now: datetime.datetime | None = None,
    ) -> list[Entitlement]:
        """Return pending entitlement settlements due for retry."""


class ClientEntitlementDebit(typing.Protocol):
    async def get(self, client_id: uuid.UUID):
        """Read the registered customer's server-owned discount category."""

    async def debit(
        self,
        client_id: uuid.UUID,
        amount_cents: int,
        reason: str,
        actor_id: str,
        idempotency_key: str,
        allow_negative_balance: bool = False,
    ) -> tuple[object, object]:
        """Debit a registered client's balance for a package purchase."""

    async def top_up(
        self,
        client_id: uuid.UUID,
        amount_cents: int,
        bonus_amount: int,
        reason: str,
        actor_id: str,
        idempotency_key: str,
    ) -> tuple[object, object]:
        """Compensate a debit when package creation fails after settlement."""


class CashEntitlementSettlement(typing.Protocol):
    async def settle(
        self,
        shift_id: uuid.UUID,
        amount_cents: int,
        payment_idempotency_key: str,
        actor_id: str,
    ) -> None:
        """Record confirmed cash for an entitlement purchase."""


class TariffLookup(typing.Protocol):
    async def get_tariff(self, tariff_id: uuid.UUID):
        """Return a tariff snapshot used for the entitlement."""

    async def quote_for_tariff(
        self,
        tariff_id: uuid.UUID,
        group_id: str | None,
        moment: datetime.datetime,
        discount_category: str | None = None,
        **kwargs,
    ):
        """Quote the selected package with the customer's existing catalog discounts."""


class ActiveSessionLookup(typing.Protocol):
    async def get_active_for_client(self, client_id: uuid.UUID):
        """Return the client's active session, if any."""


class WorkstationLookup(typing.Protocol):
    async def get(self, workstation_id: uuid.UUID):
        """Return the workstation hosting an active client session."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
