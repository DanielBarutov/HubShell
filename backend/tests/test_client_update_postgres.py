"""Durable all-PC deployment workflow with real admission transactions."""

import dataclasses
import datetime
import os
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.application.service import ClientUpdateService
from gameclub_backend.modules.client_updates.domain import DeploymentPhase, DeviceUpdateReport
from gameclub_backend.modules.client_updates.infrastructure.postgres import (
    DeploymentModel,
    PostgresDeploymentRepository,
)
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionAdmission,
    PostgresSessionRepository,
    SessionAdmissionBlockModel,
    SessionModel,
)
from gameclub_backend.modules.workstations.domain import Workstation
from gameclub_backend.modules.workstations.infrastructure.deployment_freeze import (
    PostgresWorkstationDeploymentFreeze,
    WorkstationFreezeModel,
)
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from test_session_admission_postgres import new_session

pytestmark = [pytest.mark.integration, pytest.mark.postgres]
HASH = "a" * 64
OPERATOR = Principal(
    "operator", SubjectType.OPERATOR, frozenset(), frozenset({"workstations.manage"})
)


def agent(device_id):
    return Principal(
        device_id, SubjectType.UPDATER, frozenset(), frozenset({"client_updates.report"})
    )


async def test_lost_creation_retry_preserves_targets_when_membership_has_grown(deployment_context):
    """Повтор создания возвращает исходный список, новые PC добавляются отдельным раундом."""
    _, _, service, value = deployment_context
    await service._workstations.save(Workstation(uuid.uuid4(), "new-pc", "New PC"))
    repeated = await service.create(OPERATOR, value.operation_id, value.release_id, HASH)
    assert repeated.id == value.id
    assert repeated.targets == value.targets
    assert "new-pc" not in repeated.targets
    refreshed = await service.refresh_targets(OPERATOR, value.id)
    assert "new-pc" in refreshed.targets


@pytest.fixture
async def deployment_context():
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to test coordinated deployment")
    engine = create_async_engine(dsn)

    def provider():
        return engine

    workstations = InMemoryWorkstationRepository()
    ids = (uuid.uuid4(), uuid.uuid4())
    for index, workstation_id in enumerate(ids):
        await workstations.save(Workstation(workstation_id, f"pc-{index}", f"PC {index}"))
    repository = PostgresDeploymentRepository(provider)
    service = ClientUpdateService(
        repository,
        PostgresSessionAdmission(provider),
        workstations,
        PostgresWorkstationDeploymentFreeze(provider),
    )
    value = await service.create(OPERATOR, uuid.uuid4(), "v2.4.0", HASH)
    try:
        yield provider, repository, service, value
    finally:
        async with engine.begin() as transaction:
            await transaction.execute(
                delete(WorkstationFreezeModel).where(
                    WorkstationFreezeModel.deployment_id == value.id
                )
            )
            await transaction.execute(
                delete(SessionAdmissionBlockModel).where(
                    SessionAdmissionBlockModel.deployment_id == value.id
                )
            )
            await transaction.execute(
                delete(SessionModel).where(SessionModel.workstation_id.in_(ids))
            )
            await transaction.execute(delete(DeploymentModel).where(DeploymentModel.id == value.id))
        await engine.dispose()


async def report_ready(service, value, device, *, stage="ready", installed_hash=None):
    previous = value.reports.get(device)
    return await service.report(
        agent(device),
        value.id,
        DeviceUpdateReport(
            device,
            value.round_id,
            previous.sequence + 1 if previous else 1,
            previous.instance_id if previous else uuid.uuid4(),
            datetime.datetime.now(datetime.UTC),
            False,
            0,
            True,
            stage,
            installed_hash,
        ),
    )


async def test_persisted_round_and_barrier_are_one_atomic_transition(deployment_context):
    """Активный сеанс откатывает смену раунда вместе с постановкой барьера."""
    provider, repository, service, value = deployment_context
    for device in value.targets:
        value = await report_ready(service, value, device)
    old_round = value.round_id
    session = new_session(next(iter(value.targets.values())))
    await PostgresSessionRepository(provider).save(session)
    with pytest.raises(ApplicationError, match="active session"):
        await service.prepare(OPERATOR, value.id)
    restored = await repository.get(value.id)
    assert restored.phase is DeploymentPhase.POLLING
    assert restored.round_id == old_round
    await PostgresSessionRepository(provider).save(
        session.stop(datetime.datetime.now(datetime.UTC))
    )
    prepared = await service.prepare(OPERATOR, value.id)
    assert prepared.phase is DeploymentPhase.PREPARING
    assert prepared.round_id != old_round
    with pytest.raises(ApplicationError, match="blocks new sessions"):
        await PostgresSessionRepository(provider).save(new_session(session.workstation_id))


async def test_full_deployment_reopens_only_after_all_gui_confirmations(
    deployment_context,
):
    """Служба и GUI независимо подтверждают всех клиентов перед снятием барьера."""
    provider, repository, service, value = deployment_context
    for device in value.targets:
        value = await report_ready(service, value, device)
    value = await service.prepare(OPERATOR, value.id)
    for device in value.targets:
        value = await report_ready(service, value, device)
    await service.server_ready(OPERATOR, value.id)
    value = await service.authorize(OPERATOR, value.id)
    recreated = PostgresDeploymentRepository(provider)
    assert (await recreated.get(value.id)).phase is DeploymentPhase.AUTHORIZED
    for device in sorted(value.targets):
        previous = value.reports[device]
        begin = dataclasses.replace(previous, sequence=previous.sequence + 1, stage="installing")
        value = await service.begin_install(agent(device), value.id, begin)
        value = await report_ready(service, value, device, stage="installed", installed_hash=HASH)
        with pytest.raises(ValueError, match="Every PC"):
            await service.finish(OPERATOR, value.id)
        principal = Principal(
            device, SubjectType.DEVICE, frozenset(), frozenset({"workstations.connect"})
        )
        value = await service.confirm_gui(principal, value.id, value.release_id)
    value = await service.finish(OPERATOR, value.id)
    assert value.phase is DeploymentPhase.COMPLETED
    await PostgresSessionRepository(provider).save(new_session(next(iter(value.targets.values()))))


async def test_operation_key_checks_contents_and_refuses_another_active_deployment(
    deployment_context,
):
    """Повтор запроса не меняет выпуск и не вытесняет незавершённую доставку."""
    _, _, service, value = deployment_context
    repeated = await service.create(OPERATOR, value.operation_id, value.release_id, HASH)
    assert repeated.id == value.id
    with pytest.raises(ApplicationError, match="reused"):
        await service.create(OPERATOR, value.operation_id, "other-release", HASH)
    with pytest.raises(ApplicationError, match="unfinished"):
        await service.create(OPERATOR, uuid.uuid4(), "other-release", HASH)


async def test_unprivileged_gui_and_wrong_device_cannot_report_for_updater(deployment_context):
    """Обычный GUI и чужая служба не могут отправлять отчёты обновления."""
    _, _, service, value = deployment_context
    device = next(iter(value.targets))
    report = DeviceUpdateReport(
        device, value.round_id, 1, uuid.uuid4(), datetime.datetime.now(datetime.UTC), False, 0, True
    )
    gui = Principal(device, SubjectType.DEVICE, frozenset(), frozenset({"workstations.connect"}))
    with pytest.raises(ApplicationError, match="Updater identity"):
        await service.report(gui, value.id, report)
    with pytest.raises(ApplicationError, match="Updater identity"):
        await service.report(agent("other-device"), value.id, report)
    with pytest.raises(ApplicationError, match="permission"):
        await service.prepare(gui, value.id)


async def test_updater_cannot_forge_independent_gui_confirmation(deployment_context):
    """Служба не может своим токеном подтвердить независимый запуск GUI."""
    _, _, service, value = deployment_context
    device = next(iter(value.targets))
    with pytest.raises(ApplicationError, match="Device identity"):
        await service.confirm_gui(agent(device), value.id, value.release_id)
