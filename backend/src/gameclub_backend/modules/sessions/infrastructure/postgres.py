from __future__ import annotations

import builtins
import datetime
import uuid

from sqlalchemy import JSON, DateTime, Integer, String, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, begin_session, open_session
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
    guest_payment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    login_grant_minutes: Mapped[int] = mapped_column(Integer(), default=0)
    entitlement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_payment_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

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
            guest_payment_id=self.guest_payment_id,
            login_grant_minutes=self.login_grant_minutes,
            entitlement_id=self.entitlement_id,
            expires_at=self.expires_at,
            applied_payment_ids=tuple(self.applied_payment_ids or []),
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
            guest_payment_id=session.guest_payment_id,
            login_grant_minutes=session.login_grant_minutes,
            entitlement_id=session.entitlement_id,
            expires_at=session.expires_at,
            applied_payment_ids=list(session.applied_payment_ids),
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

    async def get_active_for_client(self, client_id: uuid.UUID) -> Session | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(SessionModel)
                .where(
                    SessionModel.client_id == client_id,
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
    ) -> builtins.list[Session]:
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

    async def list_for_client(
        self,
        client_id: uuid.UUID,
        limit: int,
    ) -> builtins.list[Session]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(SessionModel)
                .where(SessionModel.client_id == client_id)
                .order_by(SessionModel.started_at.desc())
                .limit(max(1, min(limit, 100)))
            )
            return [model.to_domain() for model in result]

    async def save(self, session: Session) -> Session:
        async with open_session(self._engine_provider) as db_session:
            async with begin_session(db_session):
                return await PostgresSessionTransactionWriter().save(db_session, session)


class PostgresSessionTransactionWriter:
    """Public transaction writer; it hides gaming_sessions storage from V2."""

    async def save(self, transaction: AsyncSession, session: Session) -> Session:
        await transaction.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"gaming-session-workstation:{session.workstation_id}"},
        )
        model = await transaction.get(SessionModel, session.id)
        if model is None and session.idempotency_key:
            await transaction.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"gaming-session-key:{session.idempotency_key}"},
            )
            repeated = await transaction.scalar(
                select(SessionModel).where(SessionModel.idempotency_key == session.idempotency_key)
            )
            if repeated is not None:
                if repeated.workstation_id != session.workstation_id:
                    raise ValueError("Idempotency key belongs to another workstation")
                return repeated.to_domain()
        if model is None:
            if session.status is SessionStatus.ACTIVE:
                if session.client_id is not None:
                    await transaction.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                        {"lock_key": f"gaming-session-client:{session.client_id}"},
                    )
                active = await transaction.scalar(
                    select(SessionModel)
                    .where(
                        SessionModel.workstation_id == session.workstation_id,
                        SessionModel.status == SessionStatus.ACTIVE.value,
                    )
                    .with_for_update()
                )
                if active is not None:
                    raise ValueError("Workstation already has an active session")
                if session.client_id is not None:
                    active_client = await transaction.scalar(
                        select(SessionModel)
                        .where(
                            SessionModel.client_id == session.client_id,
                            SessionModel.status == SessionStatus.ACTIVE.value,
                        )
                        .with_for_update()
                    )
                    if active_client is not None:
                        raise ValueError("Client already has an active session")
            transaction.add(SessionModel.from_domain(session))
            return session

        self._copy_values(model, session)
        return session

    async def complete(
        self,
        transaction: AsyncSession,
        session_id: uuid.UUID,
        ended_at: datetime.datetime,
    ) -> Session | None:
        model = await transaction.get(SessionModel, session_id, with_for_update=True)
        if model is None:
            return None
        for lock_key in (
            f"gaming-session-workstation:{model.workstation_id}",
            *([f"gaming-session-client:{model.client_id}"] if model.client_id else []),
        ):
            await transaction.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": lock_key},
            )
        if model.status == SessionStatus.ACTIVE.value:
            if ended_at.tzinfo is None:
                raise ValueError("Session end time must include timezone")
            model.status = SessionStatus.COMPLETED.value
            model.ended_at = ended_at
        return model.to_domain()

    @staticmethod
    def _copy_values(model: SessionModel, session: Session) -> None:
        values = SessionModel.from_domain(session).__dict__
        for key, value in values.items():
            if not key.startswith("_"):
                setattr(model, key, value)
