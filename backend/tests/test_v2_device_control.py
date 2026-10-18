import dataclasses

import grpc
import pytest

from gameclub.v2 import device_control_service_pb2, device_control_service_pb2_grpc
from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.workstations.application.commands import WorkstationCommandService
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import (
    LockdownDeploymentMode,
    LockdownPolicy,
    WorkstationSessionMode,
)
from gameclub_backend.modules.workstations.infrastructure.commands_memory import (
    InMemoryCommandNotifier,
    InMemoryWorkstationCommandRepository,
)
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.presentation.grpc.services import DeviceControlGrpcService

pytestmark = pytest.mark.unit


async def test_v2_device_heartbeat_returns_configuration_without_session_state() -> None:
    """Проверяет, что V2 heartbeat выдаёт только конфигурацию места без server session."""
    repository = InMemoryWorkstationRepository()
    workstations = WorkstationService(repository)
    await workstations.register(
        "v2-device-01",
        "V2 PC",
        capabilities=("old-capability",),
    )
    saved = await repository.get_by_device_id("v2-device-01")
    assert saved is not None
    await repository.save(
        dataclasses.replace(
            saved,
            theme="neon",
            manager_password_verifier="argon2id$manager",
            lockdown_policy=LockdownPolicy(
                deployment_mode=LockdownDeploymentMode.SHELL_LAUNCHER,
                shell_enabled=False,
                hidden_drives=("D:",),
                version=7,
            ),
        )
    )
    token_service = JwtTokenService(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    access_token, _ = token_service.issue_access_token(
        Principal(
            subject_id="v2-device-01",
            subject_type=SubjectType.DEVICE,
            roles=frozenset({"device"}),
            permissions=frozenset({"workstations.connect"}),
        )
    )
    server = grpc.aio.server()
    device_control_service_pb2_grpc.add_DeviceControlServiceServicer_to_server(
        DeviceControlGrpcService(workstations, token_service), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    client = device_control_service_pb2_grpc.DeviceControlServiceStub(channel)

    try:
        response = await client.Heartbeat(
            device_control_service_pb2.DeviceHeartbeatRequest(
                device_id="v2-device-01",
                client_version="2.0.0",
                capabilities=("v2.local-ledger",),
            ),
            metadata=(("authorization", f"Bearer {access_token}"),),
        )
        assert response.device_id == "v2-device-01"
        assert response.workstation_name == "V2 PC"
        assert response.theme == "neon"
        assert response.manager_password_verifier == "argon2id$manager"
        assert response.lockdown_policy.deployment_mode == "shell_launcher"
        assert response.lockdown_policy.hidden_drives == ["D:"]
        assert response.lockdown_policy.version == 7
        assert "session_snapshot" not in response.DESCRIPTOR.fields_by_name
        assert "active_session_id" not in response.DESCRIPTOR.fields_by_name

        with pytest.raises(grpc.aio.AioRpcError) as error:
            await client.Heartbeat(
                device_control_service_pb2.DeviceHeartbeatRequest(
                    device_id="another-device",
                ),
                metadata=(("authorization", f"Bearer {access_token}"),),
            )
        assert error.value.code() is grpc.StatusCode.PERMISSION_DENIED
    finally:
        await channel.close()
        await server.stop(None)

    refreshed = await workstations.get_by_device_id("v2-device-01")
    assert refreshed.client_version == "2.0.0"
    assert refreshed.capabilities == ("v2.local-ledger",)


async def test_v2_device_enrollment_issues_only_device_scoped_token() -> None:
    """Проверяет выдачу enrollment JWT только с правом подключённого устройства."""
    repository = InMemoryWorkstationRepository()
    workstations = WorkstationService(repository)
    registered = await workstations.register(
        "v2-device-02",
        "V2 Enrollment PC",
        mac_address="00:11:22:33:44:55",
    )
    token_service = JwtTokenService(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    server = grpc.aio.server()
    device_control_service_pb2_grpc.add_DeviceControlServiceServicer_to_server(
        DeviceControlGrpcService(workstations, token_service), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    client = device_control_service_pb2_grpc.DeviceControlServiceStub(channel)

    try:
        health = await client.GetHealth(device_control_service_pb2.DeviceHealthRequest())
        assert (health.service, health.status, health.version) == (
            "gameclub-backend",
            "ok",
            "2.0.0",
        )
        pending = await client.Enroll(
            device_control_service_pb2.DeviceEnrollmentRequest(
                mac_addresses=("00:11:22:33:44:66",),
                installation_id="unknown-installation",
            )
        )
        assert pending.state == "pending"

        enrollment = await client.Enroll(
            device_control_service_pb2.DeviceEnrollmentRequest(
                mac_addresses=("00:11:22:33:44:55",),
                installation_id="v2-installation",
            )
        )
        assert enrollment.state == "approved"
        assert enrollment.device_id == "v2-device-02"
        assert enrollment.workstation_id == str(registered.id)
        assert enrollment.workstation_name == "V2 Enrollment PC"
        assert enrollment.access_token
        principal = token_service.validate_access_token(enrollment.access_token)
        assert principal.subject_type is SubjectType.DEVICE
        assert principal.subject_id == "v2-device-02"
        assert principal.permissions == frozenset({"workstations.connect"})
    finally:
        await channel.close()
        await server.stop(None)


async def test_v2_device_heartbeat_marks_disabled_workstation_as_conflict() -> None:
    """Проверяет controlled conflict для отключённого V2 места."""
    repository = InMemoryWorkstationRepository()
    workstations = WorkstationService(repository)
    workstation = await workstations.register("v2-device-disabled", "Disabled V2 PC")
    await workstations.disable(workstation.id, "operator disabled")
    token_service = JwtTokenService(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    access_token, _ = token_service.issue_access_token(
        Principal(
            subject_id="v2-device-disabled",
            subject_type=SubjectType.DEVICE,
            roles=frozenset({"device"}),
            permissions=frozenset({"workstations.connect"}),
        )
    )
    server = grpc.aio.server()
    device_control_service_pb2_grpc.add_DeviceControlServiceServicer_to_server(
        DeviceControlGrpcService(workstations, token_service), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    client = device_control_service_pb2_grpc.DeviceControlServiceStub(channel)

    try:
        with pytest.raises(grpc.aio.AioRpcError) as error:
            await client.Heartbeat(
                device_control_service_pb2.DeviceHeartbeatRequest(
                    device_id="v2-device-disabled",
                ),
                metadata=(("authorization", f"Bearer {access_token}"),),
            )
        assert error.value.code() is grpc.StatusCode.ALREADY_EXISTS
    finally:
        await channel.close()
        await server.stop(None)


async def test_v2_command_stream_delivers_only_v2_commands_and_acknowledges_them() -> None:
    """Проверяет доставку команд устройству и безопасный ack."""
    workstation_repository = InMemoryWorkstationRepository()
    workstations = WorkstationService(workstation_repository)
    workstation = await workstations.register(
        "v2-command-device",
        "Device commands PC",
        session_mode=WorkstationSessionMode.LOCAL_LEDGER,
    )
    command_service = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstation_repository,
        InMemoryCommandNotifier(),
    )
    v2_command = await command_service.dispatch(
        workstation.id,
        "display.lock",
        '{"reason":"operator"}',
        "v2-lock-command",
    )
    token_service = JwtTokenService(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    access_token, _ = token_service.issue_access_token(
        Principal(
            subject_id="v2-command-device",
            subject_type=SubjectType.DEVICE,
            roles=frozenset({"device"}),
            permissions=frozenset({"workstations.connect"}),
        )
    )
    server = grpc.aio.server()
    device_control_service_pb2_grpc.add_DeviceControlServiceServicer_to_server(
        DeviceControlGrpcService(workstations, token_service, command_service), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    client = device_control_service_pb2_grpc.DeviceControlServiceStub(channel)

    try:
        stream = client.WatchCommands(
            device_control_service_pb2.DeviceCommandWatchRequest(
                device_id="v2-command-device"
            ),
            metadata=(("authorization", f"Bearer {access_token}"),),
        )
        delivered = await stream.read()
        assert delivered.id == str(v2_command.id)
        assert delivered.command_type == "display.lock"
        assert delivered.payload_json == '{"reason":"operator"}'
        assert "workstation_id" not in delivered.DESCRIPTOR.fields_by_name

        acknowledged = await client.AcknowledgeCommand(
            device_control_service_pb2.DeviceCommandAcknowledgementRequest(
                command_id=delivered.id,
                device_id="v2-command-device",
                success=True,
                message="locked",
            ),
            metadata=(("authorization", f"Bearer {access_token}"),),
        )
        assert acknowledged.status == "acknowledged"
        assert acknowledged.acknowledgement_message == "locked"
        pending = await command_service.pending_for_device("v2-command-device")
        assert pending == []
        stream.cancel()
    finally:
        await channel.close()
        await server.stop(None)
