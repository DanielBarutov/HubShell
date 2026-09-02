import dataclasses
import datetime
import enum
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class EntitlementStatus(enum.StrEnum):
    QUEUED = "queued"
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    BURNED = "burned"


@dataclasses.dataclass(frozen=True)
class Entitlement:
    id: uuid.UUID
    client_id: uuid.UUID
    tariff_id: uuid.UUID
    zone_id: str | None
    duration_minutes: int
    remaining_minutes: int
    price_cents: int
    queue_position: int
    status: EntitlementStatus
    idempotency_key: str
    purchased_at: datetime.datetime
    activated_at: datetime.datetime | None = None
    ended_at: datetime.datetime | None = None
    burn_reason: str | None = None
    window_start_minute: int | None = None
    window_end_minute: int | None = None
    window_timezone: str | None = None

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0:
            raise ValueError("Entitlement duration must be positive")
        if not 0 <= self.remaining_minutes <= self.duration_minutes:
            raise ValueError("Entitlement remaining minutes are invalid")
        if self.price_cents < 0:
            raise ValueError("Entitlement price cannot be negative")
        if self.queue_position <= 0:
            raise ValueError("Entitlement queue position must be positive")
        if not self.idempotency_key.strip():
            raise ValueError("Entitlement idempotency key is required")
        if self.purchased_at.tzinfo is None:
            raise ValueError("Entitlement purchase time must include timezone")
        if (self.window_start_minute is None) != (self.window_end_minute is None):
            raise ValueError("Entitlement time window requires both start and end")
        if self.window_start_minute is not None and not (
            0 <= self.window_start_minute < 24 * 60
            and 0 <= self.window_end_minute < 24 * 60
            and self.window_start_minute != self.window_end_minute
        ):
            raise ValueError("Entitlement time window minutes are invalid")
        if self.window_start_minute is not None and not self.window_timezone:
            raise ValueError("Entitlement time window timezone is required")
        if self.window_timezone:
            try:
                ZoneInfo(self.window_timezone.strip())
            except ZoneInfoNotFoundError as error:
                raise ValueError("Entitlement time window timezone is invalid") from error
            object.__setattr__(self, "window_timezone", self.window_timezone.strip())
        if self.zone_id is not None:
            zone_id = self.zone_id.strip()
            object.__setattr__(self, "zone_id", zone_id or None)
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())

    def is_compatible(self, zone_id: str | None) -> bool:
        return self.zone_id is None or self.zone_id == (zone_id.strip() if zone_id else None)

    def is_available_at(self, now: datetime.datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("Entitlement availability time must include timezone")
        if self.window_start_minute is None:
            return True
        local = now.astimezone(ZoneInfo(self.window_timezone or "UTC"))
        minute = local.hour * 60 + local.minute
        start = self.window_start_minute
        end = self.window_end_minute
        if start < end:
            return start <= minute < end
        return minute >= start or minute < end

    def activate(self, now: datetime.datetime) -> "Entitlement":
        if now.tzinfo is None:
            raise ValueError("Entitlement activation time must include timezone")
        if self.status is EntitlementStatus.ACTIVE:
            return self
        if self.status is not EntitlementStatus.QUEUED:
            raise ValueError("Only a queued entitlement can be activated")
        if self.remaining_minutes <= 0:
            raise ValueError("Exhausted entitlement cannot be activated")
        return dataclasses.replace(self, status=EntitlementStatus.ACTIVE, activated_at=now)

    def consume(self, minutes: int, now: datetime.datetime) -> "Entitlement":
        if minutes <= 0:
            raise ValueError("Consumed minutes must be positive")
        if now.tzinfo is None:
            raise ValueError("Entitlement consumption time must include timezone")
        if self.status is not EntitlementStatus.ACTIVE:
            raise ValueError("Only an active entitlement can be consumed")
        remaining = max(0, self.remaining_minutes - minutes)
        return dataclasses.replace(
            self,
            remaining_minutes=remaining,
            status=EntitlementStatus.EXHAUSTED if remaining == 0 else EntitlementStatus.ACTIVE,
            ended_at=now if remaining == 0 else self.ended_at,
        )

    def burn(self, reason: str, now: datetime.datetime) -> "Entitlement":
        normalized_reason = reason.strip()
        if not normalized_reason or now.tzinfo is None:
            raise ValueError("Burn reason and time are required")
        if self.status in {EntitlementStatus.EXHAUSTED, EntitlementStatus.BURNED}:
            return self
        return dataclasses.replace(
            self,
            status=EntitlementStatus.BURNED,
            ended_at=now,
            burn_reason=normalized_reason[:256],
        )
