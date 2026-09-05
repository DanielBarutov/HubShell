from __future__ import annotations

import asyncio
import datetime
import uuid

from gameclub_backend.modules.reservations.domain import Reservation, ReservationStatus


class InMemoryReservationRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Reservation] = {}
        self._idempotency: dict[str, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get(self, reservation_id: uuid.UUID) -> Reservation | None:
        return self._items.get(reservation_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> Reservation | None:
        reservation_id = self._idempotency.get(idempotency_key)
        return self._items.get(reservation_id) if reservation_id else None

    async def list(
        self,
        start_at: datetime.datetime,
        end_at: datetime.datetime,
    ) -> list[Reservation]:
        return sorted(
            (item for item in self._items.values() if item.overlaps(start_at, end_at)),
            key=lambda item: item.start_at,
        )

    async def list_for_client(
        self,
        client_id: uuid.UUID,
        start_at: datetime.datetime,
        limit: int,
    ) -> list[Reservation]:
        return sorted(
            (
                item
                for item in self._items.values()
                if item.client_id == client_id
                and item.status is ReservationStatus.CONFIRMED
                and item.start_at >= start_at
            ),
            key=lambda item: (item.start_at, str(item.id)),
        )[:limit]

    async def list_pending_no_show(self, cutoff_at: datetime.datetime) -> list[Reservation]:
        return sorted(
            (
                item
                for item in self._items.values()
                if item.status is ReservationStatus.CONFIRMED and item.start_at <= cutoff_at
            ),
            key=lambda item: item.start_at,
        )

    async def mark_no_show_if_eligible(
        self,
        reservation_id: uuid.UUID,
        now: datetime.datetime,
        grace_period_minutes: int,
    ) -> Reservation | None:
        async with self._lock:
            reservation = self._items.get(reservation_id)
            if reservation is None or reservation.status is not ReservationStatus.CONFIRMED:
                return None
            try:
                updated = reservation.mark_no_show(now, grace_period_minutes)
            except ValueError:
                return None
            self._items[reservation_id] = updated
            return updated

    async def save(self, reservation: Reservation) -> Reservation:
        async with self._lock:
            existing = self._items.get(reservation.id)
            if existing is not None:
                if self._has_conflict(reservation):
                    raise ValueError("Workstation is already reserved for this period")
                self._items[reservation.id] = reservation
                if reservation.idempotency_key:
                    self._idempotency[reservation.idempotency_key] = reservation.id
                return reservation

            if reservation.idempotency_key:
                repeated_id = self._idempotency.get(reservation.idempotency_key)
                if repeated_id is not None:
                    return self._items[repeated_id]

            if self._has_conflict(reservation):
                raise ValueError("Workstation is already reserved for this period")

            self._items[reservation.id] = reservation
            if reservation.idempotency_key:
                self._idempotency[reservation.idempotency_key] = reservation.id
            return reservation

    def _has_conflict(self, reservation: Reservation) -> bool:
        active_statuses = {ReservationStatus.CONFIRMED, ReservationStatus.ACTIVE}
        return any(
            item.id != reservation.id
            and reservation.status in active_statuses
            and item.status in active_statuses
            and item.overlaps(reservation.start_at, reservation.end_at)
            and set(item.workstation_ids).intersection(reservation.workstation_ids)
            for item in self._items.values()
        )
