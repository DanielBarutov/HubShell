import dataclasses
import datetime
import typing
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.clients.bonus import (
    BonusOperationKind,
    BonusPolicy,
    BonusSource,
    BonusWallet,
)


@dataclasses.dataclass(frozen=True)
class BonusPurchaseConfirmation:
    price_cents: int
    bonus_cents: int
    money_cents: int
    earned_bonus_cents: int


@dataclasses.dataclass(frozen=True)
class BonusWalletSnapshot:
    total_cents: int
    available_cents: int
    reserved_cents: int
    pending_cents: int


@dataclasses.dataclass(frozen=True)
class BonusMinutePayment:
    client_id: uuid.UUID
    session_id: uuid.UUID
    operation_id: uuid.UUID
    occurred_at: datetime.datetime
    actor_id: str
    price_cents: int
    money_cents: int
    bonus_cents: int
    payment_limit_bps: int
    minimum_balance_cents: int

    def __post_init__(self) -> None:
        values = (
            self.price_cents,
            self.money_cents,
            self.bonus_cents,
            self.payment_limit_bps,
            self.minimum_balance_cents,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("Minute payment amounts must be integers")
        if (
            self.price_cents <= 0
            or self.money_cents < 0
            or self.bonus_cents < 0
            or self.money_cents != self.price_cents - self.bonus_cents
            or not 0 <= self.payment_limit_bps <= 10000
            or self.bonus_cents > self.price_cents * self.payment_limit_bps // 10000
        ):
            raise ValueError("Invalid minute bonus payment split")


class StaleBonusQuoteError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            ErrorCode.CONFLICT,
            "Расчёт покупки изменился. Проверьте суммы и подтвердите заново.",
        )


@dataclasses.dataclass(frozen=True)
class BonusCommand:
    client_id: uuid.UUID
    kind: BonusOperationKind
    amount_cents: int
    actor_id: str
    reason: str
    idempotency_key: str
    session_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BonusOperationKind):
            raise ValueError("Invalid bonus operation")
        if not isinstance(self.client_id, uuid.UUID):
            raise ValueError("Client id must be a UUID")
        if isinstance(self.amount_cents, bool) or not isinstance(self.amount_cents, int):
            raise ValueError("Bonus amount must be an integer")
        if abs(self.amount_cents) > 9_223_372_036_854_775_807:
            raise ValueError("Bonus amount exceeds storage limit")
        for name, limit in (("actor_id", 128), ("reason", 255), ("idempotency_key", 128)):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                raise ValueError(f"Invalid bonus {name}")
            object.__setattr__(self, name, value.strip())
        reserved_operation = self.kind in (
            BonusOperationKind.RESERVE,
            BonusOperationKind.CONSUME,
            BonusOperationKind.RELEASE,
        )
        if reserved_operation != (self.session_id is not None):
            raise ValueError("Session id is required only for reserved bonus operations")
        if self.session_id is not None and not isinstance(self.session_id, uuid.UUID):
            raise ValueError("Session id must be a UUID")
        if self.kind in (BonusOperationKind.RESERVE, BonusOperationKind.RELEASE):
            if self.amount_cents != 0:
                raise ValueError("Reserve/release operates on the entire available remainder")
        elif self.kind is BonusOperationKind.ADJUST:
            if self.amount_cents == 0:
                raise ValueError("Bonus adjustment cannot be zero")
        elif self.amount_cents <= 0:
            raise ValueError("Bonus spend must be positive")

    def apply(
        self, wallet: BonusWallet, session_reserved_cents: int, balance_cents: int
    ) -> tuple[BonusWallet, int]:
        total = wallet.total_cents
        reserved = wallet.reserved_cents
        held = session_reserved_cents
        if (
            self.kind
            in (BonusOperationKind.RESERVE, BonusOperationKind.DEBIT, BonusOperationKind.CONSUME)
            and balance_cents < 0
        ):
            raise ValueError("Bonus payment is unavailable with monetary debt")
        if self.kind is BonusOperationKind.ADJUST:
            total += self.amount_cents
        elif self.kind is BonusOperationKind.DEBIT:
            total -= self.amount_cents
        elif self.kind is BonusOperationKind.RESERVE:
            held += wallet.available_cents
            reserved += wallet.available_cents
        elif self.kind is BonusOperationKind.CONSUME:
            if self.amount_cents > held:
                raise ValueError("Insufficient session bonus reserve")
            held -= self.amount_cents
            reserved -= self.amount_cents
            total -= self.amount_cents
        elif self.kind is BonusOperationKind.RELEASE:
            reserved -= held
            held = 0
        return BonusWallet(total, reserved), held


@dataclasses.dataclass(frozen=True)
class BonusOperation:
    id: uuid.UUID
    command: BonusCommand
    wallet_after: BonusWallet
    session_reserved_after_cents: int
    total_delta_cents: int
    reserved_delta_cents: int
    created_at: datetime.datetime


@dataclasses.dataclass(frozen=True)
class BonusEarningCommand:
    """A confirmed source receipt, never a transport-supplied price or payment claim."""

    receipt_id: uuid.UUID
    client_id: uuid.UUID
    source_key: str
    source: BonusSource
    policy: BonusPolicy
    debit_operation_ids: tuple[uuid.UUID, ...] = ()
    external_paid_cents: int = 0
    session_id: uuid.UUID | None = None
    actor_id: str = "bonus-program"

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, uuid.UUID) or not isinstance(self.client_id, uuid.UUID):
            raise ValueError("Bonus receipt and client ids must be UUIDs")
        if not isinstance(self.source, BonusSource) or not isinstance(self.policy, BonusPolicy):
            raise ValueError("Invalid bonus source policy")
        if not isinstance(self.source_key, str) or not 1 <= len(self.source_key.strip()) <= 160:
            raise ValueError("Bonus source key is required")
        if not isinstance(self.actor_id, str) or not 1 <= len(self.actor_id.strip()) <= 128:
            raise ValueError("Bonus earning actor is required")
        if self.session_id is not None and not isinstance(self.session_id, uuid.UUID):
            raise ValueError("Bonus session id must be a UUID")
        if (
            isinstance(self.external_paid_cents, bool)
            or not isinstance(self.external_paid_cents, int)
            or self.external_paid_cents < 0
        ):
            raise ValueError("External bonus earning base must be a non-negative integer")
        ids = tuple(self.debit_operation_ids)
        if len(ids) != len(set(ids)) or any(not isinstance(item, uuid.UUID) for item in ids):
            raise ValueError("Bonus debit ids must be distinct UUIDs")
        object.__setattr__(self, "debit_operation_ids", ids)
        object.__setattr__(self, "source_key", self.source_key.strip())
        object.__setattr__(self, "actor_id", self.actor_id.strip())

    def payload(self) -> dict[str, object]:
        return {
            "client_id": str(self.client_id),
            "source_key": self.source_key,
            "source": self.source.value,
            "policy": dataclasses.asdict(self.policy),
            "debit_operation_ids": sorted(str(item) for item in self.debit_operation_ids),
            "external_paid_cents": self.external_paid_cents,
            "session_id": str(self.session_id) if self.session_id else None,
            "actor_id": self.actor_id,
        }


@dataclasses.dataclass(frozen=True)
class BonusDebt:
    operation_id: uuid.UUID
    client_id: uuid.UUID
    money_cents: int
    paid_cents: int
    created_at: datetime.datetime
    receipt_id: uuid.UUID | None = None
    source_key: str | None = None


class BonusEarningsPort(typing.Protocol):
    async def begin_bonus_session(self, client_id: uuid.UUID, session_id: uuid.UUID) -> BonusPolicy:
        """Capture settings for a newly opened session; preserve existing snapshots."""

    async def get_bonus_policy(
        self, client_id: uuid.UUID | None = None, session_id: uuid.UUID | None = None
    ) -> BonusPolicy:
        """Read club policy or the immutable policy of an authorized game session."""

    async def confirm_bonus_earning(self, command: BonusEarningCommand) -> None:
        """Confirm the earning only after the owning purchase has settled."""

    async def quote_bonus_game(
        self,
        client_id: uuid.UUID,
        price_cents: int,
        use_bonus: bool,
        session_id: uuid.UUID | None = None,
        *,
        include_session_reserved: bool = False,
    ) -> "BonusGameQuote":
        """Compute a server-owned split while retaining the purchase's client lock."""

    async def apply_bonus_operation(self, command: BonusCommand) -> BonusOperation:
        """Apply a validated game payment in the surrounding transaction."""

    async def finish_bonus_session(self, client_id: uuid.UUID, session_id: uuid.UUID) -> None:
        """Open the availability gate for confirmed session earnings."""


@dataclasses.dataclass(frozen=True)
class BonusPaymentState:
    balance_cents: int
    wallet: BonusWallet
    policy: BonusPolicy
    program_enabled: bool
    session_reserved_cents: int = 0
    session_minute_money_cents: int = 0


@dataclasses.dataclass(frozen=True)
class BonusGameQuote:
    earning_rate_bps: int
    price_cents: int
    bonus_cents: int
    money_cents: int
    earned_bonus_cents: int
    payment_limit_bps: int
    available_bonus_cents: int
    reserved_bonus_cents: int
    bonus_allowed: bool
    can_pay: bool
