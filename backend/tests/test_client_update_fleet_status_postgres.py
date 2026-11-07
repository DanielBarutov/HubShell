"""Whole-fleet operator projection over independent persisted device jobs."""

import dataclasses
import datetime
import uuid

import pytest
from sqlalchemy import delete

from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.domain import (
    ClientReleasePolicy,
    Deployment,
    DeviceUpdateReport,
)
from gameclub_backend.modules.client_updates.infrastructure.postgres import (
    ClientReleasePolicyModel,
    PostgresDeploymentRepository,
)
from gameclub_backend.modules.workstations.domain import WorkstationStatus
from test_client_update_agent_e2e import second_update_pc as second_update_pc
from test_client_update_http_postgres import http_updates as http_updates

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.api]
PREFIX = "/api/v1/client-updates"


@pytest.fixture
async def policy(http_updates):
    _, _, _, _, app, _ = http_updates

    def provider():
        return app.state.resources.engine

    repository = PostgresDeploymentRepository(provider)
    policy = ClientReleasePolicy(
        uuid.uuid4(),
        "fleet-v1",
        "a" * 64,
        ("fleet-v1",),
        "operator",
        datetime.datetime.now(datetime.UTC),
    )
    await repository.publish_policy(policy)
    try:
        yield repository, policy
    finally:
        async with provider().begin() as transaction:
            await transaction.execute(
                delete(ClientReleasePolicyModel).where(
                    ClientReleasePolicyModel.operation_id == policy.operation_id
                )
            )


def completed_job(workstation, policy):
    now = datetime.datetime.now(datetime.UTC)
    deployment = Deployment(
        uuid.uuid4(),
        uuid.uuid4(),
        policy.release_id,
        policy.executable_sha256,
        {workstation.device_id: workstation.id},
        "operator",
        now,
        independent=True,
    )
    instance = uuid.uuid4()

    def report(sequence=1, stage="ready", installed=None):
        return DeviceUpdateReport(
            workstation.device_id,
            deployment.round_id,
            sequence,
            instance,
            now,
            False,
            0,
            True,
            stage=stage,
            installed_sha256=installed,
            running_release_id=policy.release_id,
        )

    deployment.report(report())
    deployment.begin_preparation(now)
    deployment.report(report())
    deployment.server_ready = True
    deployment.authorize(now)
    deployment.report(report(2, "installed", policy.executable_sha256))
    deployment.confirm_gui(workstation.device_id, policy.release_id)
    deployment.finish()
    return deployment


async def test_status_includes_offline_pc_and_revokes_stale_success_after_old_gui_returns(
    http_updates, second_update_pc, policy
):
    """Отчёт сохраняет выключенный ПК и перестаёт считать успешным ПК с вернувшимся старым EXE."""
    client, operator, first, _, app, _ = http_updates
    repository, release = policy
    await repository.create(completed_job(first, release))
    response = await client.get(f"{PREFIX}/current", headers=operator)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    fleet = response.json()["deployment"]
    assert fleet["mode"] == "independent"
    assert (fleet["confirmed"], fleet["total"], fleet["phase"]) == (1, 2, "polling")
    rows = {item["device_id"]: item for item in fleet["devices"]}
    assert rows[first.device_id]["status"] == "confirmed"
    assert rows[second_update_pc.device_id]["status"] == "unreachable"
    assert rows[second_update_pc.device_id]["deployment_id"] is None
    token, _ = app.state.jwt_service.issue_access_token(
        Principal(
            first.device_id,
            SubjectType.DEVICE,
            frozenset(),
            frozenset({"workstations.connect"}),
            installation_id=first.installation_id,
        )
    )
    observed = await client.get(
        f"{PREFIX}/gui/current",
        params={"release_id": "old-exe"},
        headers={"Authorization": "Bearer " + token},
    )
    assert observed.status_code == 200, observed.text
    fleet = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
    assert fleet["confirmed"] == 0
    row = next(item for item in fleet["devices"] if item["device_id"] == first.device_id)
    assert row["running_release_id"] == "old-exe"
    assert row["status"] == "awaiting_agent"


async def test_status_uses_latest_job_and_keeps_other_device_independent(
    http_updates, second_update_pc, policy
):
    """Последняя ошибка одного ПК не маскируется старым успехом и не меняет другой ПК."""
    client, operator, first, _, _, _ = http_updates
    repository, release = policy
    completed = completed_job(first, release)
    await repository.create(completed)
    old_second = completed_job(second_update_pc, release)
    old_second.created_at -= datetime.timedelta(minutes=1)
    await repository.create(old_second)
    pending = Deployment(
        uuid.uuid4(),
        uuid.uuid4(),
        "older-assigned-release",
        "b" * 64,
        {second_update_pc.device_id: second_update_pc.id},
        "operator",
        datetime.datetime.now(datetime.UTC),
        independent=True,
    )
    await repository.create(pending)
    async with repository.change(pending.id) as changed:
        now = datetime.datetime.now(datetime.UTC)
        instance = uuid.uuid4()
        changed.report(
            DeviceUpdateReport(
                second_update_pc.device_id, changed.round_id, 1, instance, now, False, 0, True
            )
        )
        changed.begin_preparation(now)
        changed.report(
            DeviceUpdateReport(
                second_update_pc.device_id, changed.round_id, 1, instance, now, False, 0, True
            )
        )
        changed.server_ready = True
        changed.authorize(now)
        changed.report(
            DeviceUpdateReport(
                second_update_pc.device_id,
                changed.round_id,
                2,
                instance,
                now,
                False,
                0,
                False,
                stage="rolled_back",
                error_code="startup_failed",
            )
        )
    fleet = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
    assert (fleet["confirmed"], fleet["total"], fleet["phase"]) == (1, 2, "failed")
    rows = {item["device_id"]: item for item in fleet["devices"]}
    assert rows[first.device_id]["status"] == "confirmed"
    assert rows[second_update_pc.device_id]["assigned_release_id"] == "older-assigned-release"
    assert rows[second_update_pc.device_id]["status"] == "rolled_back"
    assert rows[second_update_pc.device_id]["error_code"] == "startup_failed"


async def test_empty_or_disabled_park_is_not_reported_as_updated(http_updates, policy):
    """Отключённый ПК остаётся в списке, пустой парк не получает ложный успех 0/0."""
    client, operator, first, workstations, _, _ = http_updates
    await workstations.save(dataclasses.replace(first, status=WorkstationStatus.DISABLED))
    fleet = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
    assert fleet["total"] == 1
    assert fleet["devices"][0]["status"] == "disabled"
    await workstations.save(
        dataclasses.replace(first, archived_at=datetime.datetime.now(datetime.UTC))
    )
    fleet = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
    assert (fleet["confirmed"], fleet["total"], fleet["phase"]) == (0, 0, "polling")
    assert fleet["devices"] == []


async def test_active_legacy_maintenance_is_not_hidden_by_independent_policy(http_updates, policy):
    """Незавершённое общее обслуживание сохраняет свой статус и предупреждение общего барьера."""
    client, operator, first, _, _, _ = http_updates
    repository, release = policy
    deployment = Deployment(
        uuid.uuid4(),
        uuid.uuid4(),
        release.release_id,
        release.executable_sha256,
        {first.device_id: first.id},
        "operator",
        datetime.datetime.now(datetime.UTC),
    )
    await repository.create(deployment)
    fleet = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
    assert fleet["id"] == str(deployment.id)
    assert fleet.get("mode") != "independent"


async def test_new_installation_does_not_inherit_old_confirmation(http_updates, policy):
    """Изменённая установка не наследует подтверждение и показ версии прежнего GUI."""
    client, operator, first, workstations, _, _ = http_updates
    repository, release = policy
    await repository.create(completed_job(first, release))
    await repository.observe_release(
        first.device_id, first.id, first.installation_id, release.release_id
    )
    await workstations.save(dataclasses.replace(first, installation_id=uuid.uuid4().hex))
    fleet = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
    assert fleet["confirmed"] == 0
    assert fleet["devices"][0]["status"] == "unreachable"
    assert fleet["devices"][0]["running_release_id"] is None
