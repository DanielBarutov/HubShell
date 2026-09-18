from __future__ import annotations

import dataclasses
import datetime


@dataclasses.dataclass(frozen=True)
class ClientGroup:
    id: str
    name: str
    allow_negative_balance: bool = False
    negative_balance_limit_cents: int = 0
    active: bool = True
    is_default: bool = False
    updated_at: datetime.datetime | None = None

    def __post_init__(self) -> None:
        normalized_id = self.id.strip().lower()
        normalized_name = self.name.strip()
        if not normalized_id or len(normalized_id) > 128:
            raise ValueError("Client group id is required")
        if not normalized_name or len(normalized_name) > 128:
            raise ValueError("Client group name is required")
        if self.negative_balance_limit_cents < 0:
            raise ValueError("Negative balance limit cannot be negative")
        if not self.allow_negative_balance and self.negative_balance_limit_cents:
            raise ValueError("Negative balance limit requires negative balance permission")
        object.__setattr__(self, "id", normalized_id)
        object.__setattr__(self, "name", normalized_name)

    @property
    def minimum_balance_cents(self) -> int:
        return -self.negative_balance_limit_cents if self.allow_negative_balance else 0
