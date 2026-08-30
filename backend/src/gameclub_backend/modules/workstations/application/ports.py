import datetime
import typing
import uuid

from gameclub_backend.modules.workstations.domain import Workstation, WorkstationGroup
from gameclub_backend.modules.workstations.domain_commands import WorkstationCommand


class WorkstationGroupRepository(typing.Protocol):
    async def get(self, group_id: str) -> WorkstationGroup | None:
        """Return one configured workstation group."""

    async def list(self) -> list[WorkstationGroup]:
        """Return configured workstation groups."""

    async def save(self, group: WorkstationGroup) -> WorkstationGroup:
        """Persist a workstation group."""

    async def delete(self, group_id: str) -> None:
        """Delete a workstation group configuration."""


class WorkstationRepository(typing.Protocol):
    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        """Return a workstation by ID."""

    async def get_by_device_id(self, device_id: str) -> Workstation | None:
        """Return a workstation by stable device identity."""

    async def list(self) -> list[Workstation]:
        """Return all workstations."""

    async def save(self, workstation: Workstation) -> Workstation:
        """Persist a workstation."""

    async def delete(self, workstation_id: uuid.UUID) -> None:
        """Delete a workstation from active configuration."""


class WorkstationSnapshotCache(typing.Protocol):
    async def get(self) -> list[Workstation] | None:
        """Return a cached workstation snapshot, if it is still available."""

    async def set(self, workstations: list[Workstation], ttl_seconds: int) -> None:
        """Store a workstation snapshot for a bounded amount of time."""

    async def invalidate(self) -> None:
        """Remove the snapshot after a workstation mutation."""


class WorkstationCommandRepository(typing.Protocol):
    async def get(self, command_id: uuid.UUID) -> WorkstationCommand | None:
        """Return a command by ID."""

    async def get_by_idempotency_key(self, idempotency_key: str) -> WorkstationCommand | None:
        """Return a command by its idempotency key."""

    async def list_pending(self, workstation_id: uuid.UUID) -> list[WorkstationCommand]:
        """Return commands that still need acknowledgement."""

    async def expire_queued_before(self, now: datetime.datetime) -> None:
        """Mark queued commands past their expiry as expired."""

    async def expire(self, command_id: uuid.UUID, now: datetime.datetime) -> WorkstationCommand:
        """Mark one queued command as expired."""

    async def save(self, command: WorkstationCommand) -> WorkstationCommand:
        """Persist a command or return an idempotent existing command."""

    async def acknowledge(
        self,
        command_id: uuid.UUID,
        success: bool,
        message: str | None,
        now: datetime.datetime,
    ) -> WorkstationCommand:
        """Persist an acknowledgement idempotently."""


class CommandNotifier(typing.Protocol):
    async def notify(self, device_id: str) -> None:
        """Wake a connected device stream."""

    async def wait(self, device_id: str) -> None:
        """Wait until a command may be available for a device."""


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return an aware UTC datetime."""
