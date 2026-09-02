import dataclasses
import datetime

import pytest

from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.sessions.presentation.http import SessionSnapshotResponse
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationStatus
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.modules.workstations.presentation.http import WorkstationResponse
from gameclub_backend.presentation.grpc.services import (
    to_proto,
    to_session_snapshot_proto,
)


@pytest.mark.asyncio
async def test_http_grpc_and_device_heartbeat_share_the_same_snapshot_fixture() -> None:
    workstations_repository = InMemoryWorkstationRepository()
    workstations = WorkstationService(workstations_repository)
    workstation = await workstations.register(
        "snapshot-device",
        "Snapshot PC",
        group_id="vip",
        capabilities=("sessions.v1", "commands.v1"),
    )
    clients_repository = InMemoryClientRepository()
    client = await ClientService(clients_repository).create("SnapshotClient")
    sessions_repository = InMemorySessionRepository()
    sessions = SessionService(
        sessions_repository,
        workstations=workstations_repository,
        clients=clients_repository,
    )
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="snapshot-session",
    )
    server_time = datetime.datetime(2026, 9, 2, 12, 30, tzinfo=datetime.UTC)
    snapshot = await sessions.snapshot(session.id, now=server_time)

    http_snapshot = SessionSnapshotResponse.from_domain(snapshot).model_dump(mode="json")
    grpc_snapshot = to_session_snapshot_proto(snapshot)
    device_heartbeat = to_proto(workstation, session_snapshot=snapshot)

    assert http_snapshot["schema_version"] == grpc_snapshot.schema_version == 1
    assert http_snapshot["server_time"] == server_time.isoformat()
    assert http_snapshot["session"]["id"] == grpc_snapshot.session.id == str(session.id)
    assert http_snapshot["workstation_id"] == grpc_snapshot.workstation_id == str(workstation.id)
    assert http_snapshot["device_id"] == grpc_snapshot.device_id == workstation.device_id
    assert http_snapshot["allowed_actions"] == list(grpc_snapshot.allowed_actions) == ["stop"]
    assert device_heartbeat.active_session_id == str(session.id)
    assert device_heartbeat.active_session_status == session.status.value
    assert device_heartbeat.session_snapshot.schema_version == grpc_snapshot.schema_version
    assert device_heartbeat.session_snapshot.session.id == grpc_snapshot.session.id
    assert device_heartbeat.session_server_time == grpc_snapshot.server_time


@pytest.mark.asyncio
async def test_stale_workstation_does_not_become_available_when_snapshot_is_present() -> None:
    workstations_repository = InMemoryWorkstationRepository()
    workstations = WorkstationService(workstations_repository)
    workstation = await workstations.register("stale-device", "Stale PC", group_id="main")
    clients_repository = InMemoryClientRepository()
    client = await ClientService(clients_repository).create("StaleClient")
    sessions_repository = InMemorySessionRepository()
    sessions = SessionService(
        sessions_repository,
        workstations=workstations_repository,
        clients=clients_repository,
    )
    session = await sessions.start(
        workstation.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="stale-session",
    )
    snapshot = await sessions.snapshot(
        session.id,
        now=datetime.datetime(2026, 9, 2, 12, 30, tzinfo=datetime.UTC),
    )
    stale = dataclasses.replace(
        workstation,
        status=WorkstationStatus.STALE,
        last_seen_at=datetime.datetime(2026, 9, 2, 12, 28, tzinfo=datetime.UTC),
    )

    response = WorkstationResponse.from_domain(stale, snapshot)
    device = to_proto(stale, session_snapshot=snapshot)

    assert response.status is WorkstationStatus.STALE
    assert response.session_snapshot is not None
    assert response.active_session_id == session.id
    assert device.status != 2  # WORKSTATION_STATUS_ONLINE
    assert device.session_snapshot.session.id == str(session.id)
