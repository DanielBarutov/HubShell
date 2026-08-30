import uuid

from gameclub_backend.modules.payment_methods.domain import PaymentMethod


class InMemoryPaymentMethodRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, PaymentMethod] = {}

    async def get(self, method_id: uuid.UUID) -> PaymentMethod | None:
        return self._items.get(method_id)

    async def get_by_key(self, key: str) -> PaymentMethod | None:
        return next((item for item in self._items.values() if item.key == key), None)

    async def list(self) -> list[PaymentMethod]:
        return sorted(self._items.values(), key=lambda item: (item.sort_order, item.name.lower()))

    async def save(self, method: PaymentMethod) -> PaymentMethod:
        self._items[method.id] = method
        return method

    async def delete(self, method_id: uuid.UUID) -> None:
        self._items.pop(method_id, None)
