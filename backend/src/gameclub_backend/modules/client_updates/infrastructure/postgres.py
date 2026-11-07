"""Deployment persistence, with one transaction for state and Sessions admission."""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import typing
import uuid

from pydantic import TypeAdapter
from sqlalchemy import DateTime, String, bindparam, cast, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.infrastructure.database import (
    EngineProvider,
    application_transaction,
    open_session,
)
from gameclub_backend.modules.client_updates.domain import (
    ClientReleaseObservation,
    ClientReleasePolicy,
    Deployment,
    DeploymentPhase,
)

_DEPLOYMENT_LOCK = 5099317751
_codec = TypeAdapter(Deployment)
_policy_codec = TypeAdapter(ClientReleasePolicy)


class ClientUpdatesBase(DeclarativeBase):
    pass


class DeploymentModel(ClientUpdatesBase):
    __tablename__ = "client_update_deployments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, typing.Any]] = mapped_column(JSONB, nullable=False)


class ClientReleasePolicyModel(ClientUpdatesBase):
    __tablename__ = "client_release_policies"

    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, typing.Any]] = mapped_column(JSONB, nullable=False)


class RunningClientReleaseModel(ClientUpdatesBase):
    __tablename__ = "client_running_releases"

    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workstation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    installation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
                initial = old.previous_attempts[0] if old.previous_attempts else old
                if (
                    initial.release_id,
                    initial.executable_sha256,
                    old.created_by,
                    old.independent,
                ) != (
                    deployment.release_id,
                    deployment.executable_sha256,
                    deployment.created_by,
                    deployment.independent,
                ):
                    raise ApplicationError(ErrorCode.CONFLICT, "Deployment operation id reused")
                if deployment.independent and old.targets != deployment.targets:
                    raise ApplicationError(
                        ErrorCode.CONFLICT, "Deployment operation target changed"
                    )
                return old
            active = await transaction.scalars(
                select(DeploymentModel).where(
                    DeploymentModel.phase != DeploymentPhase.COMPLETED.value
                )
            )
            for model in active:
                old = _codec.validate_python(model.payload)
                if (
                    not deployment.independent
                    or not old.independent
                    or set(old.targets.values()) & set(deployment.targets.values())
                    or old.targets.keys() & deployment.targets.keys()
                ):
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

    @contextlib.asynccontextmanager
    async def policy_change(self) -> typing.AsyncIterator[None]:
        async with application_transaction(self._engine_provider) as transaction:
            await transaction.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEPLOYMENT_LOCK}
            )
            yield

    async def observe_release(
        self, device_id: str, workstation_id: uuid.UUID, installation_id: str, release_id: str
    ) -> None:
        async with application_transaction(self._engine_provider) as transaction:
            values = dict(
                device_id=device_id,
                workstation_id=workstation_id,
                installation_id=installation_id,
                release_id=release_id,
                observed_at=datetime.datetime.now(datetime.UTC),
            )
            await transaction.execute(
                insert(RunningClientReleaseModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[RunningClientReleaseModel.device_id], set_=values
                )
            )

    async def running_release(
        self, device_id: str, workstation_id: uuid.UUID, installation_id: str
    ) -> str | None:
        async with open_session(self._engine_provider) as transaction:
            now = datetime.datetime.now(datetime.UTC)
            return await transaction.scalar(
                select(RunningClientReleaseModel.release_id).where(
                    RunningClientReleaseModel.device_id == device_id,
                    RunningClientReleaseModel.workstation_id == workstation_id,
                    RunningClientReleaseModel.installation_id == installation_id,
                    RunningClientReleaseModel.observed_at >= now - datetime.timedelta(seconds=30),
                    RunningClientReleaseModel.observed_at <= now,
                )
            )

    async def publish_policy(self, policy: ClientReleasePolicy) -> ClientReleasePolicy:
        async with application_transaction(self._engine_provider) as transaction:
            await transaction.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEPLOYMENT_LOCK}
            )
            previous = await transaction.get(ClientReleasePolicyModel, policy.operation_id)
            if previous is not None:
                old = _policy_codec.validate_python(previous.payload)
                if dataclasses.replace(policy, created_at=old.created_at) != old:
                    raise ApplicationError(ErrorCode.CONFLICT, "Release policy operation id reused")
                return old
            existing = await transaction.scalar(
                select(ClientReleasePolicyModel)
                .where(ClientReleasePolicyModel.payload["release_id"].astext == policy.release_id)
                .limit(1)
            )
            if (
                existing is not None
                and existing.payload["executable_sha256"] != policy.executable_sha256
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Release identity cannot change executable"
                )
            policy = dataclasses.replace(policy, created_at=datetime.datetime.now(datetime.UTC))
            transaction.add(
                ClientReleasePolicyModel(
                    operation_id=policy.operation_id,
                    created_at=policy.created_at,
                    payload=_policy_codec.dump_python(policy, mode="json"),
                )
            )
            return policy

    async def current_policy(self) -> ClientReleasePolicy | None:
        async with open_session(self._engine_provider) as transaction:
            model = await transaction.scalar(
                select(ClientReleasePolicyModel)
                .order_by(
                    ClientReleasePolicyModel.created_at.desc(),
                    ClientReleasePolicyModel.operation_id.desc(),
                )
                .limit(1)
            )
            return _policy_codec.validate_python(model.payload) if model else None

    async def assign_current(self, device_id: str, workstation_id: uuid.UUID) -> Deployment | None:
        async with application_transaction(self._engine_provider) as transaction:
            await transaction.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEPLOYMENT_LOCK}
            )
            previous = await self.latest_for_device(device_id)
            if previous is not None and previous.phase is not DeploymentPhase.COMPLETED:
                return previous
            policy = await self.current_policy()
            if policy is None:
                return previous
            if (
                previous is not None
                and previous.release_id == policy.release_id
                and previous.executable_sha256 == policy.executable_sha256
                and previous.targets.get(device_id) == workstation_id
            ):
                observed = await transaction.get(RunningClientReleaseModel, device_id)
                if observed is None or observed.release_id == policy.release_id:
                    return previous
            return await self.create(
                Deployment(
                    id=uuid.uuid4(),
                    operation_id=uuid.uuid4(),
                    release_id=policy.release_id,
                    executable_sha256=policy.executable_sha256,
                    targets={device_id: workstation_id},
                    created_by=policy.created_by,
                    created_at=datetime.datetime.now(datetime.UTC),
                    independent=True,
                )
            )

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

    async def latest_for_devices(self, device_ids: tuple[str, ...]) -> dict[str, Deployment]:
        if not device_ids:
            return {}
        statement = text("""
            SELECT DISTINCT ON (target.device_id) target.device_id, deployment.payload
            FROM client_update_deployments AS deployment
            CROSS JOIN LATERAL jsonb_object_keys(deployment.payload->'targets') AS target(device_id)
            WHERE target.device_id IN :device_ids
            ORDER BY target.device_id, (deployment.payload->>'created_at')::timestamptz DESC,
                     deployment.id DESC
        """).bindparams(bindparam("device_ids", expanding=True))
        async with open_session(self._engine_provider) as transaction:
            rows = await transaction.execute(statement, {"device_ids": device_ids})
            return {row.device_id: _codec.validate_python(row.payload) for row in rows}

    async def release_observations(
        self, device_ids: tuple[str, ...]
    ) -> dict[str, ClientReleaseObservation]:
        if not device_ids:
            return {}
        async with open_session(self._engine_provider) as transaction:
            models = await transaction.scalars(
                select(RunningClientReleaseModel).where(
                    RunningClientReleaseModel.device_id.in_(device_ids)
                )
            )
            return {
                model.device_id: ClientReleaseObservation(
                    model.device_id,
                    model.workstation_id,
                    model.installation_id,
                    model.release_id,
                    model.observed_at,
                )
                for model in models
            }

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
