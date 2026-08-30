import dataclasses
import datetime
import enum
import uuid


class WorkstationCommandStatus(enum.StrEnum):
    QUEUED = "queued"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclasses.dataclass(frozen=True)
class WorkstationCommand:
    id: uuid.UUID
    workstation_id: uuid.UUID
    command_type: str
    payload_json: str
    idempotency_key: str
    status: WorkstationCommandStatus
    created_at: datetime.datetime
    expires_at: datetime.datetime
    acknowledged_at: datetime.datetime | None = None
    acknowledgement_message: str | None = None

    def acknowledge(
        self,
        success: bool,
        message: str | None,
        now: datetime.datetime,
    ) -> "WorkstationCommand":
        if self.status is not WorkstationCommandStatus.QUEUED:
            return self
        if now >= self.expires_at:
            return self.expire(now)
        return dataclasses.replace(
            self,
            status=(
                WorkstationCommandStatus.ACKNOWLEDGED
                if success
                else WorkstationCommandStatus.FAILED
            ),
            acknowledged_at=now,
            acknowledgement_message=message.strip() if message else None,
        )

    def expire(self, now: datetime.datetime) -> "WorkstationCommand":
        if self.status is not WorkstationCommandStatus.QUEUED:
            return self
        return dataclasses.replace(
            self,
            status=WorkstationCommandStatus.EXPIRED,
            acknowledged_at=now,
            acknowledgement_message="Command expired before acknowledgement",
        )
