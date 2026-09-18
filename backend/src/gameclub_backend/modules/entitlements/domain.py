import dataclasses
import datetime
import enum
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from gameclub_backend.modules.catalog.domain import TariffAudience
from gameclub_backend.modules.payment_methods.domain import PaymentPart


class EntitlementStatus(enum.StrEnum):
    QUEUED = "queued"
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    BURNED = "burned"


class EntitlementSettlementStatus(enum.StrEnum):
    PENDING = "pending"
    SETTLED = "settled"
    NEEDS_REVIEW = "needs_review"


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
    payment_parts: tuple[PaymentPart, ...] = ()
    cash_shift_id: uuid.UUID | None = None
    settlement_status: EntitlementSettlementStatus = EntitlementSettlementStatus.SETTLED
    settlement_error: str | None = None
    settlement_attempts: int = 0
    next_settlement_attempt_at: datetime.datetime | None = None

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0:
            raise ValueError("Entitlement duration must be positive")
        if not 0 <= self.remaining_minutes <= self.duration_minutes:
            raise ValueError("Entitlement remaining minutes are invalid")
        if self.price_cents < 0:
            raise ValueError("Entitlement price cannot be negative")
        parts = tuple(self.payment_parts)
        if parts and sum(part.amount_cents for part in parts) != self.price_cents:
            raise ValueError("Payment parts total must match entitlement price")
        if any(part.method not in {"balance", "cash", "transfer"} for part in parts):
            raise ValueError("Unsupported entitlement payment method")
        if any(part.method == "cash" for part in parts) and self.cash_shift_id is None:
            raise ValueError("Cash entitlement payment requires a cash shift")
        try:
            settlement_status = EntitlementSettlementStatus(self.settlement_status)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid entitlement settlement status") from error
        if self.settlement_attempts < 0:
            raise ValueError("Entitlement settlement attempts cannot be negative")
        next_attempt_at = self.next_settlement_attempt_at or self.purchased_at
        if next_attempt_at.tzinfo is None:
            raise ValueError("Entitlement settlement retry timestamp must include timezone")
        if self.settlement_error is not None and not self.settlement_error.strip():
            raise ValueError("Entitlement settlement error cannot be empty")
        object.__setattr__(self, "payment_parts", parts)
        object.__setattr__(self, "settlement_status", settlement_status)
        object.__setattr__(self, "next_settlement_attempt_at", next_attempt_at)
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

    def usage_window_ends_at(self, now: datetime.datetime) -> datetime.datetime | None:
        """Return the next closing moment of the active local usage window."""
        if not self.time_restricted or not self.is_available_at(now):
            return None
        timezone = ZoneInfo(self.window_timezone or "UTC")
        local = now.astimezone(timezone)
        start = self.usage_window_start_minute
        end = self.usage_window_end_minute
        assert start is not None and end is not None
        local_end_date = local.date()
        minute = local.hour * 60 + local.minute
        if start > end and minute >= start:
            local_end_date += datetime.timedelta(days=1)
        local_end = datetime.datetime.combine(
            local_end_date,
            datetime.time(hour=end // 60, minute=end % 60),
            tzinfo=timezone,
        )
        return local_end.astimezone(datetime.UTC)

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

    def mark_settled(self, now: datetime.datetime) -> "Entitlement":
        if now.tzinfo is None:
            raise ValueError("Entitlement settlement time must include timezone")
        if self.settlement_status is EntitlementSettlementStatus.SETTLED:
            return self
        return dataclasses.replace(
            self,
            settlement_status=EntitlementSettlementStatus.SETTLED,
            settlement_error=None,
            next_settlement_attempt_at=now,
        )

    def mark_needs_review(
        self,
        error: str,
        now: datetime.datetime | None = None,
    ) -> "Entitlement":
        normalized_error = error.strip()
        if not normalized_error:
            raise ValueError("Entitlement settlement review reason is required")
        return dataclasses.replace(
            self,
            settlement_status=EntitlementSettlementStatus.NEEDS_REVIEW,
            settlement_error=normalized_error[:1_000],
            settlement_attempts=self.settlement_attempts + 1,
            next_settlement_attempt_at=now or self.next_settlement_attempt_at,
        )

    def schedule_settlement_retry(
        self,
        error: str,
        now: datetime.datetime,
    ) -> "Entitlement":
        if now.tzinfo is None:
            raise ValueError("Entitlement settlement retry time must include timezone")
        normalized_error = error.strip()
        if not normalized_error:
            raise ValueError("Entitlement settlement retry reason is required")
        attempt = self.settlement_attempts + 1
        delay_seconds = min(300, 2 ** min(attempt, 8))
        return dataclasses.replace(
            self,
            settlement_status=EntitlementSettlementStatus.PENDING,
            settlement_error=normalized_error[:1_000],
            settlement_attempts=attempt,
            next_settlement_attempt_at=now + datetime.timedelta(seconds=delay_seconds),
        )

    def is_settlement_due(self, now: datetime.datetime) -> bool:
        return (
            self.settlement_status is EntitlementSettlementStatus.PENDING
            and self.next_settlement_attempt_at is not None
            and self.next_settlement_attempt_at <= now
        )

    def reopen_settlement_for_review(
        self,
        now: datetime.datetime | None = None,
    ) -> "Entitlement":
        if self.settlement_status is EntitlementSettlementStatus.SETTLED:
            return self
        if self.settlement_status is not EntitlementSettlementStatus.NEEDS_REVIEW:
            return self
        return dataclasses.replace(
            self,
            settlement_status=EntitlementSettlementStatus.PENDING,
            settlement_error=None,
            next_settlement_attempt_at=now or self.next_settlement_attempt_at,
        )
