import typing
import uuid

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.direct_payments.application.xbox import XboxService
from gameclub_backend.modules.direct_payments.presentation.http import (
    GuestSessionPaymentResponse,
    PaymentPartRequest,
)
from gameclub_backend.modules.sessions.presentation.http import SessionResponse
from gameclub_backend.presentation.http.auth import require_permissions


class XboxStopResponse(SessionResponse):
    relay_off_pending: bool = False


class XboxSaleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workstation_id: uuid.UUID
    tariff_id: uuid.UUID
    session_id: uuid.UUID | None = None
    cash_shift_id: uuid.UUID | None = None
    payment_parts: list[PaymentPartRequest]


def create_router(service: XboxService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/xbox", tags=["xbox"])

    @router.post("/sales", response_model=GuestSessionPaymentResponse)
    async def sell(
        body: XboxSaleRequest,
        principal: typing.Annotated[
            Principal, Depends(require_permissions("sales.manage", "sessions.manage"))
        ],
        idempotency_key: str = Header(min_length=1, max_length=128, alias="Idempotency-Key"),
    ) -> GuestSessionPaymentResponse:
        payment = await service.sell(
            **body.model_dump(exclude={"payment_parts"}),
            payment_parts=[part.model_dump() for part in body.payment_parts],
            actor_id=principal.subject_id,
            idempotency_key=idempotency_key,
        )
        return GuestSessionPaymentResponse.from_domain(payment)

    @router.post("/sessions/{session_id}/stop", response_model=XboxStopResponse)
    async def stop(
        session_id: uuid.UUID,
        principal: typing.Annotated[Principal, Depends(require_permissions("sessions.manage"))],
    ) -> XboxStopResponse:
        session = await service.stop(session_id, principal.subject_id)
        warnings = await service.relay_warnings()
        return XboxStopResponse(
            **SessionResponse.from_domain(session).model_dump(),
            relay_off_pending=any(item.session_id == session_id for item in warnings),
        )

    return router
