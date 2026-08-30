from __future__ import annotations

import datetime
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.cash_shifts.application.ports import (
    CashApprovalRepository,
    CashShiftRepository,
    Clock,
)
from gameclub_backend.modules.cash_shifts.domain import (
    CashApproval,
    CashApprovalKind,
    CashMovement,
    CashMovementDirection,
    CashShift,
    CashShiftSchedule,
    CashShiftStatus,
    normalize_cash_reference,
)


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class CashShiftService:
    def __init__(
        self,
        repository: CashShiftRepository,
        clock: Clock | None = None,
        approvals: CashApprovalRepository | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()
        self._approvals = approvals

    async def open(
        self,
        register_id: str,
        opening_balance_cents: int,
        opened_by: str,
        idempotency_key: str,
    ) -> CashShift:
        normalized_register = register_id.strip()
        normalized_key = self._required_key(idempotency_key, "Opening idempotency key")
        existing = await self._repository.get_by_open_key(normalized_key)
        if existing is not None:
            if (
                existing.register_id != normalized_register
                or existing.opening_balance_cents != opening_balance_cents
                or existing.opened_by != opened_by.strip()
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Opening key belongs to another shift")
            return existing
        if await self._repository.get_open(normalized_register) is not None:
            raise ApplicationError(ErrorCode.CONFLICT, "Cash register already has an open shift")
        now = self._clock.now()
        try:
            shift = CashShift(
                id=uuid.uuid4(),
                register_id=normalized_register,
                opened_by=opened_by,
                opened_at=now,
                opening_balance_cents=opening_balance_cents,
                expected_close_cents=opening_balance_cents,
                status=CashShiftStatus.OPEN,
                open_idempotency_key=normalized_key,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        try:
            saved = await self._repository.open_shift(shift)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if (
            saved.register_id != shift.register_id
            or saved.opening_balance_cents != shift.opening_balance_cents
            or saved.opened_by != shift.opened_by
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Opening key belongs to another shift")
        return saved

    async def get(self, shift_id: uuid.UUID) -> CashShift:
        shift = await self._repository.get(shift_id)
        if shift is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Cash shift not found")
        return shift

    async def approve(
        self,
        shift_id: uuid.UUID,
        kind: str,
        target_key: str,
        approved_by: str,
        reason: str,
        idempotency_key: str,
    ) -> CashApproval:
        if self._approvals is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Cash approval repository is not configured",
            )
        try:
            approval_kind = CashApprovalKind(kind.strip().lower())
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Unknown approval kind") from error
        normalized_key = self._required_key(idempotency_key, "Approval idempotency key")
        normalized_target = target_key.strip()
        existing = await self._approvals.get_by_idempotency_key(normalized_key)
        if existing is not None:
            if (
                existing.shift_id != shift_id
                or existing.kind is not approval_kind
                or existing.target_key != normalized_target
                or existing.approved_by != approved_by.strip()
                or existing.reason != reason.strip()
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Approval key belongs to another operation"
                )
            return existing
        await self.get(shift_id)
        if await self._approvals.get_by_target(shift_id, approval_kind.value, normalized_target):
            raise ApplicationError(ErrorCode.CONFLICT, "Approval already exists for this operation")
        try:
            approval = CashApproval(
                id=uuid.uuid4(),
                shift_id=shift_id,
                kind=approval_kind,
                target_key=normalized_target,
                approved_by=approved_by,
                reason=reason,
                idempotency_key=normalized_key,
                created_at=self._clock.now(),
            )
            saved = await self._approvals.save(approval)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if (
            saved.shift_id != approval.shift_id
            or saved.kind is not approval.kind
            or saved.target_key != approval.target_key
            or saved.approved_by != approval.approved_by
            or saved.reason != approval.reason
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Approval key belongs to another operation")
        return saved

    async def require_approval(
        self,
        approval_id: uuid.UUID,
        shift_id: uuid.UUID,
        kind: str,
        target_key: str,
    ) -> CashApproval:
        if self._approvals is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Cash approval repository is not configured",
            )
        approval = await self._approvals.get(approval_id)
        if approval is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Cash approval not found")
        if (
            approval.shift_id != shift_id
            or approval.kind.value != kind.strip().lower()
            or approval.target_key != target_key.strip()
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Cash approval does not match operation")
        return approval

    async def list(self, limit: int = 50) -> list[CashShift]:
        return await self._repository.list_shifts(max(1, min(limit, 100)))

    async def list_schedules(self) -> list[CashShiftSchedule]:
        return await self._repository.list_schedules()

    async def save_schedule(
        self,
        register_id: str,
        timezone: str,
        auto_open: bool,
        auto_open_at: datetime.time | None,
        auto_close: bool,
        auto_close_at: datetime.time | None,
        opening_balance_cents: int,
    ) -> CashShiftSchedule:
        try:
            ZoneInfo(timezone)
            schedule = CashShiftSchedule(
                register_id=register_id.strip(),
                timezone=timezone.strip(),
                auto_open=auto_open,
                auto_open_at=auto_open_at,
                auto_close=auto_close,
                auto_close_at=auto_close_at,
                opening_balance_cents=opening_balance_cents,
            )
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save_schedule(schedule)

    async def run_auto_schedule(self, now: datetime.datetime | None = None) -> int:
        current = now or self._clock.now()
        actions = 0
        for schedule in await self._repository.list_schedules():
            try:
                local_now = current.astimezone(ZoneInfo(schedule.timezone))
            except ZoneInfoNotFoundError:
                continue
            current_time = local_now.time().replace(second=0, microsecond=0)
            scheduled_open_key = f"auto-open:{schedule.register_id}:{local_now.date().isoformat()}"
            shifts = await self._repository.list_shifts(500)
            has_opened_today = any(
                shift.open_idempotency_key == scheduled_open_key for shift in shifts
            )
            if (
                schedule.auto_open
                and schedule.auto_open_at is not None
                and current_time >= schedule.auto_open_at
                and not has_opened_today
            ):
                if await self._repository.get_open(schedule.register_id) is None:
                    await self.open(
                        register_id=schedule.register_id,
                        opening_balance_cents=schedule.opening_balance_cents,
                        opened_by="system:auto",
                        idempotency_key=scheduled_open_key,
                    )
                    actions += 1
            if (
                schedule.auto_close
                and schedule.auto_close_at is not None
                and current_time >= schedule.auto_close_at
            ):
                shift = await self._repository.get_open(schedule.register_id)
                if shift is not None:
                    await self.close(
                        shift_id=shift.id,
                        actual_close_cents=shift.expected_close_cents,
                        closed_by="system:auto",
                        idempotency_key=f"auto-close:{schedule.register_id}:{local_now.date().isoformat()}",
                    )
                    actions += 1
        return actions

    async def list_movements(
        self,
        shift_id: uuid.UUID,
        limit: int = 50,
    ) -> list[CashMovement]:
        await self.get(shift_id)
        return await self._repository.list_movements(shift_id, max(1, min(limit, 100)))

    async def record_movement(
        self,
        shift_id: uuid.UUID,
        direction: str,
        amount_cents: int,
        reason: str,
        actor_id: str,
        idempotency_key: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        approval_id: uuid.UUID | None = None,
    ) -> tuple[CashShift, CashMovement]:
        normalized_key = self._required_key(idempotency_key, "Movement idempotency key")
        try:
            movement_direction = CashMovementDirection(direction.strip().lower())
        except ValueError as error:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Unknown cash movement direction"
            ) from error
        if movement_direction is CashMovementDirection.CORRECTION:
            if approval_id is None:
                raise ApplicationError(
                    ErrorCode.PERMISSION_DENIED,
                    "Cash corrections require supervisor approval",
                )
            await self.require_approval(
                approval_id,
                shift_id,
                CashApprovalKind.CORRECTION.value,
                normalized_key,
            )
        existing = await self._repository.get_movement_by_key(normalized_key)
        if existing is not None:
            if not self._movement_matches(
                existing,
                shift_id=shift_id,
                direction=movement_direction,
                amount_cents=amount_cents,
                reason=reason,
                actor_id=actor_id,
                reference_type=reference_type,
                reference_id=reference_id,
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Movement key belongs to another operation"
                )
            return await self.get(shift_id), existing
        await self.get(shift_id)
        try:
            reference = normalize_cash_reference(reference_type, reference_id)
            movement = CashMovement(
                id=uuid.uuid4(),
                shift_id=shift_id,
                direction=movement_direction,
                amount_cents=amount_cents,
                reason=reason,
                actor_id=actor_id,
                idempotency_key=normalized_key,
                created_at=self._clock.now(),
                reference_type=reference.reference_type if reference else None,
                reference_id=reference.reference_id if reference else None,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        try:
            saved = await self._repository.record_movement(shift_id, movement)
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if not self._movement_matches(
            saved[1],
            shift_id=shift_id,
            direction=movement_direction,
            amount_cents=amount_cents,
            reason=reason,
            actor_id=actor_id,
            reference_type=reference_type,
            reference_id=reference_id,
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Movement key belongs to another operation")
        return saved

    async def close(
        self,
        shift_id: uuid.UUID,
        actual_close_cents: int,
        closed_by: str,
        idempotency_key: str,
        approval_id: uuid.UUID | None = None,
    ) -> CashShift:
        normalized_key = self._required_key(idempotency_key, "Closing idempotency key")
        current = await self.get(shift_id)
        if current.status is CashShiftStatus.CLOSED:
            if current.close_idempotency_key == normalized_key:
                if (
                    current.actual_close_cents != actual_close_cents
                    or current.closed_by != closed_by.strip()
                ):
                    raise ApplicationError(
                        ErrorCode.CONFLICT, "Closing key belongs to another operation"
                    )
                return current
            raise ApplicationError(ErrorCode.CONFLICT, "Cash shift is already closed")
        if current.expected_close_cents != actual_close_cents:
            if approval_id is None:
                raise ApplicationError(
                    ErrorCode.PERMISSION_DENIED,
                    "Closing a shift with a difference requires supervisor approval",
                )
            await self.require_approval(
                approval_id,
                shift_id,
                CashApprovalKind.CLOSE_DIFFERENCE.value,
                normalized_key,
            )
        try:
            saved = await self._repository.close_shift(
                shift_id,
                actual_close_cents,
                closed_by,
                normalized_key,
                self._clock.now(),
                current.expected_close_cents,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        if (
            saved.close_idempotency_key != normalized_key
            or saved.actual_close_cents != actual_close_cents
            or saved.closed_by != closed_by.strip()
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "Closing key belongs to another operation")
        return saved

    @staticmethod
    def _movement_matches(
        movement: CashMovement,
        *,
        shift_id: uuid.UUID,
        direction: CashMovementDirection,
        amount_cents: int,
        reason: str,
        actor_id: str,
        reference_type: str | None,
        reference_id: str | None,
    ) -> bool:
        return (
            movement.shift_id == shift_id
            and movement.direction is direction
            and movement.amount_cents == amount_cents
            and movement.reason == reason.strip()
            and movement.actor_id == actor_id.strip()
            and movement.reference_type == (reference_type.strip() if reference_type else None)
            and movement.reference_id == (reference_id.strip() if reference_id else None)
        )

    @staticmethod
    def _required_key(value: str, label: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, f"{label} is required")
        if len(normalized) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, f"{label} is too long")
        return normalized
