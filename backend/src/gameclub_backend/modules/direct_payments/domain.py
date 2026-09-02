import dataclasses
import datetime
import enum
import uuid

from gameclub_backend.modules.payment_methods.domain import PaymentPart


class DirectPaymentStatus(enum.StrEnum):
    CONFIRMED = "confirmed"


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
        object.__setattr__(self, "guest_name", self.guest_name.strip())
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())
