import dataclasses
import datetime
import enum
import uuid

from gameclub_backend.modules.payment_methods.domain import PaymentPart


class ProductSaleStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"


class ProductPaymentMethod(enum.StrEnum):
    BALANCE = "balance"
    CASH = "cash"
    MIXED = "mixed"


@dataclasses.dataclass(frozen=True)
class ProductSale:
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    client_id: uuid.UUID | None
    guest_name: str | None
    quantity: int
    unit_price_cents: int
    unit_cost_price_cents: int
    total_price_cents: int
    total_cost_price_cents: int
    payment_method: ProductPaymentMethod
    cash_shift_id: uuid.UUID | None
    status: ProductSaleStatus
    sold_by: str
    idempotency_key: str
    created_at: datetime.datetime
    completed_at: datetime.datetime | None = None
    product_category: str = ""
    payment_parts: tuple[PaymentPart, ...] = ()
    settlement_error: str | None = None
    attempts: int = 0
    next_attempt_at: datetime.datetime | None = None

    def __post_init__(self) -> None:
        if not self.product_name.strip():
            raise ValueError("Product sale name is required")
        if self.quantity <= 0:
            raise ValueError("Product sale quantity must be positive")
        if (
            min(
                self.unit_price_cents,
                self.unit_cost_price_cents,
                self.total_price_cents,
                self.total_cost_price_cents,
            )
            < 0
        ):
            raise ValueError("Product sale money must be non-negative")
        if self.total_price_cents != self.unit_price_cents * self.quantity:
            raise ValueError("Product sale total does not match quantity")
        if self.total_cost_price_cents != self.unit_cost_price_cents * self.quantity:
            raise ValueError("Product sale cost total does not match quantity")
        if self.client_id is None and (self.guest_name or "").strip() != "Гость":
            raise ValueError("Guest sale must be named Гость")
        if self.client_id is not None and self.guest_name is not None:
            raise ValueError("Client and guest cannot be used together")
        if self.payment_method is ProductPaymentMethod.BALANCE and self.client_id is None:
            raise ValueError("Balance payment requires a client")
        if self.payment_method is ProductPaymentMethod.CASH and self.cash_shift_id is None:
            raise ValueError("Cash payment requires a cash shift")
        parts = tuple(self.payment_parts)
        if parts and sum(part.amount_cents for part in parts) != self.total_price_cents:
            raise ValueError("Payment parts total must match the sale total")
        if self.payment_method is ProductPaymentMethod.MIXED and len(parts) < 2:
            raise ValueError("Mixed payment requires at least two payment parts")
        if self.payment_method is not ProductPaymentMethod.MIXED and len(parts) > 1:
            raise ValueError("Multiple payment parts require mixed payment")
        if not self.sold_by.strip() or not self.idempotency_key.strip():
            raise ValueError("Product sale author and idempotency key are required")
        if self.attempts < 0:
            raise ValueError("Product sale attempts cannot be negative")
        next_attempt_at = self.next_attempt_at or self.created_at
        if next_attempt_at.tzinfo is None:
            raise ValueError("Product sale retry timestamp must include timezone")
        object.__setattr__(self, "payment_parts", parts)
        object.__setattr__(self, "next_attempt_at", next_attempt_at)

    def complete(self, now: datetime.datetime) -> "ProductSale":
        if self.status is not ProductSaleStatus.PENDING:
            raise ValueError("Only a pending sale can be completed")
        return dataclasses.replace(
            self,
            status=ProductSaleStatus.COMPLETED,
            completed_at=now,
            settlement_error=None,
            next_attempt_at=now,
        )

    def needs_review(
        self,
        error: str,
        now: datetime.datetime | None = None,
    ) -> "ProductSale":
        if self.status is ProductSaleStatus.COMPLETED:
            return self
        normalized_error = error.strip()
        if not normalized_error:
            raise ValueError("Settlement review reason is required")
        return dataclasses.replace(
            self,
            status=ProductSaleStatus.NEEDS_REVIEW,
            settlement_error=normalized_error[:1_000],
            attempts=self.attempts + 1,
            next_attempt_at=now or self.next_attempt_at,
        )

    def schedule_retry(self, error: str, now: datetime.datetime) -> "ProductSale":
        if now.tzinfo is None:
            raise ValueError("Product sale retry time must include timezone")
        normalized_error = error.strip()
        if not normalized_error:
            raise ValueError("Product sale retry reason is required")
        attempt = self.attempts + 1
        delay_seconds = min(300, 2 ** min(attempt, 8))
        return dataclasses.replace(
            self,
            status=ProductSaleStatus.PENDING,
            attempts=attempt,
            next_attempt_at=now + datetime.timedelta(seconds=delay_seconds),
            settlement_error=normalized_error[:1_000],
        )

    def is_due(self, now: datetime.datetime) -> bool:
        return (
            self.status is ProductSaleStatus.PENDING
            and self.next_attempt_at is not None
            and self.next_attempt_at <= now
        )

    def reopen_for_review(
        self,
        now: datetime.datetime | None = None,
    ) -> "ProductSale":
        if self.status is ProductSaleStatus.COMPLETED:
            return self
        if self.status is not ProductSaleStatus.NEEDS_REVIEW:
            return self
        return dataclasses.replace(
            self,
            status=ProductSaleStatus.PENDING,
            settlement_error=None,
            next_attempt_at=now or self.created_at,
        )

    def cancel(self) -> "ProductSale":
        if self.status is ProductSaleStatus.COMPLETED:
            raise ValueError("Completed sale cannot be cancelled in this flow")
        return dataclasses.replace(self, status=ProductSaleStatus.CANCELLED)
