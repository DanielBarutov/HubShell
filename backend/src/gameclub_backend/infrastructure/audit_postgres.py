import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.infrastructure.database import EngineProvider, open_session


class AuditBase(DeclarativeBase):
    pass


class AuditEventModel(AuditBase):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64))
    resource_path: Mapped[str] = mapped_column(String(512))
    outcome: Mapped[str] = mapped_column(String(16))
    status_code: Mapped[int] = mapped_column(Integer)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)

    def to_domain(self) -> AuditEvent:
        return AuditEvent(
            id=self.id,
            actor_id=self.actor_id,
            action=self.action,
            resource_path=self.resource_path,
            outcome=self.outcome,
            status_code=self.status_code,
            request_id=self.request_id,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, event: AuditEvent) -> "AuditEventModel":
        return cls(
            id=event.id,
            actor_id=event.actor_id,
            action=event.action,
            resource_path=event.resource_path,
            outcome=event.outcome,
            status_code=event.status_code,
            request_id=event.request_id,
            created_at=event.created_at,
        )


class PostgresAuditRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def record(self, event: AuditEvent) -> AuditEvent:
        async with open_session(self._engine_provider) as session:
            session.add(AuditEventModel.from_domain(event))
            await session.commit()
            return event

    async def list_recent(self, limit: int = 100) -> list[AuditEvent]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(AuditEventModel).order_by(AuditEventModel.created_at.desc()).limit(limit)
            )
            return [model.to_domain() for model in result]
