import dataclasses
import datetime
import re
import uuid
from collections.abc import Mapping, Sequence

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclasses.dataclass(frozen=True)
class PaymentPart:
    """A persisted part of a top-up or sale settlement."""

    method: str
    amount_cents: int
    reference: str | None = None

    def __post_init__(self) -> None:
        method = self.method.strip().lower()
        if not _KEY_PATTERN.fullmatch(method):
            raise ValueError("Payment part method is invalid")
        if (
            isinstance(self.amount_cents, bool)
            or not isinstance(self.amount_cents, int)
            or self.amount_cents <= 0
        ):
            raise ValueError("Payment part amount must be a positive integer")
        reference = self.reference.strip() if self.reference else None
        if reference is not None and len(reference) > 256:
            raise ValueError("Payment part reference is too long")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "reference", reference or None)

    def as_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "amount_cents": self.amount_cents,
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "PaymentPart":
        method = value.get("method")
        amount_cents = value.get("amount_cents")
        reference = value.get("reference")
        if not isinstance(method, str) or not isinstance(amount_cents, int):
            raise ValueError("Payment part must contain method and amount_cents")
        if reference is not None and not isinstance(reference, str):
            raise ValueError("Payment part reference must be a string")
        return cls(method, amount_cents, reference)


def normalize_payment_parts(
    parts: Sequence[PaymentPart | Mapping[str, object]] | None,
    total_cents: int,
) -> tuple[PaymentPart, ...]:
    if parts is None or not parts:
        return ()
    normalized = tuple(
        part if isinstance(part, PaymentPart) else PaymentPart.from_dict(part) for part in parts
    )
    if not normalized:
        raise ValueError("Payment parts cannot be empty")
    if total_cents <= 0 or sum(part.amount_cents for part in normalized) != total_cents:
        raise ValueError("Payment parts total must match the operation total")
    return normalized


@dataclasses.dataclass(frozen=True)
class PaymentMethod:
    id: uuid.UUID
    key: str
    name: str
    active: bool = True
    sort_order: int = 0
    created_at: datetime.datetime = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    updated_at: datetime.datetime = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    def __post_init__(self) -> None:
        key = self.key.strip().lower()
        name = self.name.strip()
        if not _KEY_PATTERN.fullmatch(key):
            raise ValueError(
                "Payment method key must contain lowercase latin letters, numbers, _ or -"
            )
        if not name or len(name) > 128:
            raise ValueError("Payment method name must contain from 1 to 128 characters")
        if isinstance(self.sort_order, bool) or not isinstance(self.sort_order, int):
            raise ValueError("Payment method sort order must be an integer")
        if self.sort_order < 0:
            raise ValueError("Payment method sort order cannot be negative")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "name", name)
