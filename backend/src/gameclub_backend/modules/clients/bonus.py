"""Exact bonus calculations; legacy Client.balance_bonus remains in whole units."""

import dataclasses
import enum


class BonusSource(enum.StrEnum):
    GAME = "game"
    PRODUCT = "product"


def _non_negative_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


@dataclasses.dataclass(frozen=True)
class BonusPayment:
    bonus_cents: int
    money_cents: int


@dataclasses.dataclass(frozen=True)
class BonusPolicy:
    """Rates use basis points: 500 means 5%; amounts use 0.01 bonus units."""

    enabled: bool = True
    game_rate_bps: int = 500
    product_rate_bps: int = 200
    payment_limit_bps: int = 2000

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("Enabled must be a boolean")
        for name in ("game_rate_bps", "product_rate_bps", "payment_limit_bps"):
            value = getattr(self, name)
            _non_negative_integer(value, name)
            if value > 10_000:
                raise ValueError(f"{name} cannot exceed 100%")

    def payment(
        self,
        price_cents: int,
        available_bonus_cents: int,
        balance_cents: int,
        *,
        use_bonus: bool,
    ) -> BonusPayment:
        """Quote a discounted game price; money/debt eligibility is checked by its owner."""
        _non_negative_integer(price_cents, "Price")
        _non_negative_integer(available_bonus_cents, "Available bonus")
        if isinstance(balance_cents, bool) or not isinstance(balance_cents, int):
            raise ValueError("Balance must be an integer")
        if not isinstance(use_bonus, bool):
            raise ValueError("Use bonus must be a boolean")
        bonus = 0
        if self.enabled and use_bonus and balance_cents >= 0:
            bonus = min(available_bonus_cents, price_cents * self.payment_limit_bps // 10_000)
        return BonusPayment(bonus, price_cents - bonus)

    def rate(self, source: BonusSource) -> int:
        if not isinstance(source, BonusSource):
            raise ValueError("Unknown bonus source")
        if not self.enabled:
            return 0
        return self.game_rate_bps if source is BonusSource.GAME else self.product_rate_bps


@dataclasses.dataclass(frozen=True)
class BonusAccrual:
    """Cumulative source amounts preserve sub-cent fractions across minute facts."""

    rate_bps: int
    money_cents: int = 0
    paid_cents: int = 0
    released_bonus_cents: int = 0

    def __post_init__(self) -> None:
        for name in ("rate_bps", "money_cents", "paid_cents", "released_bonus_cents"):
            _non_negative_integer(getattr(self, name), name)
        if self.rate_bps > 10_000:
            raise ValueError("Accrual rate cannot exceed 100%")
        if self.paid_cents > self.money_cents:
            raise ValueError("Paid amount cannot exceed the source money amount")
        if self.released_bonus_cents > self.paid_cents * self.rate_bps // 10_000:
            raise ValueError("Released bonus cannot exceed paid earnings")

    @property
    def earned_bonus_cents(self) -> int:
        return self.money_cents * self.rate_bps // 10_000

    @property
    def pending_bonus_cents(self) -> int:
        return self.earned_bonus_cents - self.released_bonus_cents

    def record(self, money_cents: int, paid_cents: int) -> "BonusAccrual":
        _non_negative_integer(money_cents, "Money")
        _non_negative_integer(paid_cents, "Paid")
        if paid_cents > money_cents:
            raise ValueError("Paid amount cannot exceed the source money amount")
        return dataclasses.replace(
            self,
            money_cents=self.money_cents + money_cents,
            paid_cents=self.paid_cents + paid_cents,
        )

    def repay(self, amount_cents: int) -> "BonusAccrual":
        """Apply the part assigned to this source by the oldest-debt-first allocator."""
        _non_negative_integer(amount_cents, "Repayment")
        return dataclasses.replace(self, paid_cents=self.paid_cents + amount_cents)

    def release(self, *, session_finished: bool) -> tuple["BonusAccrual", int]:
        if not isinstance(session_finished, bool):
            raise ValueError("Session finished must be a boolean")
        if not session_finished:
            return self, 0
        available = self.paid_cents * self.rate_bps // 10_000
        delta = available - self.released_bonus_cents
        return dataclasses.replace(self, released_bonus_cents=available), delta


class BonusOperationKind(enum.StrEnum):
    ADJUST = "adjust"
    DEBIT = "debit"
    RESERVE = "reserve"
    CONSUME = "consume"
    RELEASE = "release"


@dataclasses.dataclass(frozen=True)
class BonusWallet:
    total_cents: int
    reserved_cents: int = 0

    def __post_init__(self) -> None:
        _non_negative_integer(self.total_cents, "Bonus total")
        _non_negative_integer(self.reserved_cents, "Bonus reserve")
        if self.reserved_cents > self.total_cents:
            raise ValueError("Bonus reserve exceeds total")
        if self.total_cents > 9_223_372_036_854_775_807:
            raise ValueError("Bonus total exceeds storage limit")

    @property
    def available_cents(self) -> int:
        return self.total_cents - self.reserved_cents
