import dataclasses
import datetime
import typing
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.workstations.application.ports import (
    Clock,
    WorkstationGroupRepository,
    WorkstationRepository,
    WorkstationSnapshotCache,
)
from gameclub_backend.modules.workstations.domain import Workstation, WorkstationStatus

LEGACY_WORKSTATION_GROUP_IDS = frozenset({"main", "vip"})


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class WorkstationService:
    def __init__(
        self,
        repository: WorkstationRepository,
        clock: Clock | None = None,
        stale_after_seconds: int = 45,
        offline_after_seconds: int = 120,
        groups: WorkstationGroupRepository | None = None,
        cache: WorkstationSnapshotCache | None = None,
        cache_ttl_seconds: int = 20,
    ) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()
        self._stale_after = datetime.timedelta(seconds=stale_after_seconds)
        self._offline_after = datetime.timedelta(seconds=offline_after_seconds)
        self._groups = groups
        self._cache = cache
        self._cache_ttl_seconds = cache_ttl_seconds

    async def register(
        self,
        device_id: str,
        name: str,
        group_id: str | None = None,
        position: int | None = None,
        client_version: str | None = None,
        capabilities: typing.Sequence[str] = (),
    ) -> Workstation:
        normalized_device_id = device_id.strip()
        normalized_name = name.strip()
        if not normalized_device_id or not normalized_name:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "device_id and name are required")
        if await self._repository.get_by_device_id(normalized_device_id):
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation already registered")

        workstation = Workstation(
            id=uuid.uuid4(),
            device_id=normalized_device_id,
            name=normalized_name,
            group_id=group_id,
            position=position,
            client_version=client_version,
            capabilities=self._normalize_capabilities(capabilities),
        )
        saved = await self._with_group_theme(await self._repository.save(workstation))
        await self._invalidate_cache()
        return saved

    async def heartbeat(
        self,
        device_id: str,
        client_version: str | None = None,
        capabilities: typing.Sequence[str] = (),
    ) -> Workstation:
        workstation = await self._repository.get_by_device_id(device_id.strip())
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        if workstation.status is WorkstationStatus.DISABLED:
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation is disabled")
        updated = workstation.heartbeat(
            self._clock.now(),
            client_version,
            self._normalize_capabilities(capabilities),
        )
        saved = await self._with_group_theme(await self._repository.save(updated))
        await self._invalidate_cache()
        return saved

    async def disable(self, workstation_id: uuid.UUID, reason: str) -> Workstation:
        workstation = await self._repository.get(workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        saved = await self._repository.save(workstation.disable(reason))
        await self._invalidate_cache()
        return saved

    async def update(
        self,
        workstation_id: uuid.UUID,
        name: str,
        group_id: str | None,
        position: int | None,
    ) -> Workstation:
        workstation = await self._repository.get(workstation_id)
        if workstation is None or workstation.archived_at is not None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        normalized_name = name.strip()
        normalized_group = group_id.strip().lower() if group_id else None
        if not normalized_name:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Workstation name is required")
        if (
            normalized_group
            and self._groups
            and normalized_group not in LEGACY_WORKSTATION_GROUP_IDS
            and await self._groups.get(normalized_group) is None
        ):
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation group not found")
        updated = dataclasses.replace(
            workstation,
            name=normalized_name,
            group_id=normalized_group,
            position=position,
        )
        saved = await self._with_group_theme(await self._repository.save(updated))
        await self._invalidate_cache()
        return saved

    async def enable(self, workstation_id: uuid.UUID) -> Workstation:
        workstation = await self._repository.get(workstation_id)
        if workstation is None or workstation.archived_at is not None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        saved = await self._with_group_theme(await self._repository.save(workstation.enable()))
        await self._invalidate_cache()
        return saved

    async def archive(self, workstation_id: uuid.UUID) -> None:
        workstation = await self._repository.get(workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        if workstation.archived_at is None:
            await self._repository.save(workstation.archive(self._clock.now()))
            await self._invalidate_cache()

    async def list(self) -> list[Workstation]:
        if self._cache is not None:
            cached = await self._cache.get()
            if cached is not None:
                return cached
        now = self._clock.now()
        workstations = [
            await self._with_group_theme(
                workstation.status_at(now, self._stale_after, self._offline_after)
            )
            for workstation in await self._repository.list()
            if workstation.archived_at is None
        ]
        if self._cache is not None:
            await self._cache.set(workstations, self._cache_ttl_seconds)
        return workstations

    async def _invalidate_cache(self) -> None:
        if self._cache is not None:
            await self._cache.invalidate()

    async def _with_group_theme(self, workstation: Workstation) -> Workstation:
        if self._groups is None or not workstation.group_id:
            return workstation
        group = await self._groups.get(workstation.group_id)
        return dataclasses.replace(
            workstation,
            theme=group.theme if group else "standard",
            manager_password_verifier=group.manager_password_verifier if group else None,
            lockdown_policy=group.lockdown_policy if group else workstation.lockdown_policy,
        )

    @staticmethod
    def _normalize_capabilities(capabilities: typing.Sequence[str]) -> tuple[str, ...]:
        return tuple(sorted({value.strip() for value in capabilities if value.strip()}))
