import dataclasses
import datetime
import typing
import uuid


@dataclasses.dataclass(frozen=True)
class AuditEvent:
    id: uuid.UUID
    actor_id: str | None
    action: str
    resource_path: str
    outcome: str
    status_code: int
    request_id: str | None
    created_at: datetime.datetime


class AuditRepository(typing.Protocol):
    async def record(self, event: AuditEvent) -> AuditEvent:
        """Persist a security-relevant administrative event."""

    async def list_recent(self, limit: int = 100) -> list[AuditEvent]:
        """Return the newest security-relevant administrative events."""
