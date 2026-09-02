import datetime
import typing
import uuid

from gameclub_backend.modules.clients.domain import BalanceOperation, Client, Guest


class ClientRepository(typing.Protocol):
    async def get(self, client_id: uuid.UUID) -> Client | None:
        """Return a client by ID."""

    async def get_by_nickname(self, nickname: str) -> Client | None:
        """Return a client by case-insensitive nickname."""

    async def get_by_phone(self, phone: str) -> Client | None:
        """Return a client by canonical phone."""

    async def list_clients(self) -> list[Client]:
        """Return clients ordered for operator display."""

    async def search(self, query: str, field: str) -> list[Client]:
        """Search clients by a normalized field."""

    async def save(self, client: Client) -> Client:
        """Persist a client."""

    async def delete(self, client_id: uuid.UUID) -> None:
        """Remove or archive a client from the operator directory."""

    async def add_operation(self, operation: BalanceOperation) -> BalanceOperation:
        """Persist a balance operation."""

    async def get_operation_by_key(self, idempotency_key: str) -> BalanceOperation | None:
        """Find an operation by idempotency key."""

    async def list_operations(
        self,
        client_id: uuid.UUID,
        limit: int,
    ) -> list[BalanceOperation]:
        """Return the most recent balance operations for a client."""

    async def apply_balance_operation(
        self,
        client: Client,
        operation: BalanceOperation,
    ) -> tuple[Client, BalanceOperation]:
        """Apply a balance operation atomically with its ledger record."""


class GuestRepository(typing.Protocol):
    async def get(self, guest_id: uuid.UUID) -> Guest | None:
        """Return a guest by ID."""

    async def list_guests(self) -> list[Guest]:
        """Return guests ordered for operator display."""

    async def search(self, query: str, field: str) -> list[Guest]:
        """Search guests by a normalized field."""

    async def save(self, guest: Guest) -> Guest:
        """Persist a guest profile."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
