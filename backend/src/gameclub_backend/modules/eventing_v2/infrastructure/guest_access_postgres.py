import datetime
import typing
import uuid

from sqlalchemy import Boolean, DateTime, LargeBinary, String, func, select, update
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.infrastructure.database import (
    EngineProvider,
    application_transaction,
    open_session,
)
from gameclub_backend.modules.eventing_v2.application.guest_access import GuestAccessGrant
from gameclub_backend.modules.sessions.application.v2_transfer import V2TransferReservation
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionTransactionWriter,
    lock_session_admission,
    require_session_admission,
)


class GuestAccessBase(DeclarativeBase):
    pass


class GuestAccessGrantModel(GuestAccessBase):
    __tablename__ = "v2_guest_access_grants"

    is_extension: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default="false")
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
            is_extension=self.is_extension,
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
            is_extension=value.is_extension,
            payment_id=value.payment_id,
            workstation_id=value.workstation_id,
            expires_at=value.expires_at,
            session_id=value.session_id,
            payload=value.payload,
            signature=value.signature,
            signing_key_id=value.signing_key_id,
        )


class GuestTransferAccessModel(GuestAccessBase):
    __tablename__ = "v2_guest_transfer_access"

    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    target_workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    issued_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    signed_snapshot: Mapped[bytes] = mapped_column(LargeBinary())


class PostgresGuestAccessGrantRepository:
    def __init__(
        self,
        engine_provider: EngineProvider,
        release_sale_hold: typing.Callable[[uuid.UUID], typing.Awaitable[None]] | None = None,
    ) -> None:
        self._engine_provider = engine_provider
        self._release_sale_hold = release_sale_hold

    async def has_initial_access_pending(self, workstation_id: uuid.UUID) -> bool:
        async with open_session(self._engine_provider) as db:
            return (
                await db.scalar(
                    select(GuestAccessGrantModel.id)
                    .where(
                        GuestAccessGrantModel.workstation_id == workstation_id,
                        ~GuestAccessGrantModel.is_extension,
                        GuestAccessGrantModel.payload.is_(None),
                        GuestAccessGrantModel.expires_at > func.clock_timestamp(),
                    )
                    .limit(1)
                )
                is not None
            )

    async def latest_transfer_for_session(
        self, session_id: uuid.UUID, workstation_id: uuid.UUID
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot | None:
        async with open_session(self._engine_provider) as db:
            item = await db.scalar(
                select(GuestTransferAccessModel)
                .where(
                    GuestTransferAccessModel.session_id == session_id,
                    GuestTransferAccessModel.target_workstation_id == workstation_id,
                )
                .order_by(
                    GuestTransferAccessModel.issued_at.desc(), GuestTransferAccessModel.operation_id
                )
                .limit(1)
            )
            return self._decode_transfer(item)

    async def save_guest_transfer(
        self,
        operation: V2TransferReservation,
        snapshot: offline_session_snapshot_pb2.SignedOfflineSessionSnapshot,
    ) -> None:
        async with open_session(self._engine_provider) as db:
            if not db.in_transaction():
                raise RuntimeError("Guest transfer must share the session commit transaction")
            issued_at = snapshot.payload.issued_at.ToDatetime(datetime.UTC)
            db.add(
                GuestTransferAccessModel(
                    operation_id=operation.operation_id,
                    session_id=operation.session_id,
                    target_workstation_id=operation.target_workstation_id,
                    issued_at=issued_at,
                    signed_snapshot=snapshot.SerializeToString(deterministic=True),
                )
            )
            await db.execute(
                update(GuestAccessGrantModel)
                .where(
                    GuestAccessGrantModel.session_id == operation.session_id,
                    GuestAccessGrantModel.workstation_id == operation.source_workstation_id,
                    GuestAccessGrantModel.is_extension,
                    GuestAccessGrantModel.payload.is_(None),
                )
                .values(workstation_id=operation.target_workstation_id)
            )
            await db.execute(
                update(GuestAccessGrantModel)
                .where(
                    GuestAccessGrantModel.session_id == operation.session_id,
                    ~GuestAccessGrantModel.is_extension,
                    GuestAccessGrantModel.expires_at >= issued_at,
                )
                .values(expires_at=issued_at - datetime.timedelta(microseconds=1))
            )

    @staticmethod
    def _decode_transfer(
        item: GuestTransferAccessModel | None,
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot | None:
        if item is None:
            return None
        return offline_session_snapshot_pb2.SignedOfflineSessionSnapshot.FromString(
            item.signed_snapshot
        )

    async def list_redeemed_for_session(self, session_id: uuid.UUID) -> list[GuestAccessGrant]:
        async with open_session(self._engine_provider) as session:
            grants = await session.scalars(
                select(GuestAccessGrantModel).where(
                    GuestAccessGrantModel.session_id == session_id,
                    GuestAccessGrantModel.payload.is_not(None),
                    GuestAccessGrantModel.signature.is_not(None),
                )
            )
            return [grant.to_domain() for grant in grants]

    async def get_by_payment(self, payment_id: uuid.UUID) -> GuestAccessGrant | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(GuestAccessGrantModel).where(GuestAccessGrantModel.payment_id == payment_id)
            )
            return model.to_domain() if model else None

    async def get_pending_for_workstation(
        self,
        workstation_id: uuid.UUID,
        now: datetime.datetime,
        session_id: uuid.UUID | None = None,
        applied_grant_ids: tuple[uuid.UUID, ...] = (),
    ) -> GuestAccessGrant | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(GuestAccessGrantModel)
                .where(
                    GuestAccessGrantModel.workstation_id == workstation_id,
                    GuestAccessGrantModel.id.not_in(applied_grant_ids),
                    (GuestAccessGrantModel.session_id == session_id)
                    if session_id is not None
                    else (GuestAccessGrantModel.expires_at >= now),
                    GuestAccessGrantModel.is_extension == (session_id is not None),
                )
                .order_by(
                    GuestAccessGrantModel.payload.is_not(None)
                    if session_id is None
                    else GuestAccessGrantModel.expires_at,
                    GuestAccessGrantModel.expires_at,
                )
                .limit(1)
            )
            return model.to_domain() if model else None

    async def save(self, grant: GuestAccessGrant) -> GuestAccessGrant:
        async with application_transaction(self._engine_provider) as session:
            if grant.session_id is None:
                await lock_session_admission(session)
                await require_session_admission(session, grant.workstation_id)
            else:
                await PostgresSessionTransactionWriter().require_access(
                    session, grant.session_id, grant.workstation_id
                )
            model = await session.scalar(
                select(GuestAccessGrantModel)
                .where(GuestAccessGrantModel.payment_id == grant.payment_id)
                .with_for_update()
            )
            if model is None:
                session.add(GuestAccessGrantModel.from_domain(grant))
                if self._release_sale_hold is not None:
                    await self._release_sale_hold(grant.payment_id)
                return grant
            if model.id != grant.id:
                return model.to_domain()
            model.session_id = grant.session_id
            model.payload = grant.payload
            model.signature = grant.signature
            model.signing_key_id = grant.signing_key_id
            return grant
