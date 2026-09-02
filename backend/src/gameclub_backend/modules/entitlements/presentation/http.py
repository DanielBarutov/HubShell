import typing
import uuid

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import Entitlement
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("clients.manage"))]


class PurchaseEntitlementRequest(BaseModel):
    tariff_id: uuid.UUID


class EntitlementResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    tariff_id: uuid.UUID
    zone_id: str | None
    window_start_minute: int | None
    window_end_minute: int | None
    window_timezone: str | None
    duration_minutes: int
    remaining_minutes: int
    price_cents: int
    queue_position: int
    status: str
    idempotency_key: str
    purchased_at: str
    activated_at: str | None
    ended_at: str | None
    burn_reason: str | None

    @classmethod
    def from_domain(cls, item: Entitlement) -> "EntitlementResponse":
        return cls(
            id=item.id,
            client_id=item.client_id,
            tariff_id=item.tariff_id,
            zone_id=item.zone_id,
            window_start_minute=item.window_start_minute,
            window_end_minute=item.window_end_minute,
            window_timezone=item.window_timezone,
            duration_minutes=item.duration_minutes,
            remaining_minutes=item.remaining_minutes,
            price_cents=item.price_cents,
            queue_position=item.queue_position,
            status=item.status.value,
            idempotency_key=item.idempotency_key,
            purchased_at=item.purchased_at.isoformat(),
            activated_at=item.activated_at.isoformat() if item.activated_at else None,
            ended_at=item.ended_at.isoformat() if item.ended_at else None,
            burn_reason=item.burn_reason,
        )


def create_router(service: EntitlementService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/clients/{client_id}/entitlements", tags=["entitlements"])

    @router.get("", response_model=list[EntitlementResponse])
    async def list_entitlements(
        client_id: uuid.UUID,
        principal: Operator,
    ) -> list[EntitlementResponse]:
        del principal
        return [
            EntitlementResponse.from_domain(item)
            for item in await service.list_for_client(client_id)
        ]

    @router.post("", response_model=EntitlementResponse, status_code=status.HTTP_201_CREATED)
    async def purchase_entitlement(
        client_id: uuid.UUID,
        body: PurchaseEntitlementRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> EntitlementResponse:
        return EntitlementResponse.from_domain(
            await service.purchase(
                client_id=client_id,
                tariff_id=body.tariff_id,
                actor_id=principal.subject_id,
                idempotency_key=idempotency_key,
            )
        )

    @router.post("/{entitlement_id}/activate", response_model=EntitlementResponse)
    async def activate_entitlement(
        client_id: uuid.UUID,
        entitlement_id: uuid.UUID,
        principal: Operator,
    ) -> EntitlementResponse:
        del principal
        return EntitlementResponse.from_domain(await service.activate(entitlement_id, client_id))

    return router
