from __future__ import annotations

import dataclasses
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.domain import CashMovement, CashMovementDirection


def _validate_producer_amount(amount_cents: int) -> None:
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ApplicationError(
            ErrorCode.INVALID_ARGUMENT,
            "Producer amount must be a positive integer",
        )


@dataclasses.dataclass(frozen=True)
class BillingSettlement:
    settlement_id: str
    amount_cents: int
    confirmed: bool


@dataclasses.dataclass(frozen=True)
class ExternalPayment:
    provider: str
    payment_id: str
    amount_cents: int
    status: str
    direction: CashMovementDirection = CashMovementDirection.CASH_IN


class BillingCashSettlementProducer:
    """Publishes only confirmed Billing settlements into the cash ledger."""

    def __init__(self, cash_shifts: CashShiftService) -> None:
        self._cash_shifts = cash_shifts

    async def publish(
        self,
        shift_id: uuid.UUID,
        settlement: BillingSettlement,
        actor_id: str = "service:billing",
    ) -> CashMovement:
        if not settlement.confirmed:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Only confirmed billing settlements can enter the cash ledger",
            )
        _validate_producer_amount(settlement.amount_cents)
        _, movement = await self._cash_shifts.record_movement(
            shift_id=shift_id,
            direction=CashMovementDirection.CASH_IN.value,
            amount_cents=settlement.amount_cents,
            reason="Billing settlement",
            actor_id=actor_id,
            idempotency_key=f"billing-settlement:{settlement.settlement_id}",
            reference_type="billing_settlement",
            reference_id=settlement.settlement_id,
        )
        return movement


class ExternalPaymentProducer:
    """Consumes a provider-neutral, already verified payment capture."""

    _accepted_statuses = frozenset({"captured", "settled", "succeeded", "refunded", "paid_out"})

    def __init__(self, cash_shifts: CashShiftService) -> None:
        self._cash_shifts = cash_shifts

    async def publish(
        self,
        shift_id: uuid.UUID,
        payment: ExternalPayment,
    ) -> CashMovement:
        provider = payment.provider.strip().lower()
        payment_id = payment.payment_id.strip()
        status = payment.status.strip().lower()
        if not provider or not payment_id:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Payment provider and ID are required"
            )
        if status not in self._accepted_statuses:
            raise ApplicationError(ErrorCode.CONFLICT, "External payment is not finalized")
        if payment.direction not in {
            CashMovementDirection.CASH_IN,
            CashMovementDirection.CASH_OUT,
        }:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "External payment direction must be cash_in or cash_out",
            )
        _validate_producer_amount(payment.amount_cents)
        _, movement = await self._cash_shifts.record_movement(
            shift_id=shift_id,
            direction=payment.direction.value,
            amount_cents=payment.amount_cents,
            reason=f"External payment · {provider}",
            actor_id=f"service:payment:{provider}",
            idempotency_key=f"external-payment:{provider}:{payment_id}",
            reference_type="external_payment",
            reference_id=f"{provider}:{payment_id}",
        )
        return movement
