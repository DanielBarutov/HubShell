import typing
import uuid

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.direct_payments.application.service import GuestSessionPaymentService
from gameclub_backend.modules.direct_payments.domain import GuestSessionPayment
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("sales.manage"))]


class PaymentPartRequest(BaseModel):
    method: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=256)


class GuestSessionPaymentRequest(BaseModel):
    workstation_id: uuid.UUID
    tariff_id: uuid.UUID
    tariff_quantity: int = Field(default=1, ge=1, le=100)
    guest_id: uuid.UUID | None = None
    guest_name: str = Field(default="Гость", min_length=1, max_length=128)
    cash_shift_id: uuid.UUID | None = None
    payment_parts: list[PaymentPartRequest] = Field(default_factory=list)


class GuestSessionPaymentResponse(BaseModel):
    id: uuid.UUID
    workstation_id: uuid.UUID
    tariff_id: uuid.UUID
    tariff_quantity: int
    guest_id: uuid.UUID | None
    guest_name: str
    total_price_cents: int
    payment_parts: list[PaymentPartRequest]
    cash_shift_id: uuid.UUID | None
    status: str
    idempotency_key: str
    created_at: str
    attempts: int
    next_attempt_at: str
    settlement_error: str | None

    @classmethod
    def from_domain(cls, payment: GuestSessionPayment) -> "GuestSessionPaymentResponse":
        return cls(
            id=payment.id,
            workstation_id=payment.workstation_id,
            tariff_id=payment.tariff_id,
            tariff_quantity=payment.tariff_quantity,
            guest_id=payment.guest_id,
            guest_name=payment.guest_name,
            total_price_cents=payment.total_price_cents,
            payment_parts=[
                PaymentPartRequest(
                    method=part.method,
                    amount_cents=part.amount_cents,
                    reference=part.reference,
                )
                for part in payment.payment_parts
            ],
            cash_shift_id=payment.cash_shift_id,
            status=payment.status.value,
            idempotency_key=payment.idempotency_key,
            created_at=payment.created_at.isoformat(),
            attempts=payment.attempts,
            next_attempt_at=payment.next_attempt_at.isoformat(),
            settlement_error=payment.settlement_error,
        )


def create_router(service: GuestSessionPaymentService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/guest-payments", tags=["guest-payments"])

    @router.get("/{payment_id}", response_model=GuestSessionPaymentResponse)
    async def get_payment(
        payment_id: uuid.UUID,
        principal: Operator,
    ) -> GuestSessionPaymentResponse:
        del principal
        return GuestSessionPaymentResponse.from_domain(await service.get(payment_id))

    @router.post(
        "",
        response_model=GuestSessionPaymentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def confirm_payment(
        body: GuestSessionPaymentRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> GuestSessionPaymentResponse:
        payment = await service.confirm(
            workstation_id=body.workstation_id,
            tariff_id=body.tariff_id,
            tariff_quantity=body.tariff_quantity,
            guest_id=body.guest_id,
            guest_name=body.guest_name,
            cash_shift_id=body.cash_shift_id,
            payment_parts=[part.model_dump() for part in body.payment_parts],
            actor_id=principal.subject_id,
            idempotency_key=idempotency_key,
        )
        return GuestSessionPaymentResponse.from_domain(payment)

    @router.post(
        "/{payment_id}/retry",
        response_model=GuestSessionPaymentResponse,
    )
    async def retry_payment(
        payment_id: uuid.UUID,
        principal: typing.Annotated[
            Principal,
            Depends(require_permissions("sales.manage", "cashier.supervise")),
        ],
    ) -> GuestSessionPaymentResponse:
        return GuestSessionPaymentResponse.from_domain(
            await service.retry_reconciliation(payment_id, principal.subject_id)
        )

    return router
