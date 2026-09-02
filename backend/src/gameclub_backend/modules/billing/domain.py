import dataclasses
import datetime
import enum
import uuid


@dataclasses.dataclass(frozen=True)
class SessionCharge:
    id: uuid.UUID
    session_id: uuid.UUID
    client_id: uuid.UUID
    balance_operation_id: uuid.UUID
    tariff_id: uuid.UUID
    duration_minutes: int
    amount_cents: int
    amount_before_discount_cents: int
    discount_amount_cents: int
    discount_percent_bps: int
    discount_category: str | None
    charged_by: str
    idempotency_key: str
    created_at: datetime.datetime


@dataclasses.dataclass(frozen=True)
class RevenueSummary:
    start_at: datetime.datetime
    end_at: datetime.datetime
    amount_cents: int
    charge_count: int


class MeterStatus(enum.StrEnum):
    RUNNING = "running"
    EXHAUSTED = "exhausted"
    SETTLED = "settled"


@dataclasses.dataclass(frozen=True)
class SessionMeter:
    session_id: uuid.UUID
    client_id: uuid.UUID
    tariff_id: uuid.UUID
    billed_minutes: int
    billed_cents: int
    status: MeterStatus
    last_operation_id: uuid.UUID | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    package_minutes: int = 0
    active_entitlement_id: uuid.UUID | None = None

    def advance(
        self,
        billed_minutes: int,
        billed_cents: int,
        operation_id: uuid.UUID | None,
        now: datetime.datetime,
        status: MeterStatus | None = None,
        package_minutes: int | None = None,
        active_entitlement_id: uuid.UUID | None = None,
    ) -> "SessionMeter":
        if billed_minutes < self.billed_minutes or billed_cents < self.billed_cents:
            raise ValueError("Session meter cannot move backwards")
        next_package_minutes = self.package_minutes if package_minutes is None else package_minutes
        if next_package_minutes < 0:
            raise ValueError("Session package minutes cannot be negative")
        if next_package_minutes < self.package_minutes:
            raise ValueError("Session package minutes cannot move backwards")
        return dataclasses.replace(
            self,
            billed_minutes=billed_minutes,
            billed_cents=billed_cents,
            last_operation_id=operation_id or self.last_operation_id,
            status=status or self.status,
            updated_at=now,
            package_minutes=next_package_minutes,
            active_entitlement_id=active_entitlement_id,
        )


class ReconciliationStatus(enum.StrEnum):
    PENDING = "pending"
    RETRYABLE = "retryable"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


@dataclasses.dataclass(frozen=True)
class ChargeReconciliation:
    session_id: uuid.UUID
    idempotency_key: str
    charged_by: str
    status: ReconciliationStatus
    attempts: int
    next_attempt_at: datetime.datetime
    last_error: str | None
    charge_id: uuid.UUID | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    def schedule_retry(
        self,
        error: str,
        now: datetime.datetime,
    ) -> "ChargeReconciliation":
        attempt = self.attempts + 1
        delay_seconds = min(300, 2 ** min(attempt, 8))
        return dataclasses.replace(
            self,
            status=ReconciliationStatus.RETRYABLE,
            attempts=attempt,
            next_attempt_at=now + datetime.timedelta(seconds=delay_seconds),
            last_error=error[:1_000],
            updated_at=now,
        )

    def mark_needs_review(
        self,
        error: str,
        now: datetime.datetime,
    ) -> "ChargeReconciliation":
        return dataclasses.replace(
            self,
            status=ReconciliationStatus.NEEDS_REVIEW,
            last_error=error[:1_000],
            updated_at=now,
        )

    def mark_completed(
        self,
        charge_id: uuid.UUID,
        now: datetime.datetime,
    ) -> "ChargeReconciliation":
        return dataclasses.replace(
            self,
            status=ReconciliationStatus.COMPLETED,
            charge_id=charge_id,
            last_error=None,
            next_attempt_at=now,
            updated_at=now,
        )

    def is_due(self, now: datetime.datetime) -> bool:
        return (
            self.status
            in {
                ReconciliationStatus.PENDING,
                ReconciliationStatus.RETRYABLE,
            }
            and self.next_attempt_at <= now
        )
