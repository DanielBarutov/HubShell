from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.client_groups.domain import ClientGroup
from gameclub_backend.modules.clients.infrastructure.postgres import ClientModel


class ClientGroupBase(DeclarativeBase):
    pass


class ClientGroupModel(ClientGroupBase):
    __tablename__ = "client_groups"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    allow_negative_balance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    negative_balance_limit_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    def to_domain(self) -> ClientGroup:
        return ClientGroup(
            id=self.id,
            name=self.name,
            allow_negative_balance=self.allow_negative_balance,
            negative_balance_limit_cents=self.negative_balance_limit_cents,
            active=self.active,
            is_default=self.is_default,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, group: ClientGroup) -> ClientGroupModel:
        return cls(
            id=group.id,
            name=group.name,
            allow_negative_balance=group.allow_negative_balance,
            negative_balance_limit_cents=group.negative_balance_limit_cents,
            active=group.active,
            is_default=group.is_default,
            updated_at=group.updated_at or datetime.datetime.now(datetime.UTC),
        )


class PostgresClientGroupRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, group_id: str) -> ClientGroup | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ClientGroupModel, group_id.strip().lower())
            return model.to_domain() if model else None

    async def list(self) -> list[ClientGroup]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(select(ClientGroupModel).order_by(ClientGroupModel.id))
            return [model.to_domain() for model in result]

    async def get_default(self) -> ClientGroup | None:
        async with open_session(self._engine_provider) as session:
            model = await session.scalar(
                select(ClientGroupModel).where(
                    ClientGroupModel.active.is_(True), ClientGroupModel.is_default.is_(True)
                )
            )
            return model.to_domain() if model else None

    async def save(self, group: ClientGroup) -> ClientGroup:
        async with open_session(self._engine_provider) as session:
            if group.is_default:
                await session.execute(
                    update(ClientGroupModel).values(is_default=False).where(
                        ClientGroupModel.id != group.id
                    )
                )
            model = await session.get(ClientGroupModel, group.id)
            if model is None:
                session.add(ClientGroupModel.from_domain(group))
            else:
                model.name = group.name
                model.allow_negative_balance = group.allow_negative_balance
                model.negative_balance_limit_cents = group.negative_balance_limit_cents
                model.active = group.active
                model.is_default = group.is_default
                model.updated_at = group.updated_at or datetime.datetime.now(datetime.UTC)
            await session.commit()
            return group

    async def delete(self, group_id: str) -> None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(ClientGroupModel, group_id.strip().lower())
            if model is not None:
                await session.delete(model)
                await session.commit()

    async def count_clients(self, group_id: str) -> int:
        from sqlalchemy import func

        async with open_session(self._engine_provider) as session:
            return int(
                await session.scalar(
                    select(func.count(ClientModel.id)).where(
                        ClientModel.client_group_id == group_id.strip().lower()
                    )
                )
                or 0
            )
