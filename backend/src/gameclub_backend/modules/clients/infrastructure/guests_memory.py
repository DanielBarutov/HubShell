import uuid

from gameclub_backend.modules.clients.domain import Guest


class InMemoryGuestRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Guest] = {}

    async def get(self, guest_id: uuid.UUID) -> Guest | None:
        return self._items.get(guest_id)

    async def list_guests(self) -> list[Guest]:
        return sorted(self._items.values(), key=lambda item: item.nickname.lower())

    async def search(self, query: str, field: str) -> list[Guest]:
        if field == "nickname":
            result = [item for item in self._items.values() if query in item.nickname.lower()]
        else:
            result = [item for item in self._items.values() if item.phone and query in item.phone]
        return sorted(result, key=lambda item: item.nickname.lower())

    async def save(self, guest: Guest) -> Guest:
        self._items[guest.id] = guest
        return guest
