import dataclasses
import datetime
import enum
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from gameclub_backend.modules.catalog.domain import TariffAudience


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
    time_restricted: bool = False
    sale_window_start_minute: int | None = None
    sale_window_end_minute: int | None = None
    usage_window_start_minute: int | None = None
    usage_window_end_minute: int | None = None
    window_timezone: str | None = None
    audience: TariffAudience = TariffAudience.ALL

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
        try:
            normalized_audience = TariffAudience(self.audience)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid entitlement audience") from error
        object.__setattr__(self, "audience", normalized_audience)
        sale_window_set = (
            self.sale_window_start_minute is not None or self.sale_window_end_minute is not None
        )
        usage_window_set = (
            self.usage_window_start_minute is not None or self.usage_window_end_minute is not None
        )
        if not self.time_restricted and (
            sale_window_set or usage_window_set or self.window_timezone
        ):
            raise ValueError("Unrestricted entitlement cannot have time windows")
        if self.time_restricted and not (sale_window_set and usage_window_set):
            raise ValueError("Restricted entitlement requires sale and usage windows")
        self._validate_window(
            self.sale_window_start_minute,
            self.sale_window_end_minute,
            "sale",
        )
        self._validate_window(
            self.usage_window_start_minute,
            self.usage_window_end_minute,
            "usage",
        )
        if self.time_restricted and not self.window_timezone:
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

    @staticmethod
    def _validate_window(
        start_minute: int | None,
        end_minute: int | None,
        name: str,
    ) -> None:
        if (start_minute is None) != (end_minute is None):
            raise ValueError(f"Entitlement {name} window requires both start and end")
        if start_minute is not None:
            assert end_minute is not None
            if not (
                0 <= start_minute < 24 * 60
                and 0 <= end_minute < 24 * 60
                and start_minute != end_minute
            ):
                raise ValueError(f"Entitlement {name} window minutes are invalid")

    def is_compatible(self, zone_id: str | None) -> bool:
        return self.zone_id is None or self.zone_id == (zone_id.strip() if zone_id else None)

    def is_available_at(self, now: datetime.datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("Entitlement availability time must include timezone")
        if not self.time_restricted:
            return True
        local = now.astimezone(ZoneInfo(self.window_timezone or "UTC"))
        minute = local.hour * 60 + local.minute
        start = self.usage_window_start_minute
        end = self.usage_window_end_minute
        assert start is not None and end is not None
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
