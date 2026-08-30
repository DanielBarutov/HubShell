import dataclasses
import datetime
import enum
import uuid


def normalize_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 10:
        digits = "7" + digits
    if digits.startswith("8") and len(digits) <= 11:
        digits = "7" + digits[1:]
    return digits


@dataclasses.dataclass(frozen=True)
class Nickname:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not 3 <= len(normalized) <= 64:
            raise ValueError("Nickname must contain from 3 to 64 characters")
        object.__setattr__(self, "value", normalized)


@dataclasses.dataclass(frozen=True)
class PhoneNumber:
    value: str

    def __post_init__(self) -> None:
        normalized = normalize_phone(self.value)
        if len(normalized) != 11 or not normalized.startswith("7"):
            raise ValueError("Phone must be a Russian number in the 11-digit format")
        object.__setattr__(self, "value", normalized)


@dataclasses.dataclass(frozen=True)
class Money:
    cents: int

    def __post_init__(self) -> None:
        if isinstance(self.cents, bool) or not isinstance(self.cents, int) or self.cents < 0:
            raise ValueError("Money must be a non-negative integer")

    def add(self, other: "Money") -> "Money":
        return Money(self.cents + other.cents)

    def subtract(self, other: "Money") -> "Money":
        if other.cents > self.cents:
            raise ValueError("Insufficient balance")
        return Money(self.cents - other.cents)


@dataclasses.dataclass(frozen=True)
class Bonus:
    units: int

    def __post_init__(self) -> None:
        if isinstance(self.units, bool) or not isinstance(self.units, int) or self.units < 0:
            raise ValueError("Bonus must be a non-negative integer")

    def add(self, other: "Bonus") -> "Bonus":
        return Bonus(self.units + other.units)


class BalanceOperationType(enum.StrEnum):
    TOP_UP = "top_up"
    DEBIT = "debit"


@dataclasses.dataclass(frozen=True)
class BalanceOperation:
    id: uuid.UUID
    client_id: uuid.UUID
    amount_cents: int
    bonus_amount: int
    reason: str
    actor_id: str
    idempotency_key: str
    created_at: datetime.datetime
    operation_type: BalanceOperationType = BalanceOperationType.TOP_UP

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("Balance operation reason is required")
        if not self.actor_id.strip():
            raise ValueError("Balance operation actor is required")
        if not self.idempotency_key.strip():
            raise ValueError("Balance operation idempotency key is required")
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "actor_id", self.actor_id.strip())
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())


@dataclasses.dataclass(frozen=True)
class Client:
    id: uuid.UUID
    nickname: str
    phone: str | None
    discount_category: str | None
    balance_cents: int
    balance_bonus: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    blocked_at: datetime.datetime | None = None
    password_hash: str | None = None

    def __post_init__(self) -> None:
        Money(self.balance_cents)
        Bonus(self.balance_bonus)

    def top_up(
        self,
        amount_cents: int,
        bonus_amount: int,
        now: datetime.datetime,
    ) -> "Client":
        amount = Money(amount_cents)
        bonus = Bonus(bonus_amount)
        if amount.cents == 0 and bonus.units == 0:
            raise ValueError("Top-up must contain a positive amount or bonus")
        balance = Money(self.balance_cents).add(amount)
        next_bonus = Bonus(self.balance_bonus).add(bonus)
        return dataclasses.replace(
            self,
            balance_cents=balance.cents,
            balance_bonus=next_bonus.units,
            updated_at=now,
        )

    def debit(self, amount_cents: int, now: datetime.datetime) -> "Client":
        if amount_cents <= 0:
            raise ValueError("Debit amount must be positive")
        balance = Money(self.balance_cents).subtract(Money(amount_cents))
        return dataclasses.replace(
            self,
            balance_cents=balance.cents,
            updated_at=now,
        )


@dataclasses.dataclass(frozen=True)
class Guest:
    """A lightweight club visitor identity without a balance ledger."""

    id: uuid.UUID
    nickname: str
    phone: str | None
    discount_category: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    def __post_init__(self) -> None:
        nickname = Nickname(self.nickname).value
        phone = PhoneNumber(self.phone).value if self.phone else None
        discount_category = self.discount_category.strip() if self.discount_category else None
        object.__setattr__(self, "nickname", nickname)
        object.__setattr__(self, "phone", phone or None)
        object.__setattr__(self, "discount_category", discount_category or None)
