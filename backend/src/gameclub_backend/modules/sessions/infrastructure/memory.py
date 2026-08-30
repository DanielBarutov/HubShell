from __future__ import annotations

import asyncio
import uuid

from gameclub_backend.modules.sessions.domain import Session, SessionStatus


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Session] = {}
        self._idempotency: dict[str, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: uuid.UUID) -> Session | None:
        return self._items.get(session_id)

    async def get_active_for_workstation(self, workstation_id: uuid.UUID) -> Session | None:
        return next(
            (
                item
                for item in self._items.values()
                if item.workstation_id == workstation_id and item.status is SessionStatus.ACTIVE
            ),
            None,
        )

    async def get_by_idempotency_key(self, idempotency_key: str) -> Session | None:
        session_id = self._idempotency.get(idempotency_key)
        return self._items.get(session_id) if session_id else None

    async def list(
        self,
        workstation_id: uuid.UUID | None = None,
        active_only: bool = False,
    ) -> list[Session]:
        return sorted(
            (
                item
                for item in self._items.values()
                if (workstation_id is None or item.workstation_id == workstation_id)
                and (not active_only or item.status is SessionStatus.ACTIVE)
            ),
            key=lambda item: item.started_at,
            reverse=True,
        )

    async def save(self, session: Session) -> Session:
        async with self._lock:
            existing = self._items.get(session.id)
            if existing is None and session.idempotency_key:
                repeated_id = self._idempotency.get(session.idempotency_key)
                if repeated_id is not None:
                    repeated = self._items[repeated_id]
                    if repeated.workstation_id != session.workstation_id:
                        raise ValueError("Idempotency key belongs to another workstation")
                    return repeated
            if session.status is SessionStatus.ACTIVE:
                active = await self.get_active_for_workstation(session.workstation_id)
                if active is not None and active.id != session.id:
                    raise ValueError("Workstation already has an active session")
            self._items[session.id] = session
            if session.idempotency_key:
                self._idempotency[session.idempotency_key] = session.id
            return session
