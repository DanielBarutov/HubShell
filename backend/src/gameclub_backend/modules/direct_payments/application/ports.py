import datetime
import typing
import uuid

from gameclub_backend.modules.direct_payments.domain import GuestSessionPayment


class GuestSessionPaymentRepository(typing.Protocol):
    async def get(self, payment_id: uuid.UUID) -> GuestSessionPayment | None:
        """Return one confirmed guest payment."""

    async def get_by_idempotency_key(self, key: str) -> GuestSessionPayment | None:
        """Return the payment created by the same request."""

    async def save(self, payment: GuestSessionPayment) -> GuestSessionPayment:
        """Persist a payment state idempotently."""

    async def list_recoverable(
        self,
        limit: int = 100,
        now: datetime.datetime | None = None,
    ) -> list[GuestSessionPayment]:
        """Return pending payments eligible for durable reconciliation."""


class TariffLookup(typing.Protocol):
    async def get_tariff(self, tariff_id: uuid.UUID):
        """Return the tariff snapshot used for direct payment."""


class CashDirectSettlement(typing.Protocol):
    async def settle(
        self,
        shift_id: uuid.UUID,
        amount_cents: int,
        payment_idempotency_key: str,
        actor_id: str,
    ) -> None:
        """Record confirmed cash for a guest tariff payment."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
