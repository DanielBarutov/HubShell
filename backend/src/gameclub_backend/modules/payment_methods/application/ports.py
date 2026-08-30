import typing
import uuid

from gameclub_backend.modules.payment_methods.domain import PaymentMethod


class PaymentMethodRepository(typing.Protocol):
    async def get(self, method_id: uuid.UUID) -> PaymentMethod | None:
        """Return a payment method by ID."""

    async def get_by_key(self, key: str) -> PaymentMethod | None:
        """Return a payment method by its stable key."""

    async def list(self) -> list[PaymentMethod]:
        """Return payment methods in operator display order."""

    async def save(self, method: PaymentMethod) -> PaymentMethod:
        """Create or update a payment method."""

    async def delete(self, method_id: uuid.UUID) -> None:
        """Delete a payment method configuration."""
