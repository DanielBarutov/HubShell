"""Workstations-owned membership freeze; heartbeat and telemetry remain writable."""

from __future__ import annotations

import uuid

from sqlalchemy import Integer, delete, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.infrastructure.database import EngineProvider, begin_session, open_session

_MEMBERSHIP_LOCK = 5099317752


class WorkstationFreezeBase(DeclarativeBase):
    pass


class WorkstationFreezeModel(WorkstationFreezeBase):
    __tablename__ = "workstation_deployment_freeze"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deployment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


async def require_membership_change_allowed(transaction: AsyncSession) -> None:
    await transaction.execute(
        text("SELECT pg_advisory_xact_lock_shared(:key)"), {"key": _MEMBERSHIP_LOCK}
    )
    if await transaction.get(WorkstationFreezeModel, 1) is not None:
        raise ApplicationError(ErrorCode.CONFLICT, "Client update freezes workstation membership")


class PostgresWorkstationDeploymentFreeze:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def freeze(self, deployment_id: uuid.UUID) -> None:
        async with open_session(self._engine_provider) as transaction:
            async with begin_session(transaction):
                await transaction.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": _MEMBERSHIP_LOCK}
                )
                row = await transaction.get(WorkstationFreezeModel, 1)
                if row is not None and row.deployment_id != deployment_id:
                    raise ApplicationError(
                        ErrorCode.CONFLICT, "Another deployment freezes membership"
                    )
                if row is None:
                    transaction.add(WorkstationFreezeModel(id=1, deployment_id=deployment_id))

    async def unfreeze(self, deployment_id: uuid.UUID) -> None:
        async with open_session(self._engine_provider) as transaction:
            async with begin_session(transaction):
                await transaction.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": _MEMBERSHIP_LOCK}
                )
                await transaction.execute(
                    delete(WorkstationFreezeModel).where(
                        WorkstationFreezeModel.deployment_id == deployment_id
                    )
                )
