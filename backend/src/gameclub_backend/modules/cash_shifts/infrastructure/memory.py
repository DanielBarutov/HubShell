import asyncio
import datetime
import uuid

from gameclub_backend.modules.cash_shifts.domain import (
    CashApproval,
    CashMovement,
    CashShift,
    CashShiftSchedule,
    CashShiftStatus,
)


class InMemoryCashShiftRepository:
    def __init__(self) -> None:
        self._shifts: dict[uuid.UUID, CashShift] = {}
        self._movements: dict[uuid.UUID, CashMovement] = {}
        self._open_keys: dict[str, uuid.UUID] = {}
        self._movement_keys: dict[str, uuid.UUID] = {}
        self._reference_keys: dict[tuple[str, str], uuid.UUID] = {}
        self._lock = asyncio.Lock()
        self._schedules: dict[str, CashShiftSchedule] = {}

    async def get_schedule(self, register_id: str) -> CashShiftSchedule | None:
        return self._schedules.get(register_id)

    async def list_schedules(self) -> list[CashShiftSchedule]:
        return list(self._schedules.values())

    async def save_schedule(self, schedule: CashShiftSchedule) -> CashShiftSchedule:
        self._schedules[schedule.register_id] = schedule
        return schedule

    async def get(self, shift_id: uuid.UUID) -> CashShift | None:
        return self._shifts.get(shift_id)

    async def get_by_open_key(self, idempotency_key: str) -> CashShift | None:
        shift_id = self._open_keys.get(idempotency_key)
        return self._shifts.get(shift_id) if shift_id else None

    async def get_open(self, register_id: str) -> CashShift | None:
        return next(
            (
                shift
                for shift in self._shifts.values()
                if shift.register_id == register_id and shift.status is CashShiftStatus.OPEN
            ),
            None,
        )

    async def list_shifts(self, limit: int) -> list[CashShift]:
        items = sorted(self._shifts.values(), key=lambda item: item.opened_at, reverse=True)
        return items[:limit]

    async def list_movements(self, shift_id: uuid.UUID, limit: int) -> list[CashMovement]:
        items = [item for item in self._movements.values() if item.shift_id == shift_id]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[:limit]

    async def get_movement_by_key(self, idempotency_key: str) -> CashMovement | None:
        movement_id = self._movement_keys.get(idempotency_key)
        return self._movements.get(movement_id) if movement_id else None

    async def open_shift(self, shift: CashShift) -> CashShift:
        async with self._lock:
            existing = await self.get_by_open_key(shift.open_idempotency_key)
            if existing is not None:
                if existing.register_id != shift.register_id:
                    raise ValueError("Opening key belongs to another shift")
                return existing
            current = await self.get_open(shift.register_id)
            if current is not None:
                raise ValueError("Cash register already has an open shift")
            self._shifts[shift.id] = shift
            self._open_keys[shift.open_idempotency_key] = shift.id
            return shift

    async def record_movement(
        self,
        shift_id: uuid.UUID,
        movement: CashMovement,
    ) -> tuple[CashShift, CashMovement]:
        async with self._lock:
            existing_id = self._movement_keys.get(movement.idempotency_key)
            if existing_id is not None:
                existing = self._movements[existing_id]
                if existing.shift_id != shift_id:
                    raise ValueError("Movement key belongs to another shift")
                return self._shifts[shift_id], existing
            current = self._shifts.get(shift_id)
            if current is None:
                raise ValueError("Cash shift not found")
            if movement.reference_type and movement.reference_id:
                reference_key = (movement.reference_type, movement.reference_id)
                existing_reference_id = self._reference_keys.get(reference_key)
                if existing_reference_id is not None:
                    raise ValueError("Cash reference has already been recorded")
            updated = current.record(movement)
            self._shifts[shift_id] = updated
            self._movements[movement.id] = movement
            self._movement_keys[movement.idempotency_key] = movement.id
            if movement.reference_type and movement.reference_id:
                self._reference_keys[(movement.reference_type, movement.reference_id)] = movement.id
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
        async with self._lock:
            current = self._shifts.get(shift_id)
            if current is None:
                raise ValueError("Cash shift not found")
            if current.status is CashShiftStatus.CLOSED:
                if current.close_idempotency_key == idempotency_key:
                    return current
                raise ValueError("Cash shift is already closed")
            if current.expected_close_cents != expected_close_cents:
                raise ValueError("Cash shift changed; retry closing with a fresh count")
            closed = current.close(actual_close_cents, closed_by, idempotency_key, now)
            self._shifts[shift_id] = closed
            return closed


class InMemoryCashApprovalRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, CashApproval] = {}
        self._idempotency: dict[str, uuid.UUID] = {}
        self._targets: dict[tuple[uuid.UUID, str, str], uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get(self, approval_id: uuid.UUID) -> CashApproval | None:
        return self._items.get(approval_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> CashApproval | None:
        approval_id = self._idempotency.get(idempotency_key)
        return self._items.get(approval_id) if approval_id else None

    async def get_by_target(
        self,
        shift_id: uuid.UUID,
        kind: str,
        target_key: str,
    ) -> CashApproval | None:
        approval_id = self._targets.get((shift_id, kind, target_key))
        return self._items.get(approval_id) if approval_id else None

    async def save(self, approval: CashApproval) -> CashApproval:
        async with self._lock:
            existing = await self.get_by_idempotency_key(approval.idempotency_key)
            if existing is not None:
                if existing.shift_id != approval.shift_id or existing.kind is not approval.kind:
                    raise ValueError("Approval key belongs to another operation")
                return existing
            target = await self.get_by_target(
                approval.shift_id,
                approval.kind.value,
                approval.target_key,
            )
            if target is not None:
                raise ValueError("Approval already exists for this operation")
            self._items[approval.id] = approval
            self._idempotency[approval.idempotency_key] = approval.id
            self._targets[(approval.shift_id, approval.kind.value, approval.target_key)] = (
                approval.id
            )
            return approval
