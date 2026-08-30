import asyncio
import contextlib
import datetime
import uuid

from gameclub_backend.modules.billing.domain import (
    ChargeReconciliation,
    ReconciliationStatus,
    RevenueSummary,
    SessionCharge,
    SessionMeter,
)


class InMemoryMeterRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, SessionMeter] = {}
        self._lock = asyncio.Lock()
        self._session_locks: dict[uuid.UUID, asyncio.Lock] = {}

    @contextlib.asynccontextmanager
    async def acquire(self, session_id: uuid.UUID):
        async with self._lock:
            lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            yield

    async def get(self, session_id: uuid.UUID) -> SessionMeter | None:
        return self._items.get(session_id)

    async def ensure(self, meter: SessionMeter) -> SessionMeter:
        async with self._lock:
            return self._items.setdefault(meter.session_id, meter)

    async def save(self, meter: SessionMeter) -> SessionMeter:
        async with self._lock:
            current = self._items.get(meter.session_id)
            if current is not None:
                if meter.billed_minutes < current.billed_minutes:
                    raise ValueError("Session meter cannot move backwards")
                if meter.billed_cents < current.billed_cents:
                    raise ValueError("Session meter cannot move backwards")
            self._items[meter.session_id] = meter
            return meter


class InMemoryChargeRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, SessionCharge] = {}
        self._by_session: dict[uuid.UUID, uuid.UUID] = {}
        self._by_key: dict[str, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get_by_session_id(self, session_id: uuid.UUID) -> SessionCharge | None:
        charge_id = self._by_session.get(session_id)
        return self._items.get(charge_id) if charge_id else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> SessionCharge | None:
        charge_id = self._by_key.get(idempotency_key)
        return self._items.get(charge_id) if charge_id else None

    async def save(self, charge: SessionCharge) -> SessionCharge:
        async with self._lock:
            existing_by_key = self._by_key.get(charge.idempotency_key)
            if existing_by_key is not None:
                existing = self._items[existing_by_key]
                if existing.session_id != charge.session_id:
                    raise ValueError("Idempotency key belongs to another session")
                return existing
            existing_by_session = self._by_session.get(charge.session_id)
            if existing_by_session is not None:
                return self._items[existing_by_session]
            self._items[charge.id] = charge
            self._by_session[charge.session_id] = charge.id
            self._by_key[charge.idempotency_key] = charge.id
            return charge

    async def revenue_between(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> RevenueSummary:
        charges = [item for item in self._items.values() if start_at <= item.created_at < end_at]
        return RevenueSummary(
            start_at=start_at,
            end_at=end_at,
            amount_cents=sum(item.amount_cents for item in charges),
            charge_count=len(charges),
        )


class InMemoryChargeReconciliationRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, ChargeReconciliation] = {}
        self._by_key: dict[str, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get_by_session_id(self, session_id: uuid.UUID) -> ChargeReconciliation | None:
        return self._items.get(session_id)

    async def ensure_pending(self, item: ChargeReconciliation) -> ChargeReconciliation:
        async with self._lock:
            existing = self._items.get(item.session_id)
            if existing is not None:
                return existing
            existing_session = self._by_key.get(item.idempotency_key)
            if existing_session is not None and existing_session != item.session_id:
                raise ValueError("Idempotency key belongs to another session")
            self._items[item.session_id] = item
            self._by_key[item.idempotency_key] = item.session_id
            return item

    async def save(self, item: ChargeReconciliation) -> ChargeReconciliation:
        async with self._lock:
            existing = self._items.get(item.session_id)
            if existing is not None and existing.status is ReconciliationStatus.COMPLETED:
                return existing
            existing_session = self._by_key.get(item.idempotency_key)
            if existing_session is not None and existing_session != item.session_id:
                raise ValueError("Idempotency key belongs to another session")
            self._items[item.session_id] = item
            self._by_key[item.idempotency_key] = item.session_id
            return item

    async def list_due(
        self,
        now: datetime.datetime,
        limit: int,
    ) -> list[ChargeReconciliation]:
        items = [item for item in self._items.values() if item.is_due(now)]
        items.sort(key=lambda item: (item.next_attempt_at, item.created_at))
        return items[:limit]

    async def list_recent(self, limit: int) -> list[ChargeReconciliation]:
        items = sorted(
            self._items.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        return items[:limit]
