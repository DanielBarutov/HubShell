import dataclasses
import typing
import uuid

from gameclub_backend.modules.workstations.domain_relay import RelaySettings


@dataclasses.dataclass(frozen=True)
class XboxRelayObligation:
    session_id: uuid.UUID
    workstation_id: uuid.UUID
    settings: RelaySettings
    pending: bool = False


class XboxRelayRepository(typing.Protocol):
    async def get(self, session_id: uuid.UUID) -> XboxRelayObligation | None: ...
    async def save(self, obligation: XboxRelayObligation) -> None: ...
    async def delete(self, session_id: uuid.UUID) -> None: ...
    async def list_pending(self) -> list[XboxRelayObligation]: ...
    async def supersede(self, workstation_id: uuid.UUID, session_id: uuid.UUID) -> None: ...
