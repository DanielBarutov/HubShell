import datetime
import uuid

from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.workstations.domain import Workstation, WorkstationStatus


class WorkstationBase(DeclarativeBase):
    pass


class WorkstationModel(WorkstationBase):
    __tablename__ = "workstations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    mac_address: Mapped[str | None] = mapped_column(
        String(17), unique=True, index=True, nullable=True
    )
    installation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    group_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    position: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    last_seen_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    client_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disabled_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    archived_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_domain(self) -> Workstation:
        return Workstation(
            id=self.id,
            device_id=self.device_id,
            name=self.name,
            group_id=self.group_id,
            position=self.position,
            status=WorkstationStatus(self.status),
            last_seen_at=self.last_seen_at,
            client_version=self.client_version,
            disabled_reason=self.disabled_reason,
            capabilities=tuple(self.capabilities or ()),
            archived_at=self.archived_at,
            mac_address=self.mac_address,
            installation_id=self.installation_id,
        )

    @classmethod
    def from_domain(cls, workstation: Workstation) -> "WorkstationModel":
        return cls(
            id=workstation.id,
            device_id=workstation.device_id,
            name=workstation.name,
            group_id=workstation.group_id,
            position=workstation.position,
            status=workstation.status.value,
            last_seen_at=workstation.last_seen_at,
            client_version=workstation.client_version,
            disabled_reason=workstation.disabled_reason,
            capabilities=list(workstation.capabilities),
            archived_at=workstation.archived_at,
            mac_address=workstation.mac_address,
            installation_id=workstation.installation_id,
        )


class PostgresWorkstationRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(WorkstationModel, workstation_id)
            return model.to_domain() if model else None

    async def get_by_device_id(self, device_id: str) -> Workstation | None:
        async with open_session(self._engine_provider) as session:
            result = await session.scalar(
                select(WorkstationModel).where(WorkstationModel.device_id == device_id)
            )
            return result.to_domain() if result else None

    async def get_by_mac_address(self, mac_address: str) -> Workstation | None:
        async with open_session(self._engine_provider) as session:
            result = await session.scalar(
                select(WorkstationModel).where(WorkstationModel.mac_address == mac_address)
            )
            return result.to_domain() if result else None

    async def list(self) -> list[Workstation]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(WorkstationModel)
                .where(WorkstationModel.archived_at.is_(None))
                .order_by(
                    WorkstationModel.position.is_(None),
                    WorkstationModel.position,
                )
            )
            return [model.to_domain() for model in result]

    async def save(self, workstation: Workstation) -> Workstation:
        async with open_session(self._engine_provider) as session:
            model = await session.get(WorkstationModel, workstation.id)
            if model is None:
                session.add(WorkstationModel.from_domain(workstation))
            else:
                for key, value in WorkstationModel.from_domain(workstation).__dict__.items():
                    if not key.startswith("_"):
                        setattr(model, key, value)
            await session.commit()
            return workstation

    async def delete(self, workstation_id: uuid.UUID) -> None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(WorkstationModel, workstation_id)
            if model is not None:
                await session.delete(model)
                await session.commit()
