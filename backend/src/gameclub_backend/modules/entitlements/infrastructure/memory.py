import asyncio
import datetime
import uuid

from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus


class InMemoryEntitlementRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Entitlement] = {}
        self._lock = asyncio.Lock()

    async def get(self, entitlement_id: uuid.UUID) -> Entitlement | None:
        return self._items.get(entitlement_id)

    async def get_by_idempotency_key(self, key: str) -> Entitlement | None:
        return next((item for item in self._items.values() if item.idempotency_key == key), None)

    async def list_for_client(self, client_id: uuid.UUID) -> list[Entitlement]:
        return sorted(
            (item for item in self._items.values() if item.client_id == client_id),
            key=lambda item: item.queue_position,
        )

    async def get_active_for_client(self, client_id: uuid.UUID) -> Entitlement | None:
        return next(
            (
                item
                for item in self._items.values()
                if item.client_id == client_id and item.status is EntitlementStatus.ACTIVE
            ),
            None,
        )

    async def create(self, entitlement: Entitlement) -> Entitlement:
        async with self._lock:
            existing = await self.get_by_idempotency_key(entitlement.idempotency_key)
            if existing is not None:
                if (
                    existing.client_id != entitlement.client_id
                    or existing.tariff_id != entitlement.tariff_id
                ):
                    raise ValueError("Idempotency key belongs to another package")
                return existing
            self._items[entitlement.id] = entitlement
            return entitlement

    async def save(self, entitlement: Entitlement) -> Entitlement:
        async with self._lock:
            if entitlement.status is EntitlementStatus.ACTIVE:
                active = await self.get_active_for_client(entitlement.client_id)
                if active is not None and active.id != entitlement.id:
                    raise ValueError("Client already has an active package")
            if entitlement.id not in self._items:
                raise ValueError("Entitlement not found")
            self._items[entitlement.id] = entitlement
            return entitlement

    async def next_compatible(
        self,
        client_id: uuid.UUID,
        zone_id: str | None,
        statuses: tuple[EntitlementStatus, ...] = (EntitlementStatus.QUEUED,),
        now: datetime.datetime | None = None,
    ) -> Entitlement | None:
        moment = now or datetime.datetime.now(datetime.UTC)
        return next(
            (
                item
                for item in await self.list_for_client(client_id)
                if item.status in statuses
                and item.is_compatible(zone_id)
                and item.is_available_at(moment)
            ),
            None,
        )

    async def activate_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        now: datetime.datetime,
        zone_id: str | None = None,
    ) -> Entitlement:
        async with self._lock:
            item = self._items.get(entitlement_id)
            if item is None:
                raise ValueError("Entitlement not found")
            if item.client_id != client_id:
                raise ValueError("Entitlement belongs to another client")
            if zone_id is not None and not item.is_compatible(zone_id):
                raise ValueError("Package is incompatible with this workstation zone")
            if not item.is_available_at(now):
                raise ValueError("Package is outside its time window")
            active = await self.get_active_for_client(client_id)
            if active is not None and active.id != entitlement_id:
                raise ValueError("Client already has an active package")
            updated = item.activate(now)
            self._items[entitlement_id] = updated
            return updated

    async def consume_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        minutes: int,
        now: datetime.datetime,
    ) -> Entitlement:
        async with self._lock:
            item = self._items.get(entitlement_id)
            if item is None:
                raise ValueError("Entitlement not found")
            if item.client_id != client_id:
                raise ValueError("Entitlement belongs to another client")
            if not item.is_available_at(now):
                raise ValueError("Package is outside its time window")
            updated = item.consume(minutes, now)
            self._items[entitlement_id] = updated
            return updated, item.remaining_minutes - updated.remaining_minutes

    async def burn_for_client(
        self,
        entitlement_id: uuid.UUID,
        client_id: uuid.UUID,
        reason: str,
        now: datetime.datetime,
    ) -> Entitlement:
        async with self._lock:
            item = self._items.get(entitlement_id)
            if item is None:
                raise ValueError("Entitlement not found")
            if item.client_id != client_id:
                raise ValueError("Entitlement belongs to another client")
            updated = item.burn(reason, now)
            self._items[entitlement_id] = updated
            return updated
