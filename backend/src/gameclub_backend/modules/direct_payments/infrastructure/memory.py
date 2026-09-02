import asyncio
import uuid

from gameclub_backend.modules.direct_payments.domain import GuestSessionPayment


class InMemoryGuestSessionPaymentRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, GuestSessionPayment] = {}
        self._by_key: dict[str, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get(self, payment_id: uuid.UUID) -> GuestSessionPayment | None:
        return self._items.get(payment_id)

    async def get_by_idempotency_key(self, key: str) -> GuestSessionPayment | None:
        payment_id = self._by_key.get(key)
        return self._items.get(payment_id) if payment_id else None

    async def save(self, payment: GuestSessionPayment) -> GuestSessionPayment:
        async with self._lock:
            existing = await self.get_by_idempotency_key(payment.idempotency_key)
            if existing is not None:
                if existing.workstation_id != payment.workstation_id:
                    raise ValueError("Idempotency key belongs to another payment")
                return existing
            self._items[payment.id] = payment
            self._by_key[payment.idempotency_key] = payment.id
            return payment
