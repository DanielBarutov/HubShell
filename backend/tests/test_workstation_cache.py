from __future__ import annotations

from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)


class FakeWorkstationSnapshotCache:
    def __init__(self) -> None:
        self.value = None
        self.get_calls = 0
        self.set_calls = 0
        self.invalidate_calls = 0
        self.ttl_seconds = None

    async def get(self):
        self.get_calls += 1
        return self.value

    async def set(self, workstations, ttl_seconds: int) -> None:
        self.set_calls += 1
        self.ttl_seconds = ttl_seconds
        self.value = workstations

    async def invalidate(self) -> None:
        self.invalidate_calls += 1
        self.value = None


async def test_workstation_list_uses_cache_for_twenty_seconds() -> None:
    cache = FakeWorkstationSnapshotCache()
    service = WorkstationService(
        InMemoryWorkstationRepository(),
        cache=cache,
        cache_ttl_seconds=20,
    )
    workstation = await service.register("device-01", "PC-01")

    first = await service.list()
    second = await service.list()

    assert [item.id for item in first] == [workstation.id]
    assert [item.id for item in second] == [workstation.id]
    assert cache.get_calls == 2
    assert cache.set_calls == 1
    assert cache.ttl_seconds == 20
    assert cache.invalidate_calls == 1
