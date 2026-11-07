"""Explicit recovery to a corrected release preserves the barrier and previous attempt."""

import datetime
import uuid

import pytest
from sqlalchemy import delete

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.modules.client_updates.domain import (
    Deployment,
    DeploymentPhase,
    DeviceUpdateReport,
)
from gameclub_backend.modules.client_updates.infrastructure.postgres import (
    ClientReleasePolicyModel,
    PostgresDeploymentRepository,
)
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionAdmission,
    PostgresSessionRepository,
)
from test_client_release_store import signed_release
from test_client_update_http_postgres import enroll_agent
from test_client_update_http_postgres import http_updates as http_updates
from test_session_admission_postgres import new_session

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.api]
PREFIX = "/api/v1/client-updates"


@pytest.fixture
async def failed_update(http_updates):
    client, operator, workstation, _, app, root = http_updates

    def provider():
        return app.state.resources.engine

    repository = PostgresDeploymentRepository(provider)
    metadata, _ = signed_release(root, "corrected-release")
    deployment = Deployment(
        uuid.uuid4(),
        uuid.uuid4(),
        "broken-release",
        "b" * 64,
        {workstation.device_id: workstation.id},
        app.state.jwt_service.validate_access_token(
            operator["Authorization"].removeprefix("Bearer ")
        ).subject_id,
        datetime.datetime.now(datetime.UTC),
        phase=DeploymentPhase.FAILED,
        independent=True,
    )
    deployment.reports[workstation.device_id] = DeviceUpdateReport(
        workstation.device_id,
        deployment.round_id,
        5,
        uuid.uuid4(),
        datetime.datetime.now(datetime.UTC),
        False,
        0,
        False,
        stage="rolled_back",
        error_code="startup_failed",
        running_release_id="old-release",
    )
    await repository.create(deployment)
    await PostgresSessionAdmission(provider).block(deployment.id, (workstation.id,))
    policy_operation = uuid.uuid4()
    published = await client.post(
        f"{PREFIX}/policy",
        headers=operator,
        json={
            "operation_id": str(policy_operation),
            "release_id": "corrected-release",
        },
    )
    assert published.status_code == 200, published.text
    try:
        yield repository, deployment, metadata, provider
    finally:
        async with provider().begin() as transaction:
            await transaction.execute(
                delete(ClientReleasePolicyModel).where(
                    ClientReleasePolicyModel.operation_id == policy_operation
                )
            )


async def test_retry_current_is_idempotent_preserves_history_and_keeps_pc_blocked(
    http_updates, failed_update
):
    """Явный повтор меняет только failed ПК, сохраняет прежнюю попытку и не открывает вход."""
    client, operator, workstation, _, app, _ = http_updates
    repository, deployment, metadata, provider = failed_update
    _, updater = await enroll_agent(client, operator, workstation.device_id)
    operation = uuid.uuid4()
    endpoint = f"{PREFIX}/{deployment.id}/retry-current"
    assert (
        await client.post(endpoint, headers=updater, json={"operation_id": str(operation)})
    ).status_code == 403
    first = await client.post(endpoint, headers=operator, json={"operation_id": str(operation)})
    assert first.status_code == 200, first.text
    value = first.json()
    assert value["id"] == str(deployment.id)
    assert value["release_id"] == "corrected-release"
    assert value["executable_sha256"] == metadata["executableSha256"]
    assert value["phase"] == "preparing"
    assert value["round_id"] != str(deployment.round_id)
    previous = value["previous_attempts"][0]
    assert previous["release_id"] == "broken-release"
    assert previous["reports"][workstation.device_id]["error_code"] == "startup_failed"
    assert previous["next_release_id"] == "corrected-release"
    repeated = await client.post(endpoint, headers=operator, json={"operation_id": str(operation)})
    assert repeated.status_code == 200
    assert repeated.json() == value
    from gameclub_backend.modules.auth.domain import Principal, SubjectType

    other_token, _ = app.state.jwt_service.issue_access_token(
        Principal(
            "another-operator",
            SubjectType.OPERATOR,
            frozenset(),
            frozenset({"workstations.manage"}),
        )
    )
    other = await client.post(
        endpoint,
        headers={"Authorization": "Bearer " + other_token},
        json={"operation_id": str(operation)},
    )
    assert other.status_code == 409
    assert (
        await client.post(endpoint, headers=operator, json={"operation_id": str(uuid.uuid4())})
    ).status_code == 409
    with pytest.raises(ApplicationError, match="blocks new sessions"):
        await PostgresSessionRepository(provider).save(new_session(workstation.id))
    creation = await client.post(
        PREFIX,
        headers=operator,
        json={
            "operation_id": str(deployment.operation_id),
            "release_id": "broken-release",
            "executable_sha256": "b" * 64,
            "device_id": workstation.device_id,
        },
    )
    assert creation.status_code == 200, creation.text
    assert creation.json()["id"] == value["id"]
    assert len((await repository.get(deployment.id)).previous_attempts) == 1


async def test_invalid_corrected_package_retains_failed_snapshot_and_barrier(
    http_updates, failed_update
):
    """Повреждённый исправленный пакет не стирает ошибку и не меняет заблокированный раунд."""
    client, operator, workstation, _, _, root = http_updates
    repository, deployment, _, provider = failed_update
    (root / "corrected-release/HubShell.zip").write_bytes(b"corrupt")
    response = await client.post(
        f"{PREFIX}/{deployment.id}/retry-current",
        headers=operator,
        json={"operation_id": str(uuid.uuid4())},
    )
    assert response.status_code == 409, response.text
    current = await repository.get(deployment.id)
    assert current.release_id == deployment.release_id
    assert current.round_id == deployment.round_id
    assert current.phase is DeploymentPhase.FAILED
    assert current.previous_attempts == []
    with pytest.raises(ApplicationError, match="blocks new sessions"):
        await PostgresSessionRepository(provider).save(new_session(workstation.id))
