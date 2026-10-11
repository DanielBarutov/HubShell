import asyncio
import datetime
import uuid

from gameclub_backend.modules.eventing_v2.application.guest_access import GuestAccessGrant


class InMemoryGuestAccessGrantRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, GuestAccessGrant] = {}
        self._by_payment: dict[uuid.UUID, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get_by_payment(self, payment_id: uuid.UUID) -> GuestAccessGrant | None:
        grant_id = self._by_payment.get(payment_id)
        return self._items.get(grant_id) if grant_id else None

    async def get_pending_for_workstation(
        self,
        workstation_id: uuid.UUID,
        now: datetime.datetime,
        session_id: uuid.UUID | None = None,
        applied_grant_ids: tuple[uuid.UUID, ...] = (),
    ) -> GuestAccessGrant | None:
        candidates = [
            grant
            for grant in self._items.values()
            if grant.workstation_id == workstation_id
            and grant.id not in applied_grant_ids
            and (
                (session_id is not None and grant.is_extension and grant.session_id == session_id)
                or (session_id is None and grant.expires_at >= now and (not grant.is_extension))
            )
        ]
        return min(
            candidates,
            key=lambda item: (item.redeemed if session_id is None else False, item.expires_at),
            default=None,
        )

    async def save(self, grant: GuestAccessGrant) -> GuestAccessGrant:
        async with self._lock:
            existing_id = self._by_payment.get(grant.payment_id)
            if existing_id is not None and existing_id != grant.id:
                return self._items[existing_id]
            self._items[grant.id] = grant
            self._by_payment[grant.payment_id] = grant.id
            return grant
