import dataclasses
import datetime
import enum
import uuid


class SessionStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


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

    def __post_init__(self) -> None:
        if self.tariff_quantity <= 0:
            raise ValueError("Tariff quantity must be positive")

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
