import dataclasses
import datetime
import enum
import typing
import uuid

if typing.TYPE_CHECKING:
    from gameclub_backend.modules.billing.domain import SessionMeter
    from gameclub_backend.modules.entitlements.domain import Entitlement


class SessionStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class TransferStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    REJECTED = "rejected"


@dataclasses.dataclass(frozen=True)
class Session:
    id: uuid.UUID
    workstation_id: uuid.UUID
    client_id: uuid.UUID | None
    guest_name: str | None
    status: SessionStatus
    started_at: datetime.datetime
    ended_at: datetime.datetime | None
    source: str
    created_by: str
    created_at: datetime.datetime
    reservation_id: uuid.UUID | None = None
    idempotency_key: str | None = None
    guest_id: uuid.UUID | None = None
    tariff_id: uuid.UUID | None = None
    tariff_quantity: int = 1
    guest_payment_id: uuid.UUID | None = None
    login_grant_minutes: int = 0
    entitlement_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.tariff_quantity <= 0:
            raise ValueError("Tariff quantity must be positive")
        if self.login_grant_minutes < 0:
            raise ValueError("Login grant minutes cannot be negative")

    def stop(self, now: datetime.datetime) -> "Session":
        if self.status is SessionStatus.COMPLETED:
            return self
        if self.status is not SessionStatus.ACTIVE:
            raise ValueError("Session is not active")
        if now.tzinfo is None:
            raise ValueError("Session end time must include timezone")
        return dataclasses.replace(
            self,
            status=SessionStatus.COMPLETED,
            ended_at=now,
        )

    def interrupt(self, now: datetime.datetime) -> "Session":
        """Finish an active session early while keeping the first-slice lifecycle."""
        return self.stop(now)

    def transfer(self, workstation_id: uuid.UUID) -> "Session":
        if self.status is not SessionStatus.ACTIVE:
            raise ValueError("Only an active session can be transferred")
        if self.workstation_id == workstation_id:
            raise ValueError("Transfer target must be another workstation")
        return dataclasses.replace(self, workstation_id=workstation_id)


@dataclasses.dataclass(frozen=True)
class SessionSnapshot:
    """Server-owned, versioned state sent to operator and device consumers."""

    schema_version: int
    server_time: datetime.datetime
    session: Session
    workstation_id: uuid.UUID
    device_id: str
    zone_id: str | None
    client_id: uuid.UUID | None
    balance_cents: int | None
    balance_bonus: int | None
    active_entitlement: "Entitlement | None"
    entitlements: tuple["Entitlement", ...]
    meter: "SessionMeter | None"
    allowed_actions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version < 1:
            raise ValueError("Session snapshot schema version is invalid")
        if self.server_time.tzinfo is None:
            raise ValueError("Session snapshot server time must include timezone")


@dataclasses.dataclass(frozen=True)
class SessionTransferOffer:
    id: uuid.UUID
    session_id: uuid.UUID
    client_id: uuid.UUID
    source_workstation_id: uuid.UUID
    target_workstation_id: uuid.UUID
    token: str
    status: TransferStatus
    requires_package_burn: bool
    warning: str | None
    idempotency_key: str
    confirm_idempotency_key: str | None
    created_at: datetime.datetime
    expires_at: datetime.datetime
    confirmed_at: datetime.datetime | None = None

    def __post_init__(self) -> None:
        if not self.token.strip() or not self.idempotency_key.strip():
            raise ValueError("Transfer token and idempotency key are required")
        if self.expires_at <= self.created_at:
            raise ValueError("Transfer offer expiry must be after creation")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Transfer offer timestamps must include timezone")

    def expire_if_needed(self, now: datetime.datetime) -> "SessionTransferOffer":
        if self.status is TransferStatus.PENDING and now >= self.expires_at:
            return dataclasses.replace(self, status=TransferStatus.EXPIRED)
        return self

    def confirm(self, idempotency_key: str, now: datetime.datetime) -> "SessionTransferOffer":
        key = idempotency_key.strip()
        if not key:
            raise ValueError("Transfer confirmation key is required")
        if self.status is TransferStatus.CONFIRMED:
            if self.confirm_idempotency_key != key:
                raise ValueError("Transfer offer was confirmed by another request")
            return self
        if self.status is not TransferStatus.PENDING:
            raise ValueError("Transfer offer is no longer pending")
        if now.tzinfo is None or now >= self.expires_at:
            raise ValueError("Transfer offer has expired")
        return dataclasses.replace(
            self,
            status=TransferStatus.CONFIRMED,
            confirm_idempotency_key=key,
            confirmed_at=now,
        )
