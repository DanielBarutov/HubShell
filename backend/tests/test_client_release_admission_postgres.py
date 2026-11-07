"""Release admission uses real GUI JWT, PostgreSQL and the public Sessions writers."""

import asyncio
import contextvars
import dataclasses
import datetime
import uuid

import pytest
from sqlalchemy import delete, update

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.infrastructure.database import application_transaction, open_session
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.application.admission import (
    ClientReleaseAdmissionService,
)
from gameclub_backend.modules.client_updates.infrastructure.postgres import (
    ClientReleasePolicyModel,
    PostgresDeploymentRepository,
    RunningClientReleaseModel,
)
from gameclub_backend.modules.sessions.domain import TransferStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionAdmission,
    PostgresSessionRepository,
    PostgresSessionTransactionWriter,
    SessionModel,
)
from gameclub_backend.modules.sessions.infrastructure.transfers_postgres import (
    PostgresSessionTransferRepository,
    SessionTransferOfferModel,
)
from test_client_release_store import signed_release
from test_client_update_agent_e2e import second_update_pc as second_update_pc
from test_client_update_http_postgres import http_updates as http_updates
from test_session_admission_postgres import new_session, transfer_offer

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.api]
PREFIX = "/api/v1/client-updates"


@pytest.fixture
async def release_admission(http_updates):
    client, operator, workstation, workstations, app, root = http_updates
    signed_release(root)

    def provider():
        return app.state.resources.engine

    repository = PostgresDeploymentRepository(provider)
    gate = ClientReleaseAdmissionService(repository, workstations)
    sessions = PostgresSessionRepository(provider, gate)
    operations = []

    async def publish(accepted):
        operation = uuid.uuid4()
        operations.append(operation)
        response = await client.post(
            f"{PREFIX}/policy",
            headers=operator,
            json={
                "operation_id": str(operation),
                "release_id": "signed-v1",
                "accepted_release_ids": accepted,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def observe(release):
        current = await workstations.get(workstation.id)
        gui_token, _ = app.state.jwt_service.issue_access_token(
            Principal(
                workstation.device_id,
                SubjectType.DEVICE,
                frozenset(),
                frozenset({"workstations.connect"}),
                installation_id=current.installation_id,
            )
        )
        response = await client.get(
            f"{PREFIX}/gui/current",
            params={"release_id": release},
            headers={"Authorization": "Bearer " + gui_token},
        )
        assert response.status_code == 200, response.text
        return response.json()

    try:
        yield provider, gate, sessions, publish, observe
    finally:
        async with provider().begin() as transaction:
            await transaction.execute(
                delete(SessionModel).where(SessionModel.workstation_id == workstation.id)
            )
            await transaction.execute(
                delete(RunningClientReleaseModel).where(
                    RunningClientReleaseModel.device_id == workstation.device_id
                )
            )
            await transaction.execute(
                delete(ClientReleasePolicyModel).where(
                    ClientReleasePolicyModel.operation_id.in_(operations)
                )
            )


async def test_gui_release_controls_new_access_but_preserves_active_play(
    http_updates, release_admission
):
    """Допуск требует свежего GUI текущей установки; активная игра сохраняется."""
    _, _, workstation, workstations, _, _ = http_updates
    provider, gate, sessions, publish, observe = release_admission
    await publish(["previous-v1"])
    active = new_session(workstation.id)
    with pytest.raises(ApplicationError, match="release must be updated"):
        await sessions.save(active)
    assert (await observe("previous-v1"))["release_allowed"]
    await sessions.save(active)
    await publish([])
    assert not (await observe("previous-v1"))["release_allowed"]
    await sessions.save(active)
    async with open_session(provider) as transaction:
        async with transaction.begin():
            await PostgresSessionTransactionWriter(gate).require_access(transaction, active.id)
    stopped = active.stop(datetime.datetime.now(datetime.UTC))
    await sessions.save(stopped)
    with pytest.raises(ApplicationError, match="release must be updated"):
        await sessions.save(active)
    async with open_session(provider) as transaction:
        async with transaction.begin():
            with pytest.raises(ApplicationError, match="release must be updated"):
                await PostgresSessionTransactionWriter(gate).require_access(transaction, active.id)
    assert (await observe("signed-v1"))["release_allowed"]
    await sessions.save(active)
    await sessions.save(stopped)
    async with provider().begin() as transaction:
        await transaction.execute(
            update(RunningClientReleaseModel)
            .where(RunningClientReleaseModel.device_id == workstation.device_id)
            .values(
                observed_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=31)
            )
        )
    with pytest.raises(ApplicationError, match="release must be updated"):
        await sessions.save(active)
    await observe("signed-v1")
    await workstations.save(dataclasses.replace(workstation, installation_id=uuid.uuid4().hex))
    with pytest.raises(ApplicationError, match="release must be updated"):
        await sessions.save(active)
    await observe("signed-v1")
    await sessions.save(active)


async def test_transfer_to_incompatible_pc_preserves_source(
    http_updates, second_update_pc, release_admission
):
    """Несовместимый целевой ПК не получает перенос: исходная сессия и offer сохраняются."""
    _, _, first, _, _, _ = http_updates
    provider, gate, _, publish, observe = release_admission
    ids = (first.id, second_update_pc.id)
    transfers, offer, moved = await transfer_offer(provider, ids)
    try:
        await publish([])
        await observe("signed-v1")
        with pytest.raises(ApplicationError, match="release must be updated"):
            await PostgresSessionTransferRepository(provider, gate).commit_transfer(offer, moved)
        assert (await PostgresSessionRepository(provider).get(moved.id)).workstation_id == first.id
        assert (await transfers.get(offer.id)).status is TransferStatus.PENDING
    finally:
        async with provider().begin() as transaction:
            await transaction.execute(
                delete(SessionTransferOfferModel).where(SessionTransferOfferModel.id == offer.id)
            )
            await transaction.execute(delete(SessionModel).where(SessionModel.id == moved.id))


async def test_release_policy_change_serializes_with_new_session(http_updates, release_admission):
    """Новый вход ждёт фиксации изменения политики и затем проверяет уже новый список выпусков."""
    _, _, workstation, _, _, _ = http_updates
    provider, _, sessions, publish, observe = release_admission
    await publish(["previous-v1"])
    await observe("previous-v1")
    started = asyncio.Event()

    async def start():
        started.set()
        return await sessions.save(new_session(workstation.id))

    async with (
        PostgresDeploymentRepository(provider).policy_change(),
        PostgresSessionAdmission(provider).policy_change(),
    ):
        await publish([])
        task = asyncio.create_task(start(), context=contextvars.Context())
        await started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 0.1)
    with pytest.raises(ApplicationError, match="release must be updated"):
        await asyncio.wait_for(task, 3)


async def test_policy_waits_for_inflight_start_and_preserves_its_session(
    http_updates, release_admission
):
    """Смена политики ждёт уже начатый вход и не завершает созданную сессию."""
    _, _, workstation, _, _, _ = http_updates
    provider, _, sessions, publish, observe = release_admission
    await publish(["previous-v1"])
    await observe("previous-v1")
    active = new_session(workstation.id)
    started = asyncio.Event()

    async def change():
        started.set()
        return await publish([])

    async with application_transaction(provider):
        await sessions.save(active)
        task = asyncio.create_task(change(), context=contextvars.Context())
        await started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 0.1)
    await asyncio.wait_for(task, 3)
    assert (await sessions.get(active.id)).status == active.status
    await sessions.save(active)


async def test_old_or_unbound_gui_token_cannot_attest_new_installation(
    http_updates, release_admission
):
    """JWT прежней установки и токен без привязки не подтверждают выпуск новой установки."""
    client, _, workstation, workstations, app, _ = http_updates
    _, _, _, publish, _ = release_admission
    await publish([])
    old, _ = app.state.jwt_service.issue_access_token(
        Principal(
            workstation.device_id,
            SubjectType.DEVICE,
            frozenset(),
            frozenset({"workstations.connect"}),
            installation_id=workstation.installation_id,
        )
    )
    unbound, _ = app.state.jwt_service.issue_access_token(
        Principal(
            workstation.device_id,
            SubjectType.DEVICE,
            frozenset(),
            frozenset({"workstations.connect"}),
        )
    )
    await workstations.save(dataclasses.replace(workstation, installation_id=uuid.uuid4().hex))
    for token in (old, unbound):
        response = await client.get(
            f"{PREFIX}/gui/current",
            params={"release_id": "signed-v1"},
            headers={"Authorization": "Bearer " + token},
        )
        assert response.status_code == 401, response.text


async def test_pc_release_policy_does_not_block_xbox(http_updates, release_admission):
    """Политика Windows-клиента не требует GUI-подтверждения для Xbox."""
    from gameclub_backend.domain.equipment import EquipmentType
    from gameclub_backend.modules.workstations.domain import WorkstationSessionMode

    _, _, workstation, workstations, _, _ = http_updates
    _, gate, _, publish, _ = release_admission
    await publish([])
    await workstations.save(
        dataclasses.replace(
            workstation,
            equipment_type=EquipmentType.XBOX,
            session_mode=WorkstationSessionMode.SERVER_OWNED,
            device_id=None,
            installation_id=None,
            mac_address=None,
        )
    )
    await gate.require_release(workstation.id)
