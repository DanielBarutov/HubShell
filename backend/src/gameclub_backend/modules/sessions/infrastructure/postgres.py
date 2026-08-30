from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.sessions.domain import Session, SessionStatus


class SessionBase(DeclarativeBase):
    pass


class SessionModel(SessionBase):
    __tablename__ = "gaming_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    guest_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    guest_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )
    tariff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    tariff_quantity: Mapped[int] = mapped_column(Integer(), default=1)

    def to_domain(self) -> Session:
        return Session(
            id=self.id,
            workstation_id=self.workstation_id,
            client_id=self.client_id,
            guest_name=self.guest_name,
            guest_id=self.guest_id,
            status=SessionStatus(self.status),
            started_at=self.started_at,
            ended_at=self.ended_at,
            source=self.source,
            created_by=self.created_by,
            created_at=self.created_at,
            reservation_id=self.reservation_id,
            idempotency_key=self.idempotency_key,
            tariff_id=self.tariff_id,
            tariff_quantity=self.tariff_quantity,
        )

    @classmethod
    def from_domain(cls, session: Session) -> SessionModel:
        return cls(
            id=session.id,
            workstation_id=session.workstation_id,
            client_id=session.client_id,
            guest_name=session.guest_name,
            guest_id=session.guest_id,
            status=session.status.value,
            started_at=session.started_at,
            ended_at=session.ended_at,
            source=session.source,
            created_by=session.created_by,
            created_at=session.created_at,
            reservation_id=session.reservation_id,
            idempotency_key=session.idempotency_key,
            tariff_id=session.tariff_id,
            tariff_quantity=session.tariff_quantity,
        )


class PostgresSessionRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, session_id: uuid.UUID) -> Session | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(SessionModel, session_id)
            return model.to_domain() if model else None

    async def get_active_for_workstation(self, workstation_id: uuid.UUID) -> Session | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(SessionModel)
                .where(
                    SessionModel.workstation_id == workstation_id,
                    SessionModel.status == SessionStatus.ACTIVE.value,
                )
                .order_by(SessionModel.started_at.desc())
                .limit(1)
            )
            return model.to_domain() if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Session | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(SessionModel).where(SessionModel.idempotency_key == idempotency_key)
            )
            return model.to_domain() if model else None

    async def list(
        self,
        workstation_id: uuid.UUID | None = None,
        active_only: bool = False,
    ) -> list[Session]:
        async with open_session(self._engine_provider) as session:
            filters = []
            if workstation_id is not None:
                filters.append(SessionModel.workstation_id == workstation_id)
            if active_only:
                filters.append(SessionModel.status == SessionStatus.ACTIVE.value)
            result = await session.scalars(
                select(SessionModel).where(*filters).order_by(SessionModel.started_at.desc())
            )
            return [model.to_domain() for model in result]

    async def save(self, session: Session) -> Session:
        async with open_session(self._engine_provider) as db_session:
            async with db_session.begin():
                await db_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"gaming-session-workstation:{session.workstation_id}"},
                )
                model = await db_session.get(SessionModel, session.id)
                if model is None and session.idempotency_key:
                    await db_session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                        {"lock_key": f"gaming-session-key:{session.idempotency_key}"},
                    )
                    repeated = await db_session.scalar(
                        select(SessionModel).where(
                            SessionModel.idempotency_key == session.idempotency_key
                        )
                    )
                    if repeated is not None:
                        if repeated.workstation_id != session.workstation_id:
                            raise ValueError("Idempotency key belongs to another workstation")
                        return repeated.to_domain()
                if model is None:
                    if session.status is SessionStatus.ACTIVE:
                        active = await db_session.scalar(
                            select(SessionModel)
                            .where(
                                SessionModel.workstation_id == session.workstation_id,
                                SessionModel.status == SessionStatus.ACTIVE.value,
                            )
                            .with_for_update()
                        )
                        if active is not None:
                            raise ValueError("Workstation already has an active session")
                    db_session.add(SessionModel.from_domain(session))
                    return session

                self._copy_values(model, session)
                return session

    @staticmethod
    def _copy_values(model: SessionModel, session: Session) -> None:
        values = SessionModel.from_domain(session).__dict__
        for key, value in values.items():
            if not key.startswith("_"):
                setattr(model, key, value)
