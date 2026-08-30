import datetime
import typing
import uuid

from gameclub_backend.modules.cash_shifts.domain import (
    CashApproval,
    CashMovement,
    CashShift,
    CashShiftSchedule,
)


class CashShiftRepository(typing.Protocol):
    async def get_schedule(self, register_id: str) -> CashShiftSchedule | None:
        """Return automatic opening and closing settings for a register."""

    async def list_schedules(self) -> list[CashShiftSchedule]:
        """Return all automatic shift schedules."""

    async def save_schedule(self, schedule: CashShiftSchedule) -> CashShiftSchedule:
        """Persist a register schedule."""

    async def get(self, shift_id: uuid.UUID) -> CashShift | None:
        """Return a cash shift by ID."""

    async def get_by_open_key(self, idempotency_key: str) -> CashShift | None:
        """Return a shift opened by the same idempotency key."""

    async def get_open(self, register_id: str) -> CashShift | None:
        """Return the active shift for a cash register."""

    async def list_shifts(self, limit: int) -> list[CashShift]:
        """Return recent shifts."""

    async def list_movements(self, shift_id: uuid.UUID, limit: int) -> list[CashMovement]:
        """Return recent movements for a shift."""

    async def get_movement_by_key(self, idempotency_key: str) -> CashMovement | None:
        """Return a movement by its idempotency key."""

    async def open_shift(self, shift: CashShift) -> CashShift:
        """Open a shift atomically and enforce one open shift per register."""

    async def record_movement(
        self,
        shift_id: uuid.UUID,
        movement: CashMovement,
    ) -> tuple[CashShift, CashMovement]:
        """Record one movement and update expected cash atomically."""

    async def close_shift(
        self,
        shift_id: uuid.UUID,
        actual_close_cents: int,
        closed_by: str,
        idempotency_key: str,
        now: datetime.datetime,
        expected_close_cents: int,
    ) -> CashShift:
        """Close atomically if the expected balance has not changed since the read."""


class CashApprovalRepository(typing.Protocol):
    async def get(self, approval_id: uuid.UUID) -> CashApproval | None:
        """Return an approval by ID."""

    async def get_by_idempotency_key(self, idempotency_key: str) -> CashApproval | None:
        """Return an approval by its idempotency key."""

    async def get_by_target(
        self,
        shift_id: uuid.UUID,
        kind: str,
        target_key: str,
    ) -> CashApproval | None:
        """Return an approval for one risk operation."""

    async def save(self, approval: CashApproval) -> CashApproval:
        """Persist one immutable approval."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
