import asyncio
import uuid

from gameclub_backend.modules.sessions.domain import SessionTransferOffer, TransferStatus


class InMemorySessionTransferRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, SessionTransferOffer] = {}
        self._by_key: dict[str, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get(self, offer_id: uuid.UUID) -> SessionTransferOffer | None:
        return self._items.get(offer_id)

    async def get_by_idempotency_key(self, key: str) -> SessionTransferOffer | None:
        offer_id = self._by_key.get(key)
        return self._items.get(offer_id) if offer_id else None

    async def save(self, offer: SessionTransferOffer) -> SessionTransferOffer:
        async with self._lock:
            current = self._items.get(offer.id)
            if current is not None and current.status is TransferStatus.CONFIRMED:
                return current
            existing_id = self._by_key.get(offer.idempotency_key)
            if existing_id is not None and existing_id != offer.id:
                raise ValueError("Transfer idempotency key belongs to another offer")
            self._items[offer.id] = offer
            self._by_key[offer.idempotency_key] = offer.id
            return offer
