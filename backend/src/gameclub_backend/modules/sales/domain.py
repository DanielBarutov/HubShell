import dataclasses
import datetime
import enum
import uuid


class ProductSaleStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProductPaymentMethod(enum.StrEnum):
    BALANCE = "balance"
    CASH = "cash"


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
        if not self.sold_by.strip() or not self.idempotency_key.strip():
            raise ValueError("Product sale author and idempotency key are required")

    def complete(self, now: datetime.datetime) -> "ProductSale":
        if self.status is ProductSaleStatus.CANCELLED:
            raise ValueError("Cancelled sale cannot be completed")
        return dataclasses.replace(
            self,
            status=ProductSaleStatus.COMPLETED,
            completed_at=now,
        )

    def cancel(self) -> "ProductSale":
        if self.status is ProductSaleStatus.COMPLETED:
            raise ValueError("Completed sale cannot be cancelled in this flow")
        return dataclasses.replace(self, status=ProductSaleStatus.CANCELLED)
