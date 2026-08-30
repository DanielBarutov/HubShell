import uuid

from gameclub_backend.modules.workstations.domain import Workstation


class InMemoryWorkstationRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, Workstation] = {}

    async def get(self, workstation_id: uuid.UUID) -> Workstation | None:
        return self._items.get(workstation_id)

    async def get_by_device_id(self, device_id: str) -> Workstation | None:
        return next(
            (item for item in self._items.values() if item.device_id == device_id),
            None,
        )

    async def list(self) -> list[Workstation]:
        return sorted(
            self._items.values(),
            key=lambda item: (item.position is None, item.position or 0),
        )

    async def save(self, workstation: Workstation) -> Workstation:
        self._items[workstation.id] = workstation
        return workstation

    async def delete(self, workstation_id: uuid.UUID) -> None:
        self._items.pop(workstation_id, None)
