import dataclasses
import datetime
import enum
import uuid


@dataclasses.dataclass(frozen=True)
class CashShiftSchedule:
    register_id: str
    timezone: str = "Europe/Moscow"
    auto_open: bool = False
    auto_open_at: datetime.time | None = None
    auto_close: bool = False
    auto_close_at: datetime.time | None = None
    opening_balance_cents: int = 0

    def __post_init__(self) -> None:
        if not self.register_id.strip():
            raise ValueError("Register id is required")
        if self.opening_balance_cents < 0:
            raise ValueError("Opening balance cannot be negative")
        if self.auto_open and self.auto_open_at is None:
            raise ValueError("Auto-open time is required")
        if self.auto_close and self.auto_close_at is None:
            raise ValueError("Auto-close time is required")


@dataclasses.dataclass(frozen=True)
class CashReference:
    reference_type: str
    reference_id: str

    def __post_init__(self) -> None:
        reference_type = self.reference_type.strip()
        reference_id = self.reference_id.strip()
        if not reference_type or not reference_id:
            raise ValueError("Cash reference type and ID must be provided together")
        if len(reference_type) > 64 or len(reference_id) > 128:
            raise ValueError("Cash reference is too long")
        object.__setattr__(self, "reference_type", reference_type)
        object.__setattr__(self, "reference_id", reference_id)


def normalize_cash_reference(
    reference_type: str | None,
    reference_id: str | None,
) -> CashReference | None:
    if reference_type is None and reference_id is None:
        return None
    if reference_type is None or reference_id is None:
        raise ValueError("Cash reference type and ID must be provided together")
    return CashReference(reference_type, reference_id)


@dataclasses.dataclass(frozen=True)
class CashAmount:
    cents: int

    def __post_init__(self) -> None:
        if isinstance(self.cents, bool) or not isinstance(self.cents, int) or self.cents < 0:
            raise ValueError("Cash amount must be a non-negative integer")


class CashShiftStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CashMovementDirection(enum.StrEnum):
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    CORRECTION = "correction"


class CashApprovalKind(enum.StrEnum):
    CORRECTION = "correction"
    CLOSE_DIFFERENCE = "close_difference"


@dataclasses.dataclass(frozen=True)
class CashApproval:
    id: uuid.UUID
    shift_id: uuid.UUID
    kind: CashApprovalKind
    target_key: str
    approved_by: str
    reason: str
    idempotency_key: str
    created_at: datetime.datetime

    def __post_init__(self) -> None:
        if not self.target_key.strip():
            raise ValueError("Approval target key is required")
        if not self.approved_by.strip():
            raise ValueError("Approval actor is required")
        if not self.reason.strip():
            raise ValueError("Approval reason is required")
        if not self.idempotency_key.strip():
            raise ValueError("Approval idempotency key is required")
        object.__setattr__(self, "target_key", self.target_key.strip())
        object.__setattr__(self, "approved_by", self.approved_by.strip())
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())


@dataclasses.dataclass(frozen=True)
class CashMovement:
    id: uuid.UUID
    shift_id: uuid.UUID
    direction: CashMovementDirection
    amount_cents: int
    reason: str
    actor_id: str
    idempotency_key: str
    created_at: datetime.datetime
    reference_type: str | None = None
    reference_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.amount_cents, int) or isinstance(self.amount_cents, bool):
            raise ValueError("Cash movement amount must be an integer")
        if self.direction in {
            CashMovementDirection.CASH_IN,
            CashMovementDirection.CASH_OUT,
        }:
            CashAmount(self.amount_cents)
            if self.amount_cents == 0:
                raise ValueError("Cash movement amount must be positive")
        elif self.amount_cents == 0:
            raise ValueError("Correction amount must not be zero")
        if not self.reason.strip():
            raise ValueError("Cash movement reason is required")
        if not self.actor_id.strip():
            raise ValueError("Cash movement actor is required")
        if not self.idempotency_key.strip():
            raise ValueError("Cash movement idempotency key is required")
        reference = normalize_cash_reference(self.reference_type, self.reference_id)
        object.__setattr__(self, "reason", self.reason.strip())
        object.__setattr__(self, "actor_id", self.actor_id.strip())
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())
        object.__setattr__(
            self,
            "reference_type",
            reference.reference_type if reference else None,
        )
        object.__setattr__(
            self,
            "reference_id",
            reference.reference_id if reference else None,
        )

    @property
    def delta_cents(self) -> int:
        if self.direction is CashMovementDirection.CASH_IN:
            return self.amount_cents
        if self.direction is CashMovementDirection.CASH_OUT:
            return -self.amount_cents
        return self.amount_cents


@dataclasses.dataclass(frozen=True)
class CashShift:
    id: uuid.UUID
    register_id: str
    opened_by: str
    opened_at: datetime.datetime
    opening_balance_cents: int
    expected_close_cents: int
    status: CashShiftStatus
    open_idempotency_key: str
    closed_by: str | None = None
    closed_at: datetime.datetime | None = None
    actual_close_cents: int | None = None
    difference_cents: int | None = None
    close_idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if not self.register_id.strip():
            raise ValueError("Cash register ID is required")
        if not self.opened_by.strip():
            raise ValueError("Opened by is required")
        CashAmount(self.opening_balance_cents)
        CashAmount(self.expected_close_cents)
        if not self.open_idempotency_key.strip():
            raise ValueError("Opening idempotency key is required")
        if self.status is CashShiftStatus.OPEN:
            if any(
                value is not None
                for value in (
                    self.closed_by,
                    self.closed_at,
                    self.actual_close_cents,
                    self.difference_cents,
                    self.close_idempotency_key,
                )
            ):
                raise ValueError("Open shift cannot contain close details")
        else:
            if (
                not self.closed_by
                or self.closed_at is None
                or self.actual_close_cents is None
                or self.difference_cents is None
                or not self.close_idempotency_key
            ):
                raise ValueError("Closed shift must contain close details")
            CashAmount(self.actual_close_cents)
        object.__setattr__(self, "register_id", self.register_id.strip())
        object.__setattr__(self, "opened_by", self.opened_by.strip())
        object.__setattr__(self, "open_idempotency_key", self.open_idempotency_key.strip())

    def record(self, movement: CashMovement) -> "CashShift":
        if self.status is not CashShiftStatus.OPEN:
            raise ValueError("Only an open cash shift can receive movements")
        expected = self.expected_close_cents + movement.delta_cents
        if expected < 0:
            raise ValueError("Cash shift balance cannot be negative")
        return dataclasses.replace(self, expected_close_cents=expected)

    def close(
        self,
        actual_close_cents: int,
        closed_by: str,
        idempotency_key: str,
        now: datetime.datetime,
    ) -> "CashShift":
        if self.status is not CashShiftStatus.OPEN:
            raise ValueError("Cash shift is already closed")
        if not closed_by.strip() or not idempotency_key.strip():
            raise ValueError("Closing actor and idempotency key are required")
        actual = CashAmount(actual_close_cents)
        return dataclasses.replace(
            self,
            status=CashShiftStatus.CLOSED,
            closed_by=closed_by.strip(),
            closed_at=now,
            actual_close_cents=actual.cents,
            difference_cents=actual.cents - self.expected_close_cents,
            close_idempotency_key=idempotency_key.strip(),
        )
