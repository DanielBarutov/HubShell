import datetime
import typing
import uuid

from gameclub_backend.modules.clients.application.bonus import (
    BonusCommand,
    BonusEarningCommand,
    BonusMinutePayment,
    BonusOperation,
    BonusPaymentState,
)
from gameclub_backend.modules.clients.application.bonus_reporting import BonusReport
from gameclub_backend.modules.clients.bonus import BonusPolicy, BonusWallet
from gameclub_backend.modules.clients.domain import BalanceOperation, Client, Guest


class ClientRepository(typing.Protocol):
    async def read_bonus_report(
        self, start_at: datetime.datetime, end_at: datetime.datetime
    ) -> BonusReport:
        """Read period journal flows and a consistent current wallet snapshot for the club."""

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

    async def consume_password_reset_login(
        self,
        client_id: uuid.UUID,
        now: datetime.datetime,
    ) -> Client:
        """Atomically consume the one-time passwordless reset login."""

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
        minimum_balance_cents: int = 0,
    ) -> tuple[Client, BalanceOperation]:
        """Apply a balance operation atomically with its ledger record."""

    async def get_bonus_wallet(self, client_id: uuid.UUID) -> BonusWallet:
        """Read exact bonus amounts without changing the wallet."""

    async def apply_bonus_operation(
        self, command: BonusCommand, now: datetime.datetime
    ) -> BonusOperation:
        """Atomically update wallet, reservation, legacy projection and journal."""

    async def list_bonus_operations(
        self, client_id: uuid.UUID, limit: int = 100
    ) -> list[BonusOperation]:
        """Return the latest immutable bonus journal entries."""

    async def begin_bonus_session(self, client_id: uuid.UUID, session_id: uuid.UUID) -> BonusPolicy:
        """Capture current settings only when Sessions opens a new session."""

    async def get_bonus_policy(
        self, client_id: uuid.UUID | None = None, session_id: uuid.UUID | None = None
    ) -> BonusPolicy:
        """Read current policy or freeze the policy for an authorized session."""

    async def update_bonus_policy(
        self, policy: BonusPolicy, actor_id: str, idempotency_key: str, now: datetime.datetime
    ) -> BonusPolicy:
        """Persist audited program settings without changing existing session snapshots."""

    async def confirm_bonus_earning(
        self, command: BonusEarningCommand, now: datetime.datetime
    ) -> None:
        """Attach a confirmed source to its monetary debits and external settled payments."""

    async def finish_bonus_session(
        self, client_id: uuid.UUID, session_id: uuid.UUID, now: datetime.datetime
    ) -> None:
        """Release only confirmed and paid session earnings."""

    async def get_pending_bonus_cents(self, client_id: uuid.UUID) -> int:
        """Read confirmed earnings still waiting for payment or session completion."""

    async def get_bonus_payment_state(
        self, client_id: uuid.UUID, session_id: uuid.UUID | None = None
    ) -> BonusPaymentState:
        """Lock a client's payment state until the surrounding purchase transaction ends."""


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


class ClientBalanceTransactionWriter(typing.Protocol):
    async def apply_bonus_minute(
        self, transaction: typing.Any, payment: "BonusMinutePayment"
    ) -> bool:
        """Validate the reserved split and apply both parts atomically."""

    async def release_bonus_reservation(
        self,
        transaction: typing.Any,
        client_id: uuid.UUID,
        session_id: uuid.UUID,
        operation_id: uuid.UUID,
        now: datetime.datetime,
    ) -> None:
        """Release only after all preceding local facts were confirmed."""

    async def apply(
        self,
        transaction: typing.Any,
        operation: BalanceOperation,
        minimum_balance_cents: int = 0,
        *,
        accepted_at: datetime.datetime | None = None,
    ) -> Client | None:
        """Apply a validated financial fact in the transaction owned by its orchestrator."""

    async def confirm_minute(
        self,
        transaction: typing.Any,
        client_id: uuid.UUID,
        session_id: uuid.UUID,
        operation_id: uuid.UUID,
        receipt_id: uuid.UUID,
        actor_id: str,
        now: datetime.datetime,
    ) -> None:
        """Attach a confirmed minute to its frozen session policy and monetary debit."""

    async def finish_session(
        self,
        transaction: typing.Any,
        client_id: uuid.UUID,
        session_id: uuid.UUID,
        now: datetime.datetime,
    ) -> None:
        """Release confirmed earnings and unused reserve after the ordered stop fact."""
