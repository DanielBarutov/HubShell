import uuid

from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.domain import CashMovementDirection


class CashShiftGuestPaymentSettlement:
    def __init__(self, cash_shifts: CashShiftService) -> None:
        self._cash_shifts = cash_shifts

    async def settle(
        self,
        shift_id: uuid.UUID,
        amount_cents: int,
        payment_idempotency_key: str,
        actor_id: str,
    ) -> None:
        await self._cash_shifts.record_movement(
            shift_id=shift_id,
            direction=CashMovementDirection.CASH_IN.value,
            amount_cents=amount_cents,
            reason="Оплата гостевого тарифа",
            actor_id=actor_id,
            idempotency_key=f"guest-payment-cash:{payment_idempotency_key}",
            reference_type="guest_session_payment",
            reference_id=payment_idempotency_key,
        )
