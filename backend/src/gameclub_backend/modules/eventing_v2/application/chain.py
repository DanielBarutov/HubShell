from __future__ import annotations

from gameclub_backend.modules.eventing_v2.application.ports import V2SessionChainRepository
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2SessionChain,
    V2SessionChainStatus,
)


class V2SessionChainService:
    """Проверяет и продвигает checkpoint до запуска финансового сценария."""

    def __init__(self, repository: V2SessionChainRepository) -> None:
        self._repository = repository

    async def accept(self, event: V2Event) -> V2SessionChainStatus:
        current = await self._repository.get(event.session_id)
        if current is None:
            try:
                updated = V2SessionChain.from_first_event(event)
            except ValueError:
                return V2SessionChainStatus.GAP
            saved = await self._repository.save_if_current(updated, expected_last_sequence=None)
            return V2SessionChainStatus.ACCEPTED if saved else V2SessionChainStatus.GAP

        status, updated = current.accept(event)
        if status is not V2SessionChainStatus.ACCEPTED or updated is None:
            return status
        saved = await self._repository.save_if_current(
            updated,
            expected_last_sequence=current.last_sequence,
        )
        return V2SessionChainStatus.ACCEPTED if saved else V2SessionChainStatus.GAP
