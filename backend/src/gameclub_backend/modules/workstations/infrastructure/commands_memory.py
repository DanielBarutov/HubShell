import asyncio
import datetime
import uuid

from gameclub_backend.modules.workstations.domain_commands import (
    WorkstationCommand,
    WorkstationCommandStatus,
)


class InMemoryWorkstationCommandRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, WorkstationCommand] = {}
        self._lock = asyncio.Lock()

    async def get(self, command_id: uuid.UUID) -> WorkstationCommand | None:
        async with self._lock:
            return self._items.get(command_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> WorkstationCommand | None:
        async with self._lock:
            return next(
                (item for item in self._items.values() if item.idempotency_key == idempotency_key),
                None,
            )

    async def list_pending(self, workstation_id: uuid.UUID) -> list[WorkstationCommand]:
        async with self._lock:
            return sorted(
                (
                    item
                    for item in self._items.values()
                    if item.workstation_id == workstation_id
                    and item.status is WorkstationCommandStatus.QUEUED
                ),
                key=lambda item: item.created_at,
            )

    async def expire_queued_before(self, now: datetime.datetime) -> None:
        async with self._lock:
            for command_id, command in self._items.items():
                if command.status is WorkstationCommandStatus.QUEUED and command.expires_at <= now:
                    self._items[command_id] = command.expire(now)

    async def expire(self, command_id: uuid.UUID, now: datetime.datetime) -> WorkstationCommand:
        async with self._lock:
            command = self._items.get(command_id)
            if command is None:
                raise ValueError("Workstation command not found")
            updated = command.expire(now)
            self._items[command_id] = updated
            return updated

    async def save(self, command: WorkstationCommand) -> WorkstationCommand:
        async with self._lock:
            existing = next(
                (
                    item
                    for item in self._items.values()
                    if item.idempotency_key == command.idempotency_key
                ),
                None,
            )
            if existing is not None:
                return existing
            self._items[command.id] = command
            return command

    async def acknowledge(
        self,
        command_id: uuid.UUID,
        success: bool,
        message: str | None,
        now: datetime.datetime,
    ) -> WorkstationCommand:
        async with self._lock:
            command = self._items.get(command_id)
            if command is None:
                raise ValueError("Workstation command not found")
            updated = command.acknowledge(success, message, now)
            self._items[command.id] = updated
            return updated


class InMemoryCommandNotifier:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[None]] = {}
        self._lock = asyncio.Lock()

    async def _queue_for(self, device_id: str) -> asyncio.Queue[None]:
        async with self._lock:
            return self._queues.setdefault(device_id, asyncio.Queue())

    async def notify(self, device_id: str) -> None:
        queue = await self._queue_for(device_id)
        queue.put_nowait(None)

    async def wait(self, device_id: str) -> None:
        queue = await self._queue_for(device_id)
        await queue.get()
