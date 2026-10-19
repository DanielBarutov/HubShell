"""Deployment persistence, with one transaction for state and Sessions admission."""

from __future__ import annotations

import contextlib
import typing
import uuid

from pydantic import TypeAdapter
from sqlalchemy import DateTime, String, cast, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.infrastructure.database import (
    EngineProvider,
    application_transaction,
    open_session,
)
from gameclub_backend.modules.client_updates.domain import Deployment, DeploymentPhase

_DEPLOYMENT_LOCK = 5099317751
_codec = TypeAdapter(Deployment)


class ClientUpdatesBase(DeclarativeBase):
    pass


class DeploymentModel(ClientUpdatesBase):
    __tablename__ = "client_update_deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, typing.Any]] = mapped_column(JSONB, nullable=False)


class PostgresDeploymentRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def create(self, deployment: Deployment) -> Deployment:
        async with application_transaction(self._engine_provider) as transaction:
            await transaction.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEPLOYMENT_LOCK}
            )
            repeated = await transaction.scalar(
                select(DeploymentModel).where(
                    DeploymentModel.operation_id == deployment.operation_id
                )
            )
            if repeated is not None:
                old = _codec.validate_python(repeated.payload)
                if (old.release_id, old.executable_sha256, old.created_by) != (
                    deployment.release_id,
                    deployment.executable_sha256,
                    deployment.created_by,
                ):
                    raise ApplicationError(ErrorCode.CONFLICT, "Deployment operation id reused")
                return old
            active = await transaction.scalar(
                select(DeploymentModel.id)
                .where(DeploymentModel.phase != DeploymentPhase.COMPLETED.value)
                .limit(1)
            )
            if active is not None:
                raise ApplicationError(ErrorCode.CONFLICT, "Another deployment is unfinished")
            transaction.add(
                DeploymentModel(
                    id=deployment.id,
                    operation_id=deployment.operation_id,
                    phase=deployment.phase.value,
                    payload=_codec.dump_python(deployment, mode="json"),
                )
            )
            return deployment

    async def get(self, deployment_id: uuid.UUID) -> Deployment | None:
        async with open_session(self._engine_provider) as transaction:
            model = await transaction.get(DeploymentModel, deployment_id)
            return _codec.validate_python(model.payload) if model is not None else None

    async def latest_for_device(self, device_id: str) -> Deployment | None:
        async with open_session(self._engine_provider) as transaction:
            model = await transaction.scalar(
                select(DeploymentModel)
                .where(DeploymentModel.payload["targets"].op("?")(device_id))
                .order_by(
                    cast(
                        DeploymentModel.payload["created_at"].astext, DateTime(timezone=True)
                    ).desc()
                )
                .limit(1)
            )
            return _codec.validate_python(model.payload) if model else None

    async def latest(self) -> Deployment | None:
        async with open_session(self._engine_provider) as transaction:
            model = await transaction.scalar(
                select(DeploymentModel)
                .order_by(
                    cast(
                        DeploymentModel.payload["created_at"].astext, DateTime(timezone=True)
                    ).desc()
                )
                .limit(1)
            )
            return _codec.validate_python(model.payload) if model else None

    @contextlib.asynccontextmanager
    async def change(self, deployment_id: uuid.UUID) -> typing.AsyncIterator[Deployment]:
        async with application_transaction(self._engine_provider) as transaction:
            await transaction.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEPLOYMENT_LOCK}
            )
            model = await transaction.get(DeploymentModel, deployment_id, with_for_update=True)
            if model is None:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Deployment not found")
            value = _codec.validate_python(model.payload)
            yield value
            model.phase = value.phase.value
            model.payload = _codec.dump_python(value, mode="json")
