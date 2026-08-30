import dataclasses
import datetime
import re
import uuid

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


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
