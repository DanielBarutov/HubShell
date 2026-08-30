import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.domain import (
    CashApproval,
    CashMovement,
    CashShift,
    CashShiftSchedule,
)
from gameclub_backend.presentation.http.auth import require_permissions

CashReader = typing.Annotated[Principal, Depends(require_permissions("cashier.read"))]
CashOperator = typing.Annotated[Principal, Depends(require_permissions("cashier.manage"))]
CashSupervisor = typing.Annotated[Principal, Depends(require_permissions("cashier.supervise"))]


class OpenCashShiftRequest(BaseModel):
    register_id: str = Field(min_length=1, max_length=128)
    opening_balance_cents: int = Field(ge=0)


class CashShiftScheduleRequest(BaseModel):
    register_id: str = Field(min_length=1, max_length=128)
    timezone: str = Field(default="Europe/Moscow", max_length=64)
    auto_open: bool = False
    auto_open_at: datetime.time | None = None
    auto_close: bool = False
    auto_close_at: datetime.time | None = None
    opening_balance_cents: int = Field(default=0, ge=0)


class CashMovementRequest(BaseModel):
    direction: str = Field(min_length=1, max_length=32)
    amount_cents: int
    reason: str = Field(min_length=1, max_length=255)
    reference_type: str | None = Field(default=None, max_length=64)
    reference_id: str | None = Field(default=None, max_length=128)
    approval_id: uuid.UUID | None = None


class CloseCashShiftRequest(BaseModel):
    actual_close_cents: int = Field(ge=0)
    approval_id: uuid.UUID | None = None


class CreateCashApprovalRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=32)
    target_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=255)


class CashShiftResponse(BaseModel):
    id: uuid.UUID
    register_id: str
    opened_by: str
    opened_at: datetime.datetime
    opening_balance_cents: int
    expected_close_cents: int
    status: str
    closed_by: str | None
    closed_at: datetime.datetime | None
    actual_close_cents: int | None
    difference_cents: int | None

    @classmethod
    def from_domain(cls, shift: CashShift) -> "CashShiftResponse":
        return cls(
            id=shift.id,
            register_id=shift.register_id,
            opened_by=shift.opened_by,
            opened_at=shift.opened_at,
            opening_balance_cents=shift.opening_balance_cents,
            expected_close_cents=shift.expected_close_cents,
            status=shift.status.value,
            closed_by=shift.closed_by,
            closed_at=shift.closed_at,
            actual_close_cents=shift.actual_close_cents,
            difference_cents=shift.difference_cents,
        )


class CashShiftScheduleResponse(BaseModel):
    register_id: str
    timezone: str
    auto_open: bool
    auto_open_at: datetime.time | None
    auto_close: bool
    auto_close_at: datetime.time | None
    opening_balance_cents: int

    @classmethod
    def from_domain(cls, schedule: CashShiftSchedule) -> "CashShiftScheduleResponse":
        return cls.model_validate(schedule, from_attributes=True)


class CashMovementResponse(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    direction: str
    amount_cents: int
    reason: str
    actor_id: str
    idempotency_key: str
    created_at: datetime.datetime
    reference_type: str | None
    reference_id: str | None

    @classmethod
    def from_domain(cls, movement: CashMovement) -> "CashMovementResponse":
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


class CashApprovalResponse(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    kind: str
    target_key: str
    approved_by: str
    reason: str
    idempotency_key: str
    created_at: datetime.datetime

    @classmethod
    def from_domain(cls, approval: CashApproval) -> "CashApprovalResponse":
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


def create_router(service: CashShiftService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/cash-shifts", tags=["cash-shifts"])

    @router.get("", response_model=list[CashShiftResponse])
    async def list_shifts(
        principal: CashReader,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[CashShiftResponse]:
        del principal
        return [CashShiftResponse.from_domain(item) for item in await service.list(limit)]

    @router.get("/schedules", response_model=list[CashShiftScheduleResponse])
    async def list_schedules(principal: CashReader) -> list[CashShiftScheduleResponse]:
        del principal
        schedules = await service.list_schedules()
        return [CashShiftScheduleResponse.from_domain(item) for item in schedules]

    @router.put("/schedules/{register_id}", response_model=CashShiftScheduleResponse)
    async def save_schedule(
        register_id: str,
        body: CashShiftScheduleRequest,
        principal: CashOperator,
    ) -> CashShiftScheduleResponse:
        del principal
        schedule = await service.save_schedule(
            register_id=register_id,
            **body.model_dump(exclude={"register_id"}),
        )
        return CashShiftScheduleResponse.from_domain(schedule)

    @router.post("", response_model=CashShiftResponse, status_code=status.HTTP_201_CREATED)
    async def open_shift(
        body: OpenCashShiftRequest,
        principal: CashOperator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> CashShiftResponse:
        shift = await service.open(
            opened_by=principal.subject_id,
            idempotency_key=idempotency_key,
            **body.model_dump(),
        )
        return CashShiftResponse.from_domain(shift)

    @router.get("/{shift_id}", response_model=CashShiftResponse)
    async def get_shift(shift_id: uuid.UUID, principal: CashReader) -> CashShiftResponse:
        del principal
        return CashShiftResponse.from_domain(await service.get(shift_id))

    @router.get("/{shift_id}/movements", response_model=list[CashMovementResponse])
    async def list_movements(
        shift_id: uuid.UUID,
        principal: CashReader,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[CashMovementResponse]:
        del principal
        movements = await service.list_movements(shift_id, limit)
        return [CashMovementResponse.from_domain(item) for item in movements]

    @router.post(
        "/{shift_id}/movements",
        response_model=CashMovementResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def record_movement(
        shift_id: uuid.UUID,
        body: CashMovementRequest,
        principal: CashOperator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> CashMovementResponse:
        if body.direction.strip().lower() == "correction" and not principal.can("cashier.correct"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cash corrections require cashier.correct permission",
            )
        _, movement = await service.record_movement(
            shift_id=shift_id,
            actor_id=principal.subject_id,
            idempotency_key=idempotency_key,
            approval_id=body.approval_id,
            **body.model_dump(exclude={"approval_id"}),
        )
        return CashMovementResponse.from_domain(movement)

    @router.post("/{shift_id}/close", response_model=CashShiftResponse)
    async def close_shift(
        shift_id: uuid.UUID,
        body: CloseCashShiftRequest,
        principal: CashOperator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> CashShiftResponse:
        current = await service.get(shift_id)
        if body.approval_id is not None and not principal.can("cashier.supervise"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cash approval requires cashier.supervise permission",
            )
        if current.expected_close_cents != body.actual_close_cents:
            if not principal.can("cashier.supervise"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Closing a shift with a difference requires supervisor approval",
                )
            if body.approval_id is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Closing a shift with a difference requires supervisor approval",
                )
        shift = await service.close(
            shift_id=shift_id,
            closed_by=principal.subject_id,
            idempotency_key=idempotency_key,
            actual_close_cents=body.actual_close_cents,
            approval_id=body.approval_id,
        )
        return CashShiftResponse.from_domain(shift)

    @router.post(
        "/{shift_id}/approvals",
        response_model=CashApprovalResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_approval(
        shift_id: uuid.UUID,
        body: CreateCashApprovalRequest,
        principal: CashSupervisor,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> CashApprovalResponse:
        approval = await service.approve(
            shift_id=shift_id,
            kind=body.kind,
            target_key=body.target_key,
            approved_by=principal.subject_id,
            reason=body.reason,
            idempotency_key=idempotency_key,
        )
        return CashApprovalResponse.from_domain(approval)

    return router
