from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, String, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.sessions.domain import Session, SessionTransferOffer, TransferStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import SessionModel


class TransferBase(DeclarativeBase):
    pass


class SessionTransferOfferModel(TransferBase):
    __tablename__ = "session_transfer_offers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    source_workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    requires_package_burn: Mapped[bool] = mapped_column(Boolean(), default=False)
    warning: Mapped[str | None] = mapped_column(String(256), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    confirm_idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_domain(self) -> SessionTransferOffer:
        return SessionTransferOffer(
            id=self.id,
            session_id=self.session_id,
            client_id=self.client_id,
            source_workstation_id=self.source_workstation_id,
            target_workstation_id=self.target_workstation_id,
            token=self.token,
            status=TransferStatus(self.status),
            requires_package_burn=self.requires_package_burn,
            warning=self.warning,
            idempotency_key=self.idempotency_key,
            confirm_idempotency_key=self.confirm_idempotency_key,
            created_at=self.created_at,
            expires_at=self.expires_at,
            confirmed_at=self.confirmed_at,
        )

    @classmethod
    def from_domain(cls, item: SessionTransferOffer) -> SessionTransferOfferModel:
        return cls(
            id=item.id,
            session_id=item.session_id,
            client_id=item.client_id,
            source_workstation_id=item.source_workstation_id,
            target_workstation_id=item.target_workstation_id,
            token=item.token,
            status=item.status.value,
            requires_package_burn=item.requires_package_burn,
            warning=item.warning,
            idempotency_key=item.idempotency_key,
            confirm_idempotency_key=item.confirm_idempotency_key,
            created_at=item.created_at,
            expires_at=item.expires_at,
            confirmed_at=item.confirmed_at,
        )


class PostgresSessionTransferRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, offer_id: uuid.UUID) -> SessionTransferOffer | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(SessionTransferOfferModel, offer_id)
            return model.to_domain() if model else None

    async def get_by_idempotency_key(self, key: str) -> SessionTransferOffer | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(SessionTransferOfferModel).where(
                    SessionTransferOfferModel.idempotency_key == key
                )
            )
            return model.to_domain() if model else None

    async def save(self, offer: SessionTransferOffer) -> SessionTransferOffer:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"session-transfer:{offer.id}"},
                )
                existing = await session.scalar(
                    select(SessionTransferOfferModel)
                    .where(SessionTransferOfferModel.id == offer.id)
                    .with_for_update()
                )
                existing_by_key = await session.scalar(
                    select(SessionTransferOfferModel).where(
                        SessionTransferOfferModel.idempotency_key == offer.idempotency_key
                    )
                )
                if existing_by_key is not None and existing_by_key.id != offer.id:
                    raise ValueError("Transfer idempotency key belongs to another offer")
                if existing is None:
                    session.add(SessionTransferOfferModel.from_domain(offer))
                    return offer
                if existing.status == TransferStatus.CONFIRMED.value:
                    return existing.to_domain()
                for key, value in SessionTransferOfferModel.from_domain(offer).__dict__.items():
                    if not key.startswith("_"):
                        setattr(existing, key, value)
                return existing.to_domain()

    async def commit_transfer(
        self,
        offer: SessionTransferOffer,
        session: Session,
    ) -> tuple[SessionTransferOffer, Session]:
        """Atomically move session ownership and confirm the durable offer."""
        async with open_session(self._engine_provider) as db:
            async with db.begin():
                current_offer = await db.scalar(
                    select(SessionTransferOfferModel)
                    .where(SessionTransferOfferModel.id == offer.id)
                    .with_for_update()
                )
                if current_offer is None:
                    raise ValueError("Transfer offer not found")
                current_session = await db.scalar(
                    select(SessionModel).where(SessionModel.id == session.id).with_for_update()
                )
                if current_session is None:
                    raise ValueError("Session not found")
                if current_offer.status == TransferStatus.CONFIRMED.value:
                    return current_offer.to_domain(), current_session.to_domain()

                for workstation_id in sorted(
                    {session.workstation_id, offer.target_workstation_id}, key=str
                ):
                    await db.execute(
                        text("SELECT id FROM workstations WHERE id = :workstation_id FOR UPDATE"),
                        {"workstation_id": workstation_id},
                    )
                occupied = await db.scalar(
                    select(SessionModel.id)
                    .where(
                        SessionModel.workstation_id == offer.target_workstation_id,
                        SessionModel.status == "active",
                    )
                    .with_for_update()
                )
                if occupied is not None:
                    raise ValueError("Transfer target already has an active session")
                if (
                    current_session.status != "active"
                    or current_session.workstation_id != offer.source_workstation_id
                ):
                    raise ValueError("Source session is no longer transferable")
                current_session.workstation_id = offer.target_workstation_id
                current_offer.status = offer.status.value
                current_offer.confirm_idempotency_key = offer.confirm_idempotency_key
                current_offer.confirmed_at = offer.confirmed_at
                return current_offer.to_domain(), current_session.to_domain()
