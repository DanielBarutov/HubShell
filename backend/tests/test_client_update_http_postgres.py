"""Real authenticated HTTP/DB protocol for updater enrollment and fleet admission."""

import dataclasses
import datetime
import os
import uuid

import httpx
import pytest
from sqlalchemy import delete, select

from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.infrastructure.credentials_postgres import (
    UpdaterCredentialModel,
)
from gameclub_backend.modules.client_updates.infrastructure.postgres import DeploymentModel
from gameclub_backend.modules.sessions.infrastructure.postgres import SessionAdmissionBlockModel
from gameclub_backend.modules.workstations.domain import Workstation
from gameclub_backend.modules.workstations.infrastructure.deployment_freeze import (
    WorkstationFreezeModel,
)
from gameclub_backend.modules.workstations.infrastructure.postgres import (
    PostgresWorkstationRepository,
    WorkstationModel,
)
from gameclub_backend.presentation.http.app import create_app

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.api]
PREFIX = "/api/v1/client-updates"


async def test_operator_current_status_keeps_unready_pc_and_denies_updater(http_updates):
    """Статус для настроек сохраняет весь парк и недоступен служебному JWT."""
    client, operator, workstation, _, _, _ = http_updates
    empty = await client.get(f"{PREFIX}/current", headers=operator)
    assert empty.status_code == 200
    assert empty.json() == {"deployment": None}
    assert empty.headers["cache-control"] == "no-store"
    _, agent = await enroll_agent(client, operator, workstation.device_id)
    assert (await client.get(f"{PREFIX}/current", headers=agent)).status_code == 403
    creation = await client.post(
        PREFIX,
        headers=operator,
        json={
            "operation_id": str(uuid.uuid4()),
            "release_id": "status-test",
            "executable_sha256": "a" * 64,
        },
    )
    value = creation.json()
    response = await client.post(
        f"{PREFIX}/{value['id']}/reports",
        headers=agent,
        json={
            "round_id": value["round_id"],
            "instance_id": str(uuid.uuid4()),
            "sequence": 1,
            "active_session": False,
            "pending_facts": 0,
            "ready": False,
            "stage": "ready",
            "running_release_id": "v-old",
            "error_code": "gui_unavailable",
        },
    )
    assert response.status_code == 200
    current = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
    assert current["id"] == value["id"]
    assert (current["confirmed"], current["total"]) == (0, 1)
    assert current["devices"][0]["status"] == "not_ready"
    assert current["devices"][0]["old_release_id"] == "v-old"


@pytest.fixture
async def http_updates(tmp_path):
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN for updater HTTP checks")
    settings = Settings(
        postgres_dsn=dsn,
        redis_url=None,
        jwt_secret="update-tests-secret-with-at-least-32-characters",
        jwt_access_ttl_seconds=3600,
        dev_operator_username="operator",
        dev_operator_password="test-password",
        client_release_root=str(tmp_path),
    )
    app = create_app(settings)
    engine = app.state.resources.engine

    def provider():
        return engine

    repository = PostgresWorkstationRepository(provider)
    workstation = Workstation(
        uuid.uuid4(),
        "update-http-" + uuid.uuid4().hex,
        "Update PC",
        installation_id=uuid.uuid4().hex,
    )
    await repository.save(workstation)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                login = await client.post(
                    "/api/v1/auth/token", json={"username": "operator", "password": "test-password"}
                )
                login.raise_for_status()
                operator = {"Authorization": "Bearer " + login.json()["access_token"]}
                yield client, operator, workstation, repository, app, tmp_path
    finally:
        # Lifespan disposes the pool but the engine can open a fresh cleanup connection.
        async with engine.begin() as transaction:
            own_deployments = select(DeploymentModel.id).where(
                DeploymentModel.payload["targets"].op("?")(workstation.device_id)
            )
            await transaction.execute(
                delete(WorkstationFreezeModel).where(
                    WorkstationFreezeModel.deployment_id.in_(own_deployments)
                )
            )
            await transaction.execute(
                delete(SessionAdmissionBlockModel).where(
                    SessionAdmissionBlockModel.deployment_id.in_(own_deployments)
                )
            )
            await transaction.execute(
                delete(DeploymentModel).where(
                    DeploymentModel.payload["targets"].op("?")(workstation.device_id)
                )
            )
            await transaction.execute(
                delete(UpdaterCredentialModel).where(
                    UpdaterCredentialModel.device_id == workstation.device_id
                )
            )
            await transaction.execute(
                delete(WorkstationModel).where(WorkstationModel.id == workstation.id)
            )
        await engine.dispose()


async def enroll_agent(client, operator, device_id):
    response = await client.post(f"{PREFIX}/credentials/{device_id}", headers=operator)
    response.raise_for_status()
    credential = response.json()
    token = await client.post(
        f"{PREFIX}/agent-token",
        json={"device_id": device_id, "credential_secret": credential["credential_secret"]},
    )
    token.raise_for_status()
    assert 0 < token.json()["expires_in"] <= 900
    return credential, {"Authorization": "Bearer " + token.json()["access_token"]}


async def test_updater_rotation_revokes_existing_jwt_and_cannot_act_as_gui(http_updates):
    """Перевыпуск секрета отзывает старый JWT, updater не подменяет GUI или финансовые события."""
    client, operator, workstation, _, app, _ = http_updates
    credential, headers = await enroll_agent(client, operator, workstation.device_id)
    current = await client.get(
        f"{PREFIX}/agent/current", params={"instance_id": str(uuid.uuid4())}, headers=headers
    )
    assert current.status_code == 200
    assert current.headers["cache-control"] == "no-store"
    assert current.json()["deployment"] is None
    assert (await client.get(f"{PREFIX}/gui/current", headers=headers)).status_code == 403
    assert (
        await client.post("/api/events/client-facts", content=b"", headers=headers)
    ).status_code == 403
    principal = app.state.jwt_service.validate_access_token(headers["Authorization"].split()[1])
    assert principal.subject_type is SubjectType.UPDATER
    assert not principal.can("workstations.connect")
    await client.post(f"{PREFIX}/credentials/{workstation.device_id}", headers=operator)
    assert (
        await client.get(
            f"{PREFIX}/agent/current", params={"instance_id": str(uuid.uuid4())}, headers=headers
        )
    ).status_code == 401
    old = await client.post(
        f"{PREFIX}/agent-token",
        json={
            "device_id": workstation.device_id,
            "credential_secret": credential["credential_secret"],
        },
    )
    assert old.status_code == 401
    assert credential["credential_secret"] not in old.text


async def test_http_protocol_requires_final_poll_and_both_success_confirmations(http_updates):
    """Общее разрешение требует второго опроса, завершение — двух независимых подтверждений."""
    client, operator, workstation, _, app, _ = http_updates
    _, agent = await enroll_agent(client, operator, workstation.device_id)
    creation = await client.post(
        PREFIX,
        headers=operator,
        json={
            "operation_id": str(uuid.uuid4()),
            "release_id": "v2.4.0",
            "executable_sha256": "a" * 64,
        },
    )
    creation.raise_for_status()
    value = creation.json()
    instance = str(uuid.uuid4())

    async def report(sequence, stage="ready"):
        return await client.post(
            f"{PREFIX}/{value['id']}/reports",
            headers=agent,
            json={
                "round_id": value["round_id"],
                "sequence": sequence,
                "instance_id": instance,
                "active_session": False,
                "pending_facts": 0,
                "ready": True,
                "stage": stage,
                "installed_sha256": "a" * 64 if stage == "installed" else None,
                "running_release_id": "v2.4.0" if stage == "installed" else "v-old",
            },
        )

    assert (await report(1)).status_code == 200
    prepared = await client.post(f"{PREFIX}/{value['id']}/prepare", headers=operator)
    prepared.raise_for_status()
    value = prepared.json()
    assert (
        await client.post(f"{PREFIX}/{value['id']}/server-ready", headers=operator)
    ).status_code == 200
    assert (
        await client.post(f"{PREFIX}/{value['id']}/authorize", headers=operator)
    ).status_code == 409
    assert (await report(1)).status_code == 200
    assert (
        await client.post(f"{PREFIX}/{value['id']}/authorize", headers=operator)
    ).status_code == 200
    command = await client.get(
        f"{PREFIX}/agent/current", headers=agent, params={"instance_id": instance}
    )
    assert command.json()["deployment"]["may_install"]
    other_instance = await client.get(
        f"{PREFIX}/agent/current", headers=agent, params={"instance_id": str(uuid.uuid4())}
    )
    assert not other_instance.json()["deployment"]["may_install"]
    assert (await report(2, "installed")).status_code == 409
    begin = await client.post(
        f"{PREFIX}/{value['id']}/begin-install",
        headers=agent,
        json={
            "round_id": value["round_id"],
            "sequence": 2,
            "instance_id": instance,
            "active_session": False,
            "pending_facts": 0,
            "ready": True,
        },
    )
    assert begin.status_code == 200
    repeated = await client.post(
        f"{PREFIX}/{value['id']}/begin-install",
        headers=agent,
        json={
            "round_id": value["round_id"],
            "sequence": 2,
            "instance_id": instance,
            "active_session": False,
            "pending_facts": 0,
            "ready": True,
        },
    )
    assert repeated.status_code == 200
    assert (await report(3, "installed")).status_code == 200
    assert (
        await client.post(f"{PREFIX}/{value['id']}/finish", headers=operator)
    ).status_code == 409
    token, _ = app.state.jwt_service.issue_access_token(
        Principal(
            workstation.device_id,
            SubjectType.DEVICE,
            frozenset({"device"}),
            frozenset({"workstations.connect"}),
        )
    )
    gui = {"Authorization": "Bearer " + token}
    assert (
        await client.post(
            f"{PREFIX}/{value['id']}/gui-confirm", headers=agent, json={"release_id": "v2.4.0"}
        )
    ).status_code == 403
    assert (
        await client.post(
            f"{PREFIX}/{value['id']}/gui-confirm", headers=gui, json={"release_id": "v2.4.0"}
        )
    ).status_code == 200
    finished = await client.post(f"{PREFIX}/{value['id']}/finish", headers=operator)
    assert finished.json()["phase"] == "completed"
    assert finished.json()["old_releases"][workstation.device_id] == "v-old"
    assert finished.json()["reports"][workstation.device_id]["running_release_id"] == "v2.4.0"
    current = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
    assert current["phase"] == "completed"
    assert (current["confirmed"], current["total"]) == (1, 1)
    assert current["devices"][0]["status"] == "confirmed"


async def test_frozen_membership_blocks_assignment_but_allows_heartbeat(http_updates):
    """После подготовки привязки ПК неизменяемы, но heartbeat продолжает обновляться."""
    from gameclub_backend.application.errors import ApplicationError

    client, operator, workstation, repository, _, _ = http_updates
    _, agent = await enroll_agent(client, operator, workstation.device_id)
    created = await client.post(
        PREFIX,
        headers=operator,
        json={
            "operation_id": str(uuid.uuid4()),
            "release_id": "freeze-test",
            "executable_sha256": "a" * 64,
        },
    )
    value = created.json()
    await client.post(
        f"{PREFIX}/{value['id']}/reports",
        headers=agent,
        json={
            "round_id": value["round_id"],
            "sequence": 1,
            "instance_id": str(uuid.uuid4()),
            "active_session": False,
            "pending_facts": 0,
            "ready": True,
            "stage": "ready",
        },
    )
    prepared = await client.post(f"{PREFIX}/{value['id']}/prepare", headers=operator)
    assert prepared.status_code == 200
    with pytest.raises(ApplicationError, match="freezes workstation"):
        await repository.save(
            dataclasses.replace(workstation, installation_id="different-installation")
        )
    with pytest.raises(ApplicationError, match="freezes workstation"):
        await repository.delete(workstation.id)
    heartbeat = dataclasses.replace(workstation, last_seen_at=datetime.datetime.now(datetime.UTC))
    assert (await repository.save(heartbeat)).last_seen_at is not None


async def test_mirror_only_serves_allowed_files_and_errors_do_not_echo_secrets(http_updates):
    """Зеркало не отдаёт произвольные файлы, ошибки валидации не раскрывают секрет службы."""
    client, _, _, _, _, root = http_updates
    (root / "v1").mkdir()
    (root / "v1" / "release.json").write_text("manifest")
    (root / "v1" / "private.pem").write_text("private material")
    assert (await client.get(f"{PREFIX}/releases/v1/release.json")).content == b"manifest"
    assert (await client.get(f"{PREFIX}/releases/v1/private.pem")).status_code == 404
    response = await client.post(
        f"{PREFIX}/agent-token", json={"credential_secret": "secret-should-not-be-echoed"}
    )
    assert response.status_code == 400
    assert "secret-should-not-be-echoed" not in response.text


async def test_refresh_includes_new_pc_and_invalidates_old_probe_round(http_updates):
    """Новый ПК добавляется только через новый опрос, прежние цели не исключаются."""
    client, operator, workstation, repository, _, _ = http_updates
    created = await client.post(
        PREFIX,
        headers=operator,
        json={
            "operation_id": str(uuid.uuid4()),
            "release_id": "new-pc",
            "executable_sha256": "a" * 64,
        },
    )
    value = created.json()
    extra = Workstation(
        uuid.uuid4(), "update-extra-" + uuid.uuid4().hex, "New PC", installation_id=uuid.uuid4().hex
    )
    await repository.save(extra)
    try:
        refreshed = await client.post(f"{PREFIX}/{value['id']}/refresh-targets", headers=operator)
        refreshed.raise_for_status()
        assert refreshed.json()["round_id"] != value["round_id"]
        assert set(refreshed.json()["targets"]) == {workstation.device_id, extra.device_id}
        assert refreshed.json()["reports"] == {}
        # A removed/archived target cannot silently disappear from the denominator.
        await repository.save(
            dataclasses.replace(extra, archived_at=datetime.datetime.now(datetime.UTC))
        )
        assert (
            await client.post(f"{PREFIX}/{value['id']}/refresh-targets", headers=operator)
        ).status_code == 409
    finally:
        await repository.delete(extra.id)


async def test_membership_mutation_waits_for_final_freeze_then_is_rejected(http_updates):
    """Регистрация, начатая во время фиксации парка, ждёт транзакцию и получает отказ."""
    import asyncio
    import contextvars

    from gameclub_backend.application.errors import ApplicationError
    from gameclub_backend.infrastructure.database import application_transaction
    from gameclub_backend.modules.workstations.infrastructure.deployment_freeze import (
        PostgresWorkstationDeploymentFreeze,
    )

    _, _, _, repository, app, _ = http_updates
    engine = app.state.resources.engine

    def provider():
        return engine

    freeze = PostgresWorkstationDeploymentFreeze(provider)
    owner = uuid.uuid4()
    extra = Workstation(uuid.uuid4(), "update-race-" + uuid.uuid4().hex, "Racing PC")
    entered = asyncio.Event()

    async def register():
        entered.set()
        await repository.save(extra)

    try:
        async with application_transaction(provider):
            await freeze.freeze(owner)
            task = asyncio.create_task(register(), context=contextvars.Context())
            await entered.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), 0.1)
        with pytest.raises(ApplicationError, match="freezes workstation"):
            await asyncio.wait_for(task, 3)
    finally:
        await freeze.unfreeze(owner)
        await repository.delete(extra.id)


async def test_kafka_ingress_ack_does_not_substitute_confirmed_financial_checkpoint(http_updates):
    """Пустой outbox не разрешает обновление, пока точный checkpoint не подтверждён сервером."""
    from gameclub_backend.modules.eventing_v2.domain import V2SessionChain
    from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
        PostgresV2SessionChainRepository,
        V2SessionChainModel,
    )

    client, operator, workstation, _, app, _ = http_updates
    _, agent = await enroll_agent(client, operator, workstation.device_id)
    created = await client.post(
        PREFIX,
        headers=operator,
        json={
            "operation_id": str(uuid.uuid4()),
            "release_id": "financial-check",
            "executable_sha256": "a" * 64,
        },
    )
    value = created.json()
    session_id = uuid.uuid4()
    report = {
        "round_id": value["round_id"],
        "sequence": 1,
        "instance_id": str(uuid.uuid4()),
        "active_session": False,
        "pending_facts": 0,
        "ready": True,
        "stage": "ready",
        "session_id": str(session_id),
        "last_sequence": 3,
        "last_payload_hash": "b" * 64,
    }
    assert (
        await client.post(f"{PREFIX}/{value['id']}/reports", headers=agent, json=report)
    ).status_code == 200
    unconfirmed = await client.post(f"{PREFIX}/{value['id']}/prepare", headers=operator)
    assert unconfirmed.status_code == 409
    assert "Financial facts" in unconfirmed.json()["message"]
    engine = app.state.resources.engine

    def provider():
        return engine

    chains = PostgresV2SessionChainRepository(provider)
    chain = V2SessionChain(
        uuid.uuid4(),
        session_id,
        workstation.device_id,
        f"workstation:{workstation.device_id}",
        3,
        "b" * 64,
    )
    try:
        assert await chains.save_if_current(chain, None)
        prepared = await client.post(f"{PREFIX}/{value['id']}/prepare", headers=operator)
        prepared.raise_for_status()
        report["round_id"] = prepared.json()["round_id"]
        assert (
            await client.post(f"{PREFIX}/{value['id']}/reports", headers=agent, json=report)
        ).status_code == 200
        await client.post(f"{PREFIX}/{value['id']}/server-ready", headers=operator)
        assert await chains.save_if_current(
            dataclasses.replace(chain, last_sequence=4, last_payload_hash="c" * 64), 3
        )
        # "At least N" is insufficient: the server and local checkpoints must be identical.
        assert (
            await client.post(f"{PREFIX}/{value['id']}/authorize", headers=operator)
        ).status_code == 409
    finally:
        async with engine.begin() as transaction:
            await transaction.execute(
                delete(V2SessionChainModel).where(V2SessionChainModel.session_id == session_id)
            )


async def test_invalid_financial_checkpoint_is_a_boundary_error(http_updates):
    """Некорректный checkpoint возвращает контролируемую ошибку вместо HTTP 500."""
    client, operator, workstation, _, _, _ = http_updates
    _, agent = await enroll_agent(client, operator, workstation.device_id)
    created = await client.post(
        PREFIX,
        headers=operator,
        json={
            "operation_id": str(uuid.uuid4()),
            "release_id": "invalid-checkpoint",
            "executable_sha256": "a" * 64,
        },
    )
    value = created.json()
    response = await client.post(
        f"{PREFIX}/{value['id']}/reports",
        headers=agent,
        json={
            "round_id": value["round_id"],
            "sequence": 1,
            "instance_id": str(uuid.uuid4()),
            "active_session": False,
            "pending_facts": 0,
            "ready": True,
            "stage": "ready",
            "last_sequence": 3,
            "last_payload_hash": "b" * 64,
        },
    )
    assert response.status_code == 400


async def test_archived_pc_with_active_session_cannot_bypass_fleet_idle_check(http_updates):
    """Архивирование занятого ПК не позволяет обойти запрет обновления при активной игре."""
    from gameclub_backend.application.errors import ApplicationError
    from gameclub_backend.modules.sessions.infrastructure.postgres import (
        PostgresSessionRepository,
        SessionModel,
    )
    from test_session_admission_postgres import new_session

    client, operator, workstation, repository, app, _ = http_updates
    archived = Workstation(
        uuid.uuid4(),
        "archived-update-" + uuid.uuid4().hex,
        "Archived PC",
        archived_at=datetime.datetime.now(datetime.UTC),
    )
    await repository.save(archived)
    engine = app.state.resources.engine

    def provider():
        return engine

    sessions = PostgresSessionRepository(provider)
    active = new_session(archived.id)
    await sessions.save(active)
    try:
        _, agent = await enroll_agent(client, operator, workstation.device_id)
        created = await client.post(
            PREFIX,
            headers=operator,
            json={
                "operation_id": str(uuid.uuid4()),
                "release_id": "archive-safety",
                "executable_sha256": "a" * 64,
            },
        )
        value = created.json()
        assert set(value["targets"]) == {workstation.device_id}
        await client.post(
            f"{PREFIX}/{value['id']}/reports",
            headers=agent,
            json={
                "round_id": value["round_id"],
                "sequence": 1,
                "instance_id": str(uuid.uuid4()),
                "active_session": False,
                "pending_facts": 0,
                "ready": True,
                "stage": "ready",
            },
        )
        assert (
            await client.post(f"{PREFIX}/{value['id']}/prepare", headers=operator)
        ).status_code == 409
        await sessions.save(active.stop(datetime.datetime.now(datetime.UTC)))
        assert (
            await client.post(f"{PREFIX}/{value['id']}/prepare", headers=operator)
        ).status_code == 200
        with pytest.raises(ApplicationError, match="blocks new sessions"):
            await sessions.save(new_session(archived.id))
    finally:
        async with engine.begin() as transaction:
            await transaction.execute(
                delete(SessionModel).where(SessionModel.workstation_id == archived.id)
            )
            await transaction.execute(
                delete(WorkstationModel).where(WorkstationModel.id == archived.id)
            )
