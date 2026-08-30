import datetime
import typing
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.payment_methods.application.service import PaymentMethodService
from gameclub_backend.modules.payment_methods.domain import PaymentMethod
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("settings.manage"))]


class PaymentMethodRequest(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)


class PaymentMethodResponse(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    active: bool
    sort_order: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_domain(cls, method: PaymentMethod) -> "PaymentMethodResponse":
        return cls.model_validate(method, from_attributes=True)


def create_router(service: PaymentMethodService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/payment-methods", tags=["payment-methods"])

    @router.get("", response_model=list[PaymentMethodResponse])
    async def list_payment_methods(principal: Operator) -> list[PaymentMethodResponse]:
        del principal
        return [PaymentMethodResponse.from_domain(item) for item in await service.list()]

    @router.post("", response_model=PaymentMethodResponse, status_code=status.HTTP_201_CREATED)
    async def create_payment_method(
        body: PaymentMethodRequest,
        principal: Operator,
    ) -> PaymentMethodResponse:
        method = await service.create(**body.model_dump())
        del principal
        return PaymentMethodResponse.from_domain(method)

    @router.put("/{method_id}", response_model=PaymentMethodResponse)
    async def update_payment_method(
        method_id: uuid.UUID,
        body: PaymentMethodRequest,
        principal: Operator,
    ) -> PaymentMethodResponse:
        method = await service.update(method_id, **body.model_dump())
        del principal
        return PaymentMethodResponse.from_domain(method)

    @router.delete("/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_payment_method(method_id: uuid.UUID, principal: Operator) -> None:
        await service.delete(method_id)
        del principal

    return router
