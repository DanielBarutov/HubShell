"""Persistent grant history; uses the same session lock as V2 reconciliation."""

import dataclasses
import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from gameclub.v2 import offline_session_snapshot_pb2
from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.infrastructure.audit_postgres import AuditEventModel
from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.eventing_v2.application.bonus_budget import (
    BonusBudgetContext,
    BonusBudgetGrant,
    BonusBudgetRequest,
)
from gameclub_backend.modules.eventing_v2.infrastructure.lease_postgres import V2SessionLeaseModel
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
    V2EventingBase,
    V2SessionChainModel,
)


class V2BonusBudgetModel(V2EventingBase):
    __tablename__ = "v2_bonus_budgets"
    __table_args__ = (
        UniqueConstraint("session_id", "idempotency_key"),
        UniqueConstraint("session_id", "version"),
        CheckConstraint(
            "version > 0 AND ((budget_cents > 0 AND payment_limit_bps BETWEEN 1 AND 10000) "
            "OR (cancelled AND budget_cents = 0 AND payment_limit_bps = 0))"
        ),
        CheckConstraint("NOT cancelled OR NOT active"),
        Index(
            "uq_v2_bonus_budget_active", "session_id", unique=True, postgresql_where=text("active")
        ),
        CheckConstraint("spent_cents >= 0 AND spent_cents <= budget_cents"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    device_id: Mapped[str] = mapped_column(String(128))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    snapshot_version: Mapped[int] = mapped_column(Integer)
    last_sequence: Mapped[int] = mapped_column(Integer)
    last_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer)
    budget_cents: Mapped[int] = mapped_column(BigInteger)
    spent_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    payment_limit_bps: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)

    def to_domain(self) -> BonusBudgetGrant:
        request = BonusBudgetRequest(
            **{
                field.name: getattr(self, field.name)
                for field in dataclasses.fields(BonusBudgetRequest)
            }
        )
        return BonusBudgetGrant(
            self.id,
            request,
            self.version,
            self.budget_cents,
            self.payment_limit_bps,
            self.issued_at,
        )


class PostgresBonusBudgetRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def prepare(
        self, request: BonusBudgetRequest, now: datetime.datetime
    ) -> BonusBudgetContext:
        async with open_session(self._engine_provider) as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"v2-client-session:{request.session_id}"},
            )
            lease = await session.get(V2SessionLeaseModel, request.session_id, with_for_update=True)
            if (
                lease is None
                or lease.status != "active"
                or lease.client_id != request.client_id
                or lease.device_id != request.device_id
                or lease.snapshot_id != request.snapshot_id
                or lease.snapshot_version != request.snapshot_version
                or (lease.expires_at is not None and lease.expires_at < now)
            ):
                raise ApplicationError(ErrorCode.PERMISSION_DENIED, "No matching active V2 lease")
            existing = await session.scalar(
                select(V2BonusBudgetModel).where(
                    V2BonusBudgetModel.session_id == request.session_id,
                    V2BonusBudgetModel.idempotency_key == request.idempotency_key,
                )
            )
            snapshot = offline_session_snapshot_pb2.OfflineSessionSnapshotPayload()
            if lease.snapshot_payload:
                snapshot.ParseFromString(lease.snapshot_payload)
            prices = [
                item.per_minute_price_cents
                for item in snapshot.tariffs
                if (item.is_per_minute or item.per_minute_price_cents > 0)
                and (not item.HasField("zone_id") or item.zone_id == snapshot.workstation_zone_id)
            ]
            price = min(prices, default=0)
            if existing is not None:
                if existing.cancelled:
                    raise ApplicationError(ErrorCode.CONFLICT, "Minute bonus request was cancelled")
                grant = existing.to_domain()
                if grant.request != request:
                    raise ApplicationError(
                        ErrorCode.CONFLICT, "Bonus budget key belongs to another request"
                    )
                return BonusBudgetContext(grant.version + 1, grant, price)
            chain = await session.get(V2SessionChainModel, request.session_id)
            if (chain.last_sequence if chain else 0) != request.last_sequence or (
                chain.last_payload_hash if chain else None
            ) != request.last_payload_hash:
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Сначала дождитесь подтверждения локальных списаний"
                )
            version = await session.scalar(
                select(func.max(V2BonusBudgetModel.version)).where(
                    V2BonusBudgetModel.session_id == request.session_id
                )
            )
            return BonusBudgetContext((version or 0) + 1, minute_price_cents=price)

    async def prepare_cancellation(
        self, request: BonusBudgetRequest, now: datetime.datetime
    ) -> BonusBudgetContext:
        async with open_session(self._engine_provider) as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"v2-client-session:{request.session_id}"},
            )
            lease = await session.get(V2SessionLeaseModel, request.session_id, with_for_update=True)
            if (
                lease is None
                or lease.client_id != request.client_id
                or lease.device_id != request.device_id
                or lease.snapshot_id != request.snapshot_id
                or lease.snapshot_version != request.snapshot_version
            ):
                raise ApplicationError(
                    ErrorCode.PERMISSION_DENIED, "No matching V2 lease for cancellation"
                )
            existing = await session.scalar(
                select(V2BonusBudgetModel).where(
                    V2BonusBudgetModel.session_id == request.session_id,
                    V2BonusBudgetModel.idempotency_key == request.idempotency_key,
                )
            )
            if existing is not None and existing.cancelled:
                return BonusBudgetContext(existing.version + 1, is_cancelled=True)
            chain = await session.get(V2SessionChainModel, request.session_id)
            if (chain.last_sequence if chain else 0) != request.last_sequence or (
                chain.last_payload_hash if chain else None
            ) != request.last_payload_hash:
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Сначала дождитесь подтверждения локальных списаний"
                )
            version = await session.scalar(
                select(func.max(V2BonusBudgetModel.version)).where(
                    V2BonusBudgetModel.session_id == request.session_id
                )
            )
            active = await session.scalar(
                select(V2BonusBudgetModel).where(
                    V2BonusBudgetModel.session_id == request.session_id,
                    V2BonusBudgetModel.active.is_(True),
                )
            )
            return BonusBudgetContext(
                (version or 0) + 1, active.to_domain() if active is not None else None
            )

    async def cancel(
        self, request: BonusBudgetRequest, context: BonusBudgetContext, now: datetime.datetime
    ) -> None:
        async with open_session(self._engine_provider) as session:
            await session.execute(
                update(V2BonusBudgetModel)
                .where(
                    V2BonusBudgetModel.session_id == request.session_id,
                    V2BonusBudgetModel.cancelled.is_(False),
                )
                .values(active=False, cancelled=True)
            )
            existing = await session.scalar(
                select(V2BonusBudgetModel).where(
                    V2BonusBudgetModel.session_id == request.session_id,
                    V2BonusBudgetModel.idempotency_key == request.idempotency_key,
                )
            )
            if existing is not None:
                existing.cancelled = True
                existing.active = False
            else:
                session.add(
                    V2BonusBudgetModel(
                        id=uuid.uuid4(),
                        **dataclasses.asdict(request),
                        version=context.next_version,
                        budget_cents=0,
                        spent_cents=0,
                        payment_limit_bps=0,
                        issued_at=now,
                        active=False,
                        cancelled=True,
                    )
                )
            session.add(
                AuditEventModel.from_domain(
                    AuditEvent(
                        id=uuid.uuid5(
                            request.session_id, f"minute-bonus-cancel:{request.idempotency_key}"
                        ),
                        actor_id=f"client:{request.client_id}",
                        action="v2.minute_bonus.cancelled",
                        resource_path=f"clients/{request.client_id}/sessions/{request.session_id}/minute-bonus",
                        outcome="success",
                        status_code=200,
                        request_id=request.idempotency_key,
                        created_at=now,
                    )
                )
            )
            await session.flush()

    async def save(self, grant: BonusBudgetGrant) -> None:
        async with open_session(self._engine_provider) as session:
            await session.execute(
                update(V2BonusBudgetModel)
                .where(
                    V2BonusBudgetModel.session_id == grant.request.session_id,
                    V2BonusBudgetModel.active.is_(True),
                )
                .values(active=False)
            )
            session.add(
                V2BonusBudgetModel(
                    id=grant.id,
                    **dataclasses.asdict(grant.request),
                    version=grant.version,
                    budget_cents=grant.budget_cents,
                    payment_limit_bps=grant.payment_limit_bps,
                    issued_at=grant.issued_at,
                    active=True,
                )
            )
            await session.flush()
