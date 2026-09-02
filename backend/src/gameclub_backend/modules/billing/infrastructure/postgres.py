from __future__ import annotations

import contextlib
import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, and_, func, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.billing.domain import (
    ChargeReconciliation,
    MeterStatus,
    ReconciliationStatus,
    RevenueSummary,
    SessionCharge,
    SessionMeter,
)


class BillingBase(DeclarativeBase):
    pass


class SessionMeterModel(BillingBase):
    __tablename__ = "session_meters"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    tariff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    billed_minutes: Mapped[int] = mapped_column(Integer(), default=0)
    billed_cents: Mapped[int] = mapped_column(Integer(), default=0)
    status: Mapped[str] = mapped_column(String(16), index=True)
    last_operation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> SessionMeter:
        return SessionMeter(
            session_id=self.session_id,
            client_id=self.client_id,
            tariff_id=self.tariff_id,
            billed_minutes=self.billed_minutes,
            billed_cents=self.billed_cents,
            status=MeterStatus(self.status),
            last_operation_id=self.last_operation_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, meter: SessionMeter) -> SessionMeterModel:
        return cls(
            session_id=meter.session_id,
            client_id=meter.client_id,
            tariff_id=meter.tariff_id,
            billed_minutes=meter.billed_minutes,
            billed_cents=meter.billed_cents,
            status=meter.status.value,
            last_operation_id=meter.last_operation_id,
            created_at=meter.created_at,
            updated_at=meter.updated_at,
        )


class PostgresMeterRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    @contextlib.asynccontextmanager
    async def acquire(self, session_id: uuid.UUID):
        async with open_session(self._engine_provider) as db_session:
            async with db_session.begin():
                await db_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"session-meter:{session_id}"},
                )
                yield

    async def get(self, session_id: uuid.UUID) -> SessionMeter | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(SessionMeterModel, session_id)
            return model.to_domain() if model else None

    async def ensure(self, meter: SessionMeter) -> SessionMeter:
        async with open_session(self._engine_provider) as db_session:
            async with db_session.begin():
                model = await db_session.get(SessionMeterModel, meter.session_id)
                if model is not None:
                    return model.to_domain()
                db_session.add(SessionMeterModel.from_domain(meter))
                return meter

    async def save(self, meter: SessionMeter) -> SessionMeter:
        async with open_session(self._engine_provider) as db_session:
            async with db_session.begin():
                model = await db_session.get(SessionMeterModel, meter.session_id)
                if model is None:
                    db_session.add(SessionMeterModel.from_domain(meter))
                else:
                    if (
                        meter.billed_minutes < model.billed_minutes
                        or meter.billed_cents < model.billed_cents
                    ):
                        raise ValueError("Session meter cannot move backwards")
                    model.client_id = meter.client_id
                    model.tariff_id = meter.tariff_id
                    model.billed_minutes = meter.billed_minutes
                    model.billed_cents = meter.billed_cents
                    model.status = meter.status.value
                    model.last_operation_id = meter.last_operation_id
                    model.updated_at = meter.updated_at
                return meter


class SessionChargeModel(BillingBase):
    __tablename__ = "session_charges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    balance_operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    tariff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    duration_minutes: Mapped[int] = mapped_column(Integer())
    amount_cents: Mapped[int] = mapped_column()
    amount_before_discount_cents: Mapped[int] = mapped_column()
    discount_amount_cents: Mapped[int] = mapped_column()
    discount_percent_bps: Mapped[int] = mapped_column(Integer())
    discount_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    charged_by: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> SessionCharge:
        return SessionCharge(
            id=self.id,
            session_id=self.session_id,
            client_id=self.client_id,
            balance_operation_id=self.balance_operation_id,
            tariff_id=self.tariff_id,
            duration_minutes=self.duration_minutes,
            amount_cents=self.amount_cents,
            amount_before_discount_cents=self.amount_before_discount_cents,
            discount_amount_cents=self.discount_amount_cents,
            discount_percent_bps=self.discount_percent_bps,
            discount_category=self.discount_category,
            charged_by=self.charged_by,
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, charge: SessionCharge) -> SessionChargeModel:
        return cls(
            id=charge.id,
            session_id=charge.session_id,
            client_id=charge.client_id,
            balance_operation_id=charge.balance_operation_id,
            tariff_id=charge.tariff_id,
            duration_minutes=charge.duration_minutes,
            amount_cents=charge.amount_cents,
            amount_before_discount_cents=charge.amount_before_discount_cents,
            discount_amount_cents=charge.discount_amount_cents,
            discount_percent_bps=charge.discount_percent_bps,
            discount_category=charge.discount_category,
            charged_by=charge.charged_by,
            idempotency_key=charge.idempotency_key,
            created_at=charge.created_at,
        )


class ChargeReconciliationModel(BillingBase):
    __tablename__ = "billing_reconciliations"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    charged_by: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    next_attempt_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(String(1_000), nullable=True)
    charge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> ChargeReconciliation:
        return ChargeReconciliation(
            session_id=self.session_id,
            idempotency_key=self.idempotency_key,
            charged_by=self.charged_by,
            status=ReconciliationStatus(self.status),
            attempts=self.attempts,
            next_attempt_at=self.next_attempt_at,
            last_error=self.last_error,
            charge_id=self.charge_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, item: ChargeReconciliation) -> ChargeReconciliationModel:
        return cls(
            session_id=item.session_id,
            idempotency_key=item.idempotency_key,
            charged_by=item.charged_by,
            status=item.status.value,
            attempts=item.attempts,
            next_attempt_at=item.next_attempt_at,
            last_error=item.last_error,
            charge_id=item.charge_id,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class PostgresChargeRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get_by_session_id(self, session_id: uuid.UUID) -> SessionCharge | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(SessionChargeModel).where(SessionChargeModel.session_id == session_id)
            )
            return model.to_domain() if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> SessionCharge | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(SessionChargeModel).where(
                    SessionChargeModel.idempotency_key == idempotency_key
                )
            )
            return model.to_domain() if model else None

    async def list_for_client(self, client_id: uuid.UUID, limit: int) -> list[SessionCharge]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(SessionChargeModel)
                .where(SessionChargeModel.client_id == client_id)
                .order_by(SessionChargeModel.created_at.desc())
                .limit(max(1, min(limit, 100)))
            )
            return [model.to_domain() for model in result]

    async def save(self, charge: SessionCharge) -> SessionCharge:
        async with open_session(self._engine_provider) as db_session:
            async with db_session.begin():
                await db_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"session-charge:{charge.session_id}"},
                )
                await db_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"session-charge-key:{charge.idempotency_key}"},
                )
                existing_by_key = await db_session.scalar(
                    select(SessionChargeModel).where(
                        SessionChargeModel.idempotency_key == charge.idempotency_key
                    )
                )
                if existing_by_key is not None:
                    if existing_by_key.session_id != charge.session_id:
                        raise ValueError("Idempotency key belongs to another session")
                    return existing_by_key.to_domain()
                existing_by_session = await db_session.scalar(
                    select(SessionChargeModel).where(
                        SessionChargeModel.session_id == charge.session_id
                    )
                )
                if existing_by_session is not None:
                    return existing_by_session.to_domain()
                db_session.add(SessionChargeModel.from_domain(charge))
                return charge

    async def revenue_between(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> RevenueSummary:
        async with open_session(self._engine_provider) as session:
            result = await session.execute(
                select(
                    func.coalesce(func.sum(SessionChargeModel.amount_cents), 0),
                    func.count(SessionChargeModel.id),
                ).where(
                    SessionChargeModel.created_at >= start_at,
                    SessionChargeModel.created_at < end_at,
                )
            )
            amount_cents, charge_count = result.one()
            return RevenueSummary(
                start_at=start_at,
                end_at=end_at,
                amount_cents=int(amount_cents),
                charge_count=int(charge_count),
            )


class PostgresChargeReconciliationRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get_by_session_id(self, session_id: uuid.UUID) -> ChargeReconciliation | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ChargeReconciliationModel, session_id)
            return model.to_domain() if model else None

    async def ensure_pending(self, item: ChargeReconciliation) -> ChargeReconciliation:
        async with open_session(self._engine_provider) as db_session:
            async with db_session.begin():
                await db_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"billing-reconciliation:{item.session_id}"},
                )
                await db_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"billing-reconciliation-key:{item.idempotency_key}"},
                )
                existing = await db_session.get(ChargeReconciliationModel, item.session_id)
                if existing is not None:
                    return existing.to_domain()
                existing_by_key = await db_session.scalar(
                    select(ChargeReconciliationModel).where(
                        ChargeReconciliationModel.idempotency_key == item.idempotency_key
                    )
                )
                if existing_by_key is not None:
                    if existing_by_key.session_id != item.session_id:
                        raise ValueError("Idempotency key belongs to another session")
                    return existing_by_key.to_domain()
                db_session.add(ChargeReconciliationModel.from_domain(item))
                return item

    async def save(self, item: ChargeReconciliation) -> ChargeReconciliation:
        async with open_session(self._engine_provider) as db_session:
            async with db_session.begin():
                await db_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"billing-reconciliation:{item.session_id}"},
                )
                await db_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"billing-reconciliation-key:{item.idempotency_key}"},
                )
                existing = await db_session.scalar(
                    select(ChargeReconciliationModel)
                    .where(ChargeReconciliationModel.session_id == item.session_id)
                    .with_for_update()
                )
                if existing is not None and existing.status == ReconciliationStatus.COMPLETED.value:
                    return existing.to_domain()
                existing_by_key = await db_session.scalar(
                    select(ChargeReconciliationModel).where(
                        ChargeReconciliationModel.idempotency_key == item.idempotency_key
                    )
                )
                if existing_by_key is not None and existing_by_key.session_id != item.session_id:
                    raise ValueError("Idempotency key belongs to another session")
                if existing is None:
                    db_session.add(ChargeReconciliationModel.from_domain(item))
                else:
                    existing.idempotency_key = item.idempotency_key
                    existing.charged_by = item.charged_by
                    existing.status = item.status.value
                    existing.attempts = item.attempts
                    existing.next_attempt_at = item.next_attempt_at
                    existing.last_error = item.last_error
                    existing.charge_id = item.charge_id
                    existing.updated_at = item.updated_at
                return item

    async def list_due(
        self,
        now: datetime.datetime,
        limit: int,
    ) -> list[ChargeReconciliation]:
        bounded_limit = max(1, min(limit, 500))
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ChargeReconciliationModel)
                .where(
                    and_(
                        ChargeReconciliationModel.status.in_(
                            [
                                ReconciliationStatus.PENDING.value,
                                ReconciliationStatus.RETRYABLE.value,
                            ]
                        ),
                        ChargeReconciliationModel.next_attempt_at <= now,
                    )
                )
                .order_by(
                    ChargeReconciliationModel.next_attempt_at,
                    ChargeReconciliationModel.created_at,
                )
                .limit(bounded_limit)
            )
            return [model.to_domain() for model in result]

    async def list_recent(self, limit: int) -> list[ChargeReconciliation]:
        bounded_limit = max(1, min(limit, 500))
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(ChargeReconciliationModel)
                .order_by(ChargeReconciliationModel.updated_at.desc())
                .limit(bounded_limit)
            )
            return [model.to_domain() for model in result]
