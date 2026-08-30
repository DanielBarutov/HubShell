from gameclub_backend.application.audit import AuditEvent


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        return event

    async def list_recent(self, limit: int = 100) -> list[AuditEvent]:
        return sorted(self.events, key=lambda event: event.created_at, reverse=True)[:limit]
