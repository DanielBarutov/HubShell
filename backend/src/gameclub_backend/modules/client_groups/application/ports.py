from __future__ import annotations

import datetime
import typing

from gameclub_backend.modules.client_groups.domain import ClientGroup


class ClientGroupRepository(typing.Protocol):
    async def get(self, group_id: str) -> ClientGroup | None:
        """Return a client group by normalized id."""

    async def list(self) -> list[ClientGroup]:
        """Return client groups ordered for operator display."""

    async def get_default(self) -> ClientGroup | None:
        """Return the active default group."""

    async def save(self, group: ClientGroup) -> ClientGroup:
        """Persist a group and its default marker atomically."""

    async def delete(self, group_id: str) -> None:
        """Delete a group that has no client assignments."""

    async def count_clients(self, group_id: str) -> int:
        """Return the number of clients assigned to a group."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
