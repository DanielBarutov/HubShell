"""Постоянная серверная привязка V2 session к клиенту и устройству."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, LargeBinary, String, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.eventing_v2.application.lease import V2SessionLease
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import V2EventingBase


class V2SessionLeaseModel(V2EventingBase):
    """Записывается только после успешной server-side выдачи V2 snapshot."""

    __tablename__ = "v2_session_leases"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    snapshot_version: Mapped[int] = mapped_column(Integer(), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    signing_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot_payload: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    snapshot_signature: Mapped[bytes | None] = mapped_column(LargeBinary(), nullable=True)
    snapshot_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    issued_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_domain(self) -> V2SessionLease:
        return V2SessionLease(
            session_id=self.session_id,
            client_id=self.client_id,
            device_id=self.device_id,
            snapshot_id=self.snapshot_id,
            snapshot_version=self.snapshot_version,
            policy_version=self.policy_version,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
        )

    @classmethod
    def from_domain(cls, lease: V2SessionLease) -> V2SessionLeaseModel:
        return cls(
            session_id=lease.session_id,
            client_id=lease.client_id,
            device_id=lease.device_id,
            snapshot_id=lease.snapshot_id,
            snapshot_version=lease.snapshot_version,
            policy_version=lease.policy_version,
            signing_key_id=None,
            snapshot_payload=None,
            snapshot_signature=None,
            snapshot_payload_hash=None,
            status="active",
            issued_at=lease.issued_at,
            expires_at=lease.expires_at,
            revoked_at=None,
        )


class PostgresV2SessionLeaseRepository:
    """Выдаёт lease только при отсутствии другой active V2-сессии."""

    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def revoke(
        self,
        session_id: uuid.UUID,
        revoked_at: datetime.datetime,
    ) -> None:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                lease = await session.get(
                    V2SessionLeaseModel,
                    session_id,
                    with_for_update=True,
                )
                if lease is None or lease.status != "active":
                    return
                lease.status = "revoked"
                lease.revoked_at = revoked_at

    async def issue_exclusively(self, lease: V2SessionLease) -> tuple[V2SessionLease, bool]:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                for lock_key in (
                    f"v2-lease-client:{lease.client_id}",
                    f"v2-lease-device:{lease.device_id}",
                    f"v2-lease-session:{lease.session_id}",
                ):
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                        {"lock_key": lock_key},
                    )
                current = await session.get(V2SessionLeaseModel, lease.session_id)
                if current is not None:
                    if current.snapshot_id == lease.snapshot_id and current.status == "active":
                        return current.to_domain(), True
                    raise ValueError("V2 session id belongs to another lease")
                active = await session.scalars(
                    select(V2SessionLeaseModel)
                    .where(
                        V2SessionLeaseModel.status == "active",
                        (V2SessionLeaseModel.client_id == lease.client_id)
                        | (V2SessionLeaseModel.device_id == lease.device_id),
                    )
                    .with_for_update()
                )
                if any(True for _ in active):
                    raise ValueError("Client or device already has an active V2 lease")
                session.add(V2SessionLeaseModel.from_domain(lease))
                return lease, False
