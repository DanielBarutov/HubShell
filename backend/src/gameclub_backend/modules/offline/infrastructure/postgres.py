from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, Text, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.offline.domain import (
    OfflineOperation,
    OfflineOperationKind,
    OfflineOperationResult,
    OfflineOperationStatus,
)


class OfflineBase(DeclarativeBase):
    pass


class OfflineOperationModel(OfflineBase):
    __tablename__ = "offline_operations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    device_id: Mapped[str] = mapped_column(String(128), index=True)
    sequence: Mapped[int] = mapped_column(Integer())
    kind: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text())
    snapshot_version: Mapped[int] = mapped_column(Integer())
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True)
    message: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_operation(self) -> OfflineOperation:
        return OfflineOperation(
            id=self.id,
            session_id=self.session_id,
            device_id=self.device_id,
            sequence=self.sequence,
            kind=OfflineOperationKind(self.kind),
            payload_json=self.payload_json,
            snapshot_version=self.snapshot_version,
            idempotency_key=self.idempotency_key,
            checksum=self.checksum,
            created_at=self.created_at,
        )

    def to_result(self) -> OfflineOperationResult:
        return OfflineOperationResult(
            operation_id=self.id,
            sequence=self.sequence,
            status=OfflineOperationStatus(self.status),
            message=self.message,
            applied_at=self.applied_at,
        )

    @classmethod
    def from_domain(
        cls,
        operation: OfflineOperation,
        result: OfflineOperationResult,
    ) -> OfflineOperationModel:
        return cls(
            id=operation.id,
            session_id=operation.session_id,
            device_id=operation.device_id,
            sequence=operation.sequence,
            kind=operation.kind.value,
            payload_json=operation.payload_json,
            snapshot_version=operation.snapshot_version,
            idempotency_key=operation.idempotency_key,
            checksum=operation.checksum,
            status=result.status.value,
            message=result.message,
            created_at=operation.created_at,
            applied_at=result.applied_at,
        )


class PostgresOfflineReplayRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get_by_idempotency_key(self, key: str) -> OfflineOperationResult | None:
        async with open_session(self._engine_provider) as session:
            item = await session.scalar(
                select(OfflineOperationModel).where(OfflineOperationModel.idempotency_key == key)
            )
            return item.to_result() if item else None

    async def get_operation_by_idempotency_key(self, key: str) -> OfflineOperation | None:
        async with open_session(self._engine_provider) as session:
            item = await session.scalar(
                select(OfflineOperationModel).where(OfflineOperationModel.idempotency_key == key)
            )
            return item.to_operation() if item else None

    async def get_by_sequence(
        self,
        device_id: str,
        session_id: uuid.UUID,
        sequence: int,
    ) -> tuple[OfflineOperation, OfflineOperationResult] | None:
        async with open_session(self._engine_provider) as session:
            item = await session.scalar(
                select(OfflineOperationModel).where(
                    OfflineOperationModel.device_id == device_id,
                    OfflineOperationModel.session_id == session_id,
                    OfflineOperationModel.sequence == sequence,
                )
            )
            return (item.to_operation(), item.to_result()) if item else None

    async def get_last_sequence(self, device_id: str, session_id: uuid.UUID) -> int:
        async with open_session(self._engine_provider) as session:
            item = await session.scalar(
                select(OfflineOperationModel.sequence)
                .where(
                    OfflineOperationModel.device_id == device_id,
                    OfflineOperationModel.session_id == session_id,
                )
                .order_by(OfflineOperationModel.sequence.desc())
                .limit(1)
            )
            return int(item or 0)

    async def save(
        self,
        operation: OfflineOperation,
        result: OfflineOperationResult,
    ) -> OfflineOperationResult:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": (f"offline:{operation.device_id}:{operation.session_id}")},
                )
                existing = await session.scalar(
                    select(OfflineOperationModel)
                    .where(OfflineOperationModel.idempotency_key == operation.idempotency_key)
                    .with_for_update()
                )
                if existing is not None:
                    if existing.id != operation.id:
                        return existing.to_result()
                    if existing.status != OfflineOperationStatus.PENDING.value:
                        return existing.to_result()
                    existing.status = result.status.value
                    existing.message = result.message
                    existing.applied_at = result.applied_at
                    return existing.to_result()
                session.add(OfflineOperationModel.from_domain(operation, result))
                return result
