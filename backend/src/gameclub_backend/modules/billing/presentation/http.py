import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.domain import (
    ChargeReconciliation,
    MeterStatus,
    SessionCharge,
    SessionMeter,
)
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("billing.manage"))]


class SessionChargeResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    client_id: uuid.UUID
    balance_operation_id: uuid.UUID
    tariff_id: uuid.UUID
    duration_minutes: int
    amount_cents: int
    amount_before_discount_cents: int
    discount_amount_cents: int
    discount_percent_bps: int
    discount_category: str | None
    charged_by: str
    idempotency_key: str
    created_at: str
    client_balance_cents: int
    client_balance_bonus: int


class SessionMeterResponse(BaseModel):
    session_id: uuid.UUID
    client_id: uuid.UUID
    tariff_id: uuid.UUID
    billed_minutes: int
    billed_cents: int
    status: MeterStatus
    updated_at: str

    @classmethod
    def from_domain(cls, meter: SessionMeter) -> "SessionMeterResponse":
        return cls(
            session_id=meter.session_id,
            client_id=meter.client_id,
            tariff_id=meter.tariff_id,
            billed_minutes=meter.billed_minutes,
            billed_cents=meter.billed_cents,
            status=meter.status,
            updated_at=meter.updated_at.isoformat(),
        )


class ReconciliationResponse(BaseModel):
    session_id: uuid.UUID
    idempotency_key: str
    charged_by: str
    status: str
    attempts: int
    next_attempt_at: str
    last_error: str | None
    charge_id: uuid.UUID | None
    created_at: str
    updated_at: str


class RevenueResponse(BaseModel):
    start_at: str
    end_at: str
    amount_cents: int
    charge_count: int


QueryDatetime = typing.Annotated[datetime.datetime, Query()]


def to_response(
    charge: SessionCharge, balance_cents: int, balance_bonus: int
) -> SessionChargeResponse:
    return SessionChargeResponse(
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
        created_at=charge.created_at.isoformat(),
        client_balance_cents=balance_cents,
        client_balance_bonus=balance_bonus,
    )


def to_reconciliation_response(item: ChargeReconciliation) -> ReconciliationResponse:
    return ReconciliationResponse(
        session_id=item.session_id,
        idempotency_key=item.idempotency_key,
        charged_by=item.charged_by,
        status=item.status.value,
        attempts=item.attempts,
        next_attempt_at=item.next_attempt_at.isoformat(),
        last_error=item.last_error,
        charge_id=item.charge_id,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


def create_router(service: BillingService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

    @router.post("/sessions/{session_id}/charge", response_model=SessionChargeResponse)
    async def charge_session(
        session_id: uuid.UUID,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> SessionChargeResponse:
        charge, client = await service.charge_session(
            session_id=session_id,
            charged_by=principal.subject_id,
            idempotency_key=idempotency_key,
        )
        return to_response(charge, client.balance_cents, client.balance_bonus)

    @router.get("/sessions/{session_id}/charge", response_model=SessionChargeResponse)
    async def get_session_charge(
        session_id: uuid.UUID,
        principal: Operator,
    ) -> SessionChargeResponse:
        del principal
        charge, client = await service.get_session_charge(session_id)
        return to_response(charge, client.balance_cents, client.balance_bonus)

    @router.get("/sessions/{session_id}/meter", response_model=SessionMeterResponse)
    async def get_session_meter(
        session_id: uuid.UUID,
        principal: Operator,
    ) -> SessionMeterResponse:
        del principal
        return SessionMeterResponse.from_domain(await service.get_meter(session_id))

    @router.get("/reconciliation", response_model=list[ReconciliationResponse])
    async def list_reconciliation(
        principal: Operator,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> list[ReconciliationResponse]:
        del principal
        items = await service.list_reconciliation(limit)
        return [to_reconciliation_response(item) for item in items]

    @router.post(
        "/reconciliation/{session_id}/retry",
        response_model=ReconciliationResponse,
    )
    async def retry_reconciliation(
        session_id: uuid.UUID,
        principal: typing.Annotated[
            Principal,
            Depends(require_permissions("billing.manage", "cashier.supervise")),
        ],
    ) -> ReconciliationResponse:
        return to_reconciliation_response(
            await service.retry_reconciliation(session_id, principal.subject_id)
        )

    @router.get("/revenue", response_model=RevenueResponse)
    async def revenue(
        principal: typing.Annotated[
            Principal,
            Depends(require_permissions("dashboard.read")),
        ],
        start_at: QueryDatetime,
        end_at: QueryDatetime,
    ) -> RevenueResponse:
        del principal
        summary = await service.revenue_between(start_at, end_at)
        return RevenueResponse(
            start_at=summary.start_at.isoformat(),
            end_at=summary.end_at.isoformat(),
            amount_cents=summary.amount_cents,
            charge_count=summary.charge_count,
        )

    return router
