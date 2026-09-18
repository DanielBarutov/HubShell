from __future__ import annotations

import asyncio
import dataclasses

from gameclub_backend.modules.client_groups.domain import ClientGroup


class InMemoryClientGroupRepository:
    def __init__(self) -> None:
        now = None
        self._items: dict[str, ClientGroup] = {
            "regular": ClientGroup(
                id="regular",
                name="Обычные клиенты",
                is_default=True,
                updated_at=now,
            )
        }
        self._lock = asyncio.Lock()
        self._client_counts: dict[str, int] = {}

    async def get(self, group_id: str) -> ClientGroup | None:
        return self._items.get(group_id.strip().lower())

    async def list(self) -> list[ClientGroup]:
        return sorted(self._items.values(), key=lambda item: item.id)

    async def get_default(self) -> ClientGroup | None:
        return next(
            (item for item in self._items.values() if item.active and item.is_default),
            None,
        )

    async def save(self, group: ClientGroup) -> ClientGroup:
        async with self._lock:
            if group.is_default:
                self._items = {
                    key: item if key == group.id else dataclasses.replace(item, is_default=False)
                    for key, item in self._items.items()
                }
            self._items[group.id] = group
            return group

    async def delete(self, group_id: str) -> None:
        async with self._lock:
            self._items.pop(group_id.strip().lower(), None)

    async def count_clients(self, group_id: str) -> int:
        return self._client_counts.get(group_id.strip().lower(), 0)
