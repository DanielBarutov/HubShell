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
from gameclub_backend.modules.workstations.domain import (
    Workstation,
    WorkstationStatus,
    normalize_mac_address,
)

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
        device_id: str | None,
        name: str,
        group_id: str | None = None,
        position: int | None = None,
        client_version: str | None = None,
        capabilities: typing.Sequence[str] = (),
        mac_address: str | None = None,
    ) -> Workstation:
        try:
            normalized_mac = normalize_mac_address(mac_address) if mac_address else None
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        normalized_device_id = device_id.strip() if device_id else ""
        if not normalized_device_id and normalized_mac:
            normalized_device_id = f"mac-{normalized_mac.replace(':', '').lower()}"
        normalized_name = name.strip()
        if not normalized_device_id or not normalized_name:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "name and either device_id or mac_address are required",
            )
        if await self._repository.get_by_device_id(normalized_device_id):
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation already registered")
        if normalized_mac and await self._repository.get_by_mac_address(normalized_mac):
            raise ApplicationError(ErrorCode.CONFLICT, "MAC address is already assigned")

        workstation = Workstation(
            id=uuid.uuid4(),
            device_id=normalized_device_id,
            name=normalized_name,
            group_id=group_id,
            position=position,
            client_version=client_version,
            capabilities=self._normalize_capabilities(capabilities),
            mac_address=normalized_mac,
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
        mac_address: str | None = None,
    ) -> Workstation:
        workstation = await self._repository.get(workstation_id)
        if workstation is None or workstation.archived_at is not None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        normalized_name = name.strip()
        normalized_group = group_id.strip().lower() if group_id else None
        if not normalized_name:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Workstation name is required")
        try:
            normalized_mac = normalize_mac_address(mac_address) if mac_address else None
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        if normalized_mac != workstation.mac_address and workstation.installation_id:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Workstation is already bound; use the explicit rebind flow",
            )
        if normalized_mac and normalized_mac != workstation.mac_address:
            assigned = await self._repository.get_by_mac_address(normalized_mac)
            if assigned is not None and assigned.id != workstation_id:
                raise ApplicationError(ErrorCode.CONFLICT, "MAC address is already assigned")
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
            mac_address=normalized_mac,
        )
        saved = await self._with_group_theme(await self._repository.save(updated))
        await self._invalidate_cache()
        return saved

    async def enroll_by_mac(
        self,
        mac_addresses: typing.Sequence[str],
        installation_id: str,
    ) -> Workstation | None:
        normalized_installation_id = installation_id.strip()
        if not normalized_installation_id or len(normalized_installation_id) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Installation identity is required")
        normalized_macs: list[str] = []
        for mac in mac_addresses:
            try:
                normalized_macs.append(normalize_mac_address(mac))
            except ValueError:
                continue
        if not normalized_macs:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "At least one valid MAC is required")

        workstation = None
        for mac in dict.fromkeys(normalized_macs):
            workstation = await self._repository.get_by_mac_address(mac)
            if workstation is not None:
                break
        if workstation is None:
            return None
        if (
            workstation.installation_id
            and workstation.installation_id != normalized_installation_id
        ):
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Workstation is already bound to another installation",
            )
        if workstation.installation_id is None:
            workstation = await self._repository.save(
                dataclasses.replace(workstation, installation_id=normalized_installation_id)
            )
            await self._invalidate_cache()
        return await self._with_group_theme(workstation)

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
