from gameclub_backend.modules.workstations.domain import WorkstationGroup


class InMemoryWorkstationGroupRepository:
    def __init__(self) -> None:
        self._items: dict[str, WorkstationGroup] = {}

    async def get(self, group_id: str) -> WorkstationGroup | None:
        return self._items.get(group_id)

    async def list(self) -> list[WorkstationGroup]:
        return sorted(self._items.values(), key=lambda item: item.id)

    async def save(self, group: WorkstationGroup) -> WorkstationGroup:
        self._items[group.id] = group
        return group

    async def delete(self, group_id: str) -> None:
        self._items.pop(group_id, None)
