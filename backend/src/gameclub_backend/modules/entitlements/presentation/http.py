import dataclasses
import typing
import uuid

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import Entitlement
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("clients.manage"))]


class PurchaseEntitlementRequest(BaseModel):
    tariff_id: uuid.UUID
    cash_shift_id: uuid.UUID | None = None
    use_bonus: bool = Field(default=False, strict=True)
    expected_price_cents: int | None = Field(default=None, strict=True, ge=0)
    expected_bonus_cents: int | None = Field(default=None, strict=True, ge=0)
    expected_money_cents: int | None = Field(default=None, strict=True, ge=0)
    expected_earned_bonus_cents: int | None = Field(default=None, strict=True, ge=0)
    payment_parts: list["PaymentPartRequest"] = Field(default_factory=list)


class QuoteEntitlementRequest(BaseModel):
    tariff_id: uuid.UUID
    use_bonus: bool = Field(default=False, strict=True)


class QuoteEntitlementResponse(BaseModel):
    earning_rate_bps: int
    price_cents: int
    bonus_cents: int
    money_cents: int
    earned_bonus_cents: int
    payment_limit_bps: int
    available_bonus_cents: int
    reserved_bonus_cents: int
    bonus_allowed: bool
    can_pay: bool


class PaymentPartRequest(BaseModel):
    method: str
    amount_cents: int
    reference: str | None = None


class EntitlementResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    tariff_id: uuid.UUID
    zone_id: str | None
    time_restricted: bool
    sale_window_start_minute: int | None
    sale_window_end_minute: int | None
    usage_window_start_minute: int | None
    usage_window_end_minute: int | None
    window_timezone: str | None
    audience: str
    duration_minutes: int
    remaining_minutes: int
    price_cents: int
    bonus_amount_cents: int
    bonus_requested: bool
    queue_position: int
    status: str
    idempotency_key: str
    purchased_at: str
    activated_at: str | None
    ended_at: str | None
    burn_reason: str | None
    payment_parts: list[dict[str, object]]
    cash_shift_id: uuid.UUID | None
    settlement_status: str
    settlement_error: str | None
    settlement_attempts: int
    next_settlement_attempt_at: str | None

    @classmethod
    def from_domain(cls, item: Entitlement) -> "EntitlementResponse":
        return cls(
            id=item.id,
            client_id=item.client_id,
            tariff_id=item.tariff_id,
            zone_id=item.zone_id,
            time_restricted=item.time_restricted,
            sale_window_start_minute=item.sale_window_start_minute,
            sale_window_end_minute=item.sale_window_end_minute,
            usage_window_start_minute=item.usage_window_start_minute,
            usage_window_end_minute=item.usage_window_end_minute,
            window_timezone=item.window_timezone,
            audience=item.audience.value,
            duration_minutes=item.duration_minutes,
            remaining_minutes=item.remaining_minutes,
            price_cents=item.price_cents,
            bonus_amount_cents=item.bonus_amount_cents,
            bonus_requested=item.bonus_requested,
            queue_position=item.queue_position,
            status=item.status.value,
            idempotency_key=item.idempotency_key,
            purchased_at=item.purchased_at.isoformat(),
            activated_at=item.activated_at.isoformat() if item.activated_at else None,
            ended_at=item.ended_at.isoformat() if item.ended_at else None,
            burn_reason=item.burn_reason,
            payment_parts=[part.as_dict() for part in item.payment_parts],
            cash_shift_id=item.cash_shift_id,
            settlement_status=item.settlement_status.value,
            settlement_error=item.settlement_error,
            settlement_attempts=item.settlement_attempts,
            next_settlement_attempt_at=(
                item.next_settlement_attempt_at.isoformat()
                if item.next_settlement_attempt_at
                else None
            ),
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

    @router.post("/quote", response_model=QuoteEntitlementResponse)
    async def quote_entitlement(
        client_id: uuid.UUID,
        body: QuoteEntitlementRequest,
        principal: Operator,
    ) -> QuoteEntitlementResponse:
        del principal
        quote = await service.quote_purchase(client_id, body.tariff_id, body.use_bonus)
        return QuoteEntitlementResponse(**dataclasses.asdict(quote))

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
                payment_parts=[part.model_dump() for part in body.payment_parts],
                cash_shift_id=body.cash_shift_id,
                use_bonus=body.use_bonus,
                principal=principal,
                expected_price_cents=body.expected_price_cents,
                expected_bonus_cents=body.expected_bonus_cents,
                expected_money_cents=body.expected_money_cents,
                expected_earned_bonus_cents=body.expected_earned_bonus_cents,
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

    @router.post("/{entitlement_id}/reconcile", response_model=EntitlementResponse)
    async def reconcile_entitlement(
        client_id: uuid.UUID,
        entitlement_id: uuid.UUID,
        principal: Operator,
    ) -> EntitlementResponse:
        entitlement = await service.get(entitlement_id)
        if entitlement.client_id != client_id:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED, "Entitlement belongs to another client"
            )
        return EntitlementResponse.from_domain(
            await service.retry_settlement_review(entitlement_id, principal.subject_id)
        )

    return router
