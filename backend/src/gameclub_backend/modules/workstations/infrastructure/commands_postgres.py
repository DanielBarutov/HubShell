import datetime
import uuid

from sqlalchemy import DateTime, String, Text, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.workstations.domain_commands import (
    WorkstationCommand,
    WorkstationCommandStatus,
)


class WorkstationCommandBase(DeclarativeBase):
    pass


class WorkstationCommandModel(WorkstationCommandBase):
    __tablename__ = "workstation_commands"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workstation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
    )
    command_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text())
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledgement_message: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    def to_domain(self) -> WorkstationCommand:
        return WorkstationCommand(
            id=self.id,
            workstation_id=self.workstation_id,
            command_type=self.command_type,
            payload_json=self.payload_json,
            idempotency_key=self.idempotency_key,
            status=WorkstationCommandStatus(self.status),
            created_at=self.created_at,
            expires_at=self.expires_at,
            acknowledged_at=self.acknowledged_at,
            acknowledgement_message=self.acknowledgement_message,
        )

    @classmethod
    def from_domain(cls, command: WorkstationCommand) -> "WorkstationCommandModel":
        return cls(
            id=command.id,
            workstation_id=command.workstation_id,
            command_type=command.command_type,
            payload_json=command.payload_json,
            idempotency_key=command.idempotency_key,
            status=command.status.value,
            created_at=command.created_at,
            expires_at=command.expires_at,
            acknowledged_at=command.acknowledged_at,
            acknowledgement_message=command.acknowledgement_message,
        )


class PostgresWorkstationCommandRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, command_id: uuid.UUID) -> WorkstationCommand | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(WorkstationCommandModel, command_id)
            return model.to_domain() if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> WorkstationCommand | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(WorkstationCommandModel).where(
                    WorkstationCommandModel.idempotency_key == idempotency_key
                )
            )
            return model.to_domain() if model else None

    async def list_pending(self, workstation_id: uuid.UUID) -> list[WorkstationCommand]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(WorkstationCommandModel)
                .where(
                    WorkstationCommandModel.workstation_id == workstation_id,
                    WorkstationCommandModel.status == WorkstationCommandStatus.QUEUED.value,
                )
                .order_by(WorkstationCommandModel.created_at)
            )
            return [model.to_domain() for model in result]

    async def expire_queued_before(self, now: datetime.datetime) -> None:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                models = await session.scalars(
                    select(WorkstationCommandModel).where(
                        WorkstationCommandModel.status == WorkstationCommandStatus.QUEUED.value,
                        WorkstationCommandModel.expires_at <= now,
                    )
                )
                for model in models:
                    updated = model.to_domain().expire(now)
                    model.status = updated.status.value
                    model.acknowledged_at = updated.acknowledged_at
                    model.acknowledgement_message = updated.acknowledgement_message

    async def expire(self, command_id: uuid.UUID, now: datetime.datetime) -> WorkstationCommand:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.get(WorkstationCommandModel, command_id)
                if model is None:
                    raise ValueError("Workstation command not found")
                updated = model.to_domain().expire(now)
                model.status = updated.status.value
                model.acknowledged_at = updated.acknowledged_at
                model.acknowledgement_message = updated.acknowledgement_message
                return updated

    async def save(self, command: WorkstationCommand) -> WorkstationCommand:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"workstation-command:{command.idempotency_key}"},
                )
                existing = await session.scalar(
                    select(WorkstationCommandModel).where(
                        WorkstationCommandModel.idempotency_key == command.idempotency_key
                    )
                )
                if existing is not None:
                    return existing.to_domain()
                session.add(WorkstationCommandModel.from_domain(command))
                return command

    async def acknowledge(
        self,
        command_id: uuid.UUID,
        success: bool,
        message: str | None,
        now: datetime.datetime,
    ) -> WorkstationCommand:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.get(WorkstationCommandModel, command_id)
                if model is None:
                    raise ValueError("Workstation command not found")
                updated = model.to_domain().acknowledge(success, message, now)
                model.status = updated.status.value
                model.acknowledged_at = updated.acknowledged_at
                model.acknowledgement_message = updated.acknowledgement_message
                return updated
