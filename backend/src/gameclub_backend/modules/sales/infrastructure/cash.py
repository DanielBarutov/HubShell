import uuid

from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.domain import CashMovementDirection


class CashShiftSaleSettlement:
    def __init__(self, cash_shifts: CashShiftService) -> None:
        self._cash_shifts = cash_shifts

    async def settle(
        self,
        shift_id: uuid.UUID,
        amount_cents: int,
        sale_idempotency_key: str,
        actor_id: str,
    ) -> None:
        await self._cash_shifts.record_movement(
            shift_id=shift_id,
            direction=CashMovementDirection.CASH_IN.value,
            amount_cents=amount_cents,
            reason="Продажа товара",
            actor_id=actor_id,
            idempotency_key=f"product-sale-cash:{sale_idempotency_key}",
            reference_type="product_sale",
            reference_id=sale_idempotency_key,
        )
