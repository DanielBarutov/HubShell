import datetime
import uuid

from sqlalchemy import DateTime, LargeBinary, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.eventing_v2.application.guest_access import GuestAccessGrant


class GuestAccessBase(DeclarativeBase):
    pass


class GuestAccessGrantModel(GuestAccessBase):
    __tablename__ = "v2_guest_access_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, index=True)
    workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    signature: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    signing_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def to_domain(self) -> GuestAccessGrant:
        return GuestAccessGrant(
            id=self.id,
            payment_id=self.payment_id,
            workstation_id=self.workstation_id,
            expires_at=self.expires_at,
            session_id=self.session_id,
            payload=self.payload,
            signature=self.signature,
            signing_key_id=self.signing_key_id,
        )

    @classmethod
    def from_domain(cls, value: GuestAccessGrant) -> "GuestAccessGrantModel":
        return cls(
            id=value.id,
            payment_id=value.payment_id,
            workstation_id=value.workstation_id,
            expires_at=value.expires_at,
            session_id=value.session_id,
            payload=value.payload,
            signature=value.signature,
            signing_key_id=value.signing_key_id,
        )


class PostgresGuestAccessGrantRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get_by_payment(self, payment_id: uuid.UUID) -> GuestAccessGrant | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(GuestAccessGrantModel).where(GuestAccessGrantModel.payment_id == payment_id)
            )
            return model.to_domain() if model else None

    async def get_pending_for_workstation(
        self, workstation_id: uuid.UUID, now: datetime.datetime
    ) -> GuestAccessGrant | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(GuestAccessGrantModel)
                .where(
                    GuestAccessGrantModel.workstation_id == workstation_id,
                    GuestAccessGrantModel.expires_at >= now,
                )
                .order_by(GuestAccessGrantModel.expires_at)
                .limit(1)
            )
            return model.to_domain() if model else None

    async def save(self, grant: GuestAccessGrant) -> GuestAccessGrant:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                model = await session.scalar(
                    select(GuestAccessGrantModel)
                    .where(GuestAccessGrantModel.payment_id == grant.payment_id)
                    .with_for_update()
                )
                if model is None:
                    session.add(GuestAccessGrantModel.from_domain(grant))
                    return grant
                if model.id != grant.id:
                    return model.to_domain()
                model.session_id = grant.session_id
                model.payload = grant.payload
                model.signature = grant.signature
                model.signing_key_id = grant.signing_key_id
                return grant
