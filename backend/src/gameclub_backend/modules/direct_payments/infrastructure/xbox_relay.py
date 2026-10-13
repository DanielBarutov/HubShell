import dataclasses
import uuid

from sqlalchemy import Boolean, delete, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, begin_session, open_session
from gameclub_backend.modules.direct_payments.application.xbox_relay import XboxRelayObligation
from gameclub_backend.modules.direct_payments.infrastructure.postgres import DirectPaymentBase
from gameclub_backend.modules.workstations.domain_relay import RelaySettings


class XboxRelayModel(DirectPaymentBase):
    __tablename__ = "xbox_relay_obligations"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    settings: Mapped[dict[str, object]] = mapped_column(JSONB)
    pending: Mapped[bool] = mapped_column(Boolean, index=True)

    def to_domain(self) -> XboxRelayObligation:
        return XboxRelayObligation(
            self.session_id, self.workstation_id, RelaySettings(**self.settings), self.pending
        )


class PostgresXboxRelayRepository:
    def __init__(self, provider: EngineProvider) -> None:
        self._provider = provider

    async def get(self, session_id: uuid.UUID) -> XboxRelayObligation | None:
        async with open_session(self._provider) as session:
            model = await session.get(XboxRelayModel, session_id)
            return model.to_domain() if model else None

    async def save(self, obligation: XboxRelayObligation) -> None:
        async with open_session(self._provider) as session, begin_session(session):
            await session.merge(
                XboxRelayModel(
                    session_id=obligation.session_id,
                    workstation_id=obligation.workstation_id,
                    settings=dataclasses.asdict(obligation.settings),
                    pending=obligation.pending,
                )
            )

    async def delete(self, session_id: uuid.UUID) -> None:
        async with open_session(self._provider) as session, begin_session(session):
            await session.execute(
                delete(XboxRelayModel).where(XboxRelayModel.session_id == session_id)
            )

    async def list_pending(self) -> list[XboxRelayObligation]:
        async with open_session(self._provider) as session:
            models = await session.scalars(select(XboxRelayModel).where(XboxRelayModel.pending))
            return [model.to_domain() for model in models]

    async def supersede(self, workstation_id: uuid.UUID, session_id: uuid.UUID) -> None:
        async with open_session(self._provider) as session, begin_session(session):
            await session.execute(
                delete(XboxRelayModel).where(
                    XboxRelayModel.workstation_id == workstation_id,
                    XboxRelayModel.session_id != session_id,
                )
            )


class MemoryXboxRelayRepository:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, XboxRelayObligation] = {}

    async def get(self, session_id: uuid.UUID) -> XboxRelayObligation | None:
        return self._items.get(session_id)

    async def save(self, obligation: XboxRelayObligation) -> None:
        self._items[obligation.session_id] = obligation

    async def delete(self, session_id: uuid.UUID) -> None:
        self._items.pop(session_id, None)

    async def list_pending(self) -> list[XboxRelayObligation]:
        return [item for item in self._items.values() if item.pending]

    async def supersede(self, workstation_id: uuid.UUID, session_id: uuid.UUID) -> None:
        self._items = {
            key: item
            for key, item in self._items.items()
            if item.workstation_id != workstation_id or key == session_id
        }
