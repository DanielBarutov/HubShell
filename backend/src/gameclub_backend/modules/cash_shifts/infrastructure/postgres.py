from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Index, String, Time, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.cash_shifts.domain import (
    CashApproval,
    CashApprovalKind,
    CashMovement,
    CashMovementDirection,
    CashShift,
    CashShiftSchedule,
    CashShiftStatus,
)


class CashShiftBase(DeclarativeBase):
    pass


class CashShiftModel(CashShiftBase):
    __tablename__ = "cash_shifts"
    __table_args__ = (
        Index(
            "uq_cash_shifts_open_register_id",
            "register_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    register_id: Mapped[str] = mapped_column(String(128), index=True)
    opened_by: Mapped[str] = mapped_column(String(128))
    opened_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    opening_balance_cents: Mapped[int] = mapped_column()
    expected_close_cents: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(32), index=True)
    open_idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    closed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    closed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_close_cents: Mapped[int | None] = mapped_column(nullable=True)
    difference_cents: Mapped[int | None] = mapped_column(nullable=True)
    close_idempotency_key: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )

    def to_domain(self) -> CashShift:
        return CashShift(
            id=self.id,
            register_id=self.register_id,
            opened_by=self.opened_by,
            opened_at=self.opened_at,
            opening_balance_cents=self.opening_balance_cents,
            expected_close_cents=self.expected_close_cents,
            status=CashShiftStatus(self.status),
            open_idempotency_key=self.open_idempotency_key,
            closed_by=self.closed_by,
            closed_at=self.closed_at,
            actual_close_cents=self.actual_close_cents,
            difference_cents=self.difference_cents,
            close_idempotency_key=self.close_idempotency_key,
        )

    @classmethod
    def from_domain(cls, shift: CashShift) -> CashShiftModel:
        return cls(
            id=shift.id,
            register_id=shift.register_id,
            opened_by=shift.opened_by,
            opened_at=shift.opened_at,
            opening_balance_cents=shift.opening_balance_cents,
            expected_close_cents=shift.expected_close_cents,
            status=shift.status.value,
            open_idempotency_key=shift.open_idempotency_key,
            closed_by=shift.closed_by,
            closed_at=shift.closed_at,
            actual_close_cents=shift.actual_close_cents,
            difference_cents=shift.difference_cents,
            close_idempotency_key=shift.close_idempotency_key,
        )


class CashShiftScheduleModel(CashShiftBase):
    __tablename__ = "cash_shift_schedules"

    register_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    auto_open: Mapped[bool] = mapped_column(default=False)
    auto_open_at: Mapped[datetime.time | None] = mapped_column(Time(), nullable=True)
    auto_close: Mapped[bool] = mapped_column(default=False)
    auto_close_at: Mapped[datetime.time | None] = mapped_column(Time(), nullable=True)
    opening_balance_cents: Mapped[int] = mapped_column(default=0)

    def to_domain(self) -> CashShiftSchedule:
        return CashShiftSchedule(
            register_id=self.register_id,
            timezone=self.timezone,
            auto_open=self.auto_open,
            auto_open_at=self.auto_open_at,
            auto_close=self.auto_close,
            auto_close_at=self.auto_close_at,
            opening_balance_cents=self.opening_balance_cents,
        )

    @classmethod
    def from_domain(cls, schedule: CashShiftSchedule) -> CashShiftScheduleModel:
        return cls(
            register_id=schedule.register_id,
            timezone=schedule.timezone,
            auto_open=schedule.auto_open,
            auto_open_at=schedule.auto_open_at,
            auto_close=schedule.auto_close,
            auto_close_at=schedule.auto_close_at,
            opening_balance_cents=schedule.opening_balance_cents,
        )


class CashMovementModel(CashShiftBase):
    __tablename__ = "cash_movements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    direction: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(String(255))
    actor_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def to_domain(self) -> CashMovement:
        return CashMovement(
            id=self.id,
            shift_id=self.shift_id,
            direction=CashMovementDirection(self.direction),
            amount_cents=self.amount_cents,
            reason=self.reason,
            actor_id=self.actor_id,
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
            reference_type=self.reference_type,
            reference_id=self.reference_id,
        )

    @classmethod
    def from_domain(cls, movement: CashMovement) -> CashMovementModel:
        return cls(
            id=movement.id,
            shift_id=movement.shift_id,
            direction=movement.direction.value,
            amount_cents=movement.amount_cents,
            reason=movement.reason,
            actor_id=movement.actor_id,
            idempotency_key=movement.idempotency_key,
            created_at=movement.created_at,
            reference_type=movement.reference_type,
            reference_id=movement.reference_id,
        )


class CashApprovalModel(CashShiftBase):
    __tablename__ = "cash_approvals"
    __table_args__ = (
        Index(
            "uq_cash_approvals_target",
            "shift_id",
            "kind",
            "target_key",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    target_key: Mapped[str] = mapped_column(String(128))
    approved_by: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> CashApproval:
        return CashApproval(
            id=self.id,
            shift_id=self.shift_id,
            kind=CashApprovalKind(self.kind),
            target_key=self.target_key,
            approved_by=self.approved_by,
            reason=self.reason,
            idempotency_key=self.idempotency_key,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, approval: CashApproval) -> CashApprovalModel:
        return cls(
            id=approval.id,
            shift_id=approval.shift_id,
            kind=approval.kind.value,
            target_key=approval.target_key,
            approved_by=approval.approved_by,
            reason=approval.reason,
            idempotency_key=approval.idempotency_key,
            created_at=approval.created_at,
        )


class PostgresCashShiftRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get_schedule(self, register_id: str) -> CashShiftSchedule | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(CashShiftScheduleModel, register_id)
            return model.to_domain() if model else None

    async def list_schedules(self) -> list[CashShiftSchedule]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(CashShiftScheduleModel).order_by(CashShiftScheduleModel.register_id)
            )
            return [model.to_domain() for model in result]

    async def save_schedule(self, schedule: CashShiftSchedule) -> CashShiftSchedule:
        async with open_session(self._engine_provider) as session:
            model = await session.get(CashShiftScheduleModel, schedule.register_id)
            if model is None:
                session.add(CashShiftScheduleModel.from_domain(schedule))
            else:
                model.timezone = schedule.timezone
                model.auto_open = schedule.auto_open
                model.auto_open_at = schedule.auto_open_at
                model.auto_close = schedule.auto_close
                model.auto_close_at = schedule.auto_close_at
                model.opening_balance_cents = schedule.opening_balance_cents
            await session.commit()
            return schedule

    async def get(self, shift_id: uuid.UUID) -> CashShift | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(CashShiftModel, shift_id)
            return model.to_domain() if model else None

    async def get_by_open_key(self, idempotency_key: str) -> CashShift | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(CashShiftModel).where(CashShiftModel.open_idempotency_key == idempotency_key)
            )
            return model.to_domain() if model else None

    async def get_open(self, register_id: str) -> CashShift | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(CashShiftModel).where(
                    CashShiftModel.register_id == register_id,
                    CashShiftModel.status == CashShiftStatus.OPEN.value,
                )
            )
            return model.to_domain() if model else None

    async def list_shifts(self, limit: int) -> list[CashShift]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(CashShiftModel).order_by(CashShiftModel.opened_at.desc()).limit(limit)
            )
            return [model.to_domain() for model in result]

    async def list_movements(self, shift_id: uuid.UUID, limit: int) -> list[CashMovement]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(CashMovementModel)
                .where(CashMovementModel.shift_id == shift_id)
                .order_by(CashMovementModel.created_at.desc())
                .limit(limit)
            )
            return [model.to_domain() for model in result]

    async def get_movement_by_key(self, idempotency_key: str) -> CashMovement | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(CashMovementModel).where(
                    CashMovementModel.idempotency_key == idempotency_key
                )
            )
            return model.to_domain() if model else None

    async def open_shift(self, shift: CashShift) -> CashShift:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"cash-register:{shift.register_id}"},
                )
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"cash-open-key:{shift.open_idempotency_key}"},
                )
                existing = await session.scalar(
                    select(CashShiftModel).where(
                        CashShiftModel.open_idempotency_key == shift.open_idempotency_key
                    )
                )
                if existing is not None:
                    if existing.register_id != shift.register_id:
                        raise ValueError("Opening key belongs to another shift")
                    return existing.to_domain()
                current = await session.scalar(
                    select(CashShiftModel)
                    .where(
                        CashShiftModel.register_id == shift.register_id,
                        CashShiftModel.status == CashShiftStatus.OPEN.value,
                    )
                    .with_for_update()
                )
                if current is not None:
                    raise ValueError("Cash register already has an open shift")
                session.add(CashShiftModel.from_domain(shift))
                return shift

    async def record_movement(
        self,
        shift_id: uuid.UUID,
        movement: CashMovement,
    ) -> tuple[CashShift, CashMovement]:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"cash-shift:{shift_id}"},
                )
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"cash-movement-key:{movement.idempotency_key}"},
                )
                if movement.reference_type and movement.reference_id:
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                        {
                            "lock_key": (
                                f"cash-reference:{movement.reference_type}:{movement.reference_id}"
                            )
                        },
                    )
                existing = await session.scalar(
                    select(CashMovementModel).where(
                        CashMovementModel.idempotency_key == movement.idempotency_key
                    )
                )
                if existing is not None:
                    if existing.shift_id != shift_id:
                        raise ValueError("Movement key belongs to another shift")
                    shift = await session.get(CashShiftModel, shift_id)
                    if shift is None:
                        raise ValueError("Cash shift not found")
                    return shift.to_domain(), existing.to_domain()
                if movement.reference_type and movement.reference_id:
                    existing_reference = await session.scalar(
                        select(CashMovementModel).where(
                            CashMovementModel.reference_type == movement.reference_type,
                            CashMovementModel.reference_id == movement.reference_id,
                        )
                    )
                    if existing_reference is not None:
                        raise ValueError("Cash reference has already been recorded")
                shift_model = await session.scalar(
                    select(CashShiftModel).where(CashShiftModel.id == shift_id).with_for_update()
                )
                if shift_model is None:
                    raise ValueError("Cash shift not found")
                updated = shift_model.to_domain().record(movement)
                shift_model.expected_close_cents = updated.expected_close_cents
                session.add(CashMovementModel.from_domain(movement))
                return updated, movement

    async def close_shift(
        self,
        shift_id: uuid.UUID,
        actual_close_cents: int,
        closed_by: str,
        idempotency_key: str,
        now: datetime.datetime,
        expected_close_cents: int,
    ) -> CashShift:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"cash-shift:{shift_id}"},
                )
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"cash-close-key:{idempotency_key}"},
                )
                shift_model = await session.scalar(
                    select(CashShiftModel).where(CashShiftModel.id == shift_id).with_for_update()
                )
                if shift_model is None:
                    raise ValueError("Cash shift not found")
                current = shift_model.to_domain()
                if current.status is CashShiftStatus.CLOSED:
                    if current.close_idempotency_key == idempotency_key:
                        return current
                    raise ValueError("Cash shift is already closed")
                if current.expected_close_cents != expected_close_cents:
                    raise ValueError("Cash shift changed; retry closing with a fresh count")
                closed = current.close(actual_close_cents, closed_by, idempotency_key, now)
                shift_model.status = closed.status.value
                shift_model.closed_by = closed.closed_by
                shift_model.closed_at = closed.closed_at
                shift_model.actual_close_cents = closed.actual_close_cents
                shift_model.difference_cents = closed.difference_cents
                shift_model.close_idempotency_key = closed.close_idempotency_key
                return closed


class PostgresCashApprovalRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, approval_id: uuid.UUID) -> CashApproval | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(CashApprovalModel, approval_id)
            return model.to_domain() if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> CashApproval | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(CashApprovalModel).where(
                    CashApprovalModel.idempotency_key == idempotency_key
                )
            )
            return model.to_domain() if model else None

    async def get_by_target(
        self,
        shift_id: uuid.UUID,
        kind: str,
        target_key: str,
    ) -> CashApproval | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(CashApprovalModel).where(
                    CashApprovalModel.shift_id == shift_id,
                    CashApprovalModel.kind == kind,
                    CashApprovalModel.target_key == target_key,
                )
            )
            return model.to_domain() if model else None

    async def save(self, approval: CashApproval) -> CashApproval:
        async with open_session(self._engine_provider) as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"cash-approval:{approval.shift_id}:{approval.target_key}"},
                )
                existing = await session.scalar(
                    select(CashApprovalModel).where(
                        CashApprovalModel.idempotency_key == approval.idempotency_key
                    )
                )
                if existing is not None:
                    if (
                        existing.shift_id != approval.shift_id
                        or existing.kind != approval.kind.value
                    ):
                        raise ValueError("Approval key belongs to another operation")
                    return existing.to_domain()
                target = await session.scalar(
                    select(CashApprovalModel).where(
                        CashApprovalModel.shift_id == approval.shift_id,
                        CashApprovalModel.kind == approval.kind.value,
                        CashApprovalModel.target_key == approval.target_key,
                    )
                )
                if target is not None:
                    raise ValueError("Approval already exists for this operation")
                session.add(CashApprovalModel.from_domain(approval))
                return approval
