import dataclasses
import datetime
import enum
import uuid

from gameclub_backend.modules.payment_methods.domain import PaymentPart


class DirectPaymentStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs_review"


@dataclasses.dataclass(frozen=True)
class GuestSessionPayment:
    id: uuid.UUID
    workstation_id: uuid.UUID
    tariff_id: uuid.UUID
    tariff_quantity: int
    guest_id: uuid.UUID | None
    guest_name: str
    total_price_cents: int
    payment_parts: tuple[PaymentPart, ...]
    cash_shift_id: uuid.UUID | None
    status: DirectPaymentStatus
    idempotency_key: str
    created_at: datetime.datetime
    created_by: str = ""
    attempts: int = 0
    next_attempt_at: datetime.datetime | None = None
    settlement_error: str | None = None

    def __post_init__(self) -> None:
        if not self.guest_name.strip():
            raise ValueError("Guest name is required")
        if self.tariff_quantity <= 0:
            raise ValueError("Tariff quantity must be positive")
        if self.total_price_cents <= 0:
            raise ValueError("Guest payment total must be positive")
        if not self.payment_parts:
            raise ValueError("Guest payment parts are required")
        if sum(part.amount_cents for part in self.payment_parts) != self.total_price_cents:
            raise ValueError("Guest payment parts total must match the payment total")
        if any(part.method != "cash" for part in self.payment_parts):
            raise ValueError("Guest direct payment provider is not configured")
        if self.cash_shift_id is None:
            raise ValueError("Guest cash payment requires a cash shift")
        if not self.idempotency_key.strip() or self.created_at.tzinfo is None:
            raise ValueError("Guest payment key and timestamp are required")
        if self.attempts < 0:
            raise ValueError("Guest payment attempts cannot be negative")
        next_attempt_at = self.next_attempt_at or self.created_at
        if next_attempt_at.tzinfo is None:
            raise ValueError("Guest payment retry timestamp must include timezone")
        object.__setattr__(self, "guest_name", self.guest_name.strip())
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())
        object.__setattr__(self, "created_by", self.created_by.strip() or "system")
        object.__setattr__(self, "next_attempt_at", next_attempt_at)

    def mark_confirmed(self, now: datetime.datetime) -> "GuestSessionPayment":
        if self.status is DirectPaymentStatus.CONFIRMED:
            return self
        if self.status not in {DirectPaymentStatus.PENDING, DirectPaymentStatus.NEEDS_REVIEW}:
            raise ValueError("Only a pending guest payment can be confirmed")
        return dataclasses.replace(
            self,
            status=DirectPaymentStatus.CONFIRMED,
            next_attempt_at=now,
            settlement_error=None,
        )

    def mark_needs_review(
        self,
        error: str,
        now: datetime.datetime | None = None,
    ) -> "GuestSessionPayment":
        normalized_error = error.strip()
        if not normalized_error:
            raise ValueError("Settlement review reason is required")
        if self.status is DirectPaymentStatus.CONFIRMED:
            return self
        return dataclasses.replace(
            self,
            status=DirectPaymentStatus.NEEDS_REVIEW,
            attempts=self.attempts + 1,
            next_attempt_at=now or self.next_attempt_at,
            settlement_error=normalized_error[:1_000],
        )

    def schedule_retry(self, error: str, now: datetime.datetime) -> "GuestSessionPayment":
        if now.tzinfo is None:
            raise ValueError("Guest payment retry time must include timezone")
        normalized_error = error.strip()
        if not normalized_error:
            raise ValueError("Guest payment retry reason is required")
        attempt = self.attempts + 1
        delay_seconds = min(300, 2 ** min(attempt, 8))
        return dataclasses.replace(
            self,
            status=DirectPaymentStatus.PENDING,
            attempts=attempt,
            next_attempt_at=now + datetime.timedelta(seconds=delay_seconds),
            settlement_error=normalized_error[:1_000],
        )

    def is_due(self, now: datetime.datetime) -> bool:
        return (
            self.status is DirectPaymentStatus.PENDING
            and self.next_attempt_at is not None
            and self.next_attempt_at <= now
        )

    def reopen_for_review(
        self,
        now: datetime.datetime | None = None,
    ) -> "GuestSessionPayment":
        if self.status is DirectPaymentStatus.CONFIRMED:
            return self
        if self.status is not DirectPaymentStatus.NEEDS_REVIEW:
            return self
        return dataclasses.replace(
            self,
            status=DirectPaymentStatus.PENDING,
            next_attempt_at=now or self.next_attempt_at,
            settlement_error=None,
        )
