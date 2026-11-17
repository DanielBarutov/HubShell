import uuid

import grpc
import pytest

from gameclub.v2 import offline_session_service_pb2, offline_session_service_pb2_grpc
from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.reservations.domain import EntryDecision
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.v2_transfer import V2TransferTargetService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationSessionMode
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.presentation.grpc.services import OfflineSessionGrpcService


async def test_transfer_targets_are_filtered_and_visible_only_from_source() -> None:
    places = InMemoryWorkstationRepository()
    workstations = WorkstationService(places)
    mode = WorkstationSessionMode.LOCAL_LEDGER

    async def register(name: str, online: bool = True):
        workstation = await workstations.register(name, name, session_mode=mode)
        if online:
            await workstations.heartbeat(name)
        return workstation

    source = await register("source")
    free = await register("free")
    held = await register("held")
    blocked = await register("blocked")
    busy = await register("busy")
    await register("offline", online=False)

    class Holds:
        async def list_reserved_targets(self) -> set[uuid.UUID]:
            return {held.id}

    class Booking:
        async def check_entry(self, workstation_id, *, client_id=None, guest_id=None):
            return EntryDecision(workstation_id != blocked.id, "booking")

    clients = InMemoryClientRepository()
    player = await ClientService(clients).create("Player")
    other = await ClientService(clients).create("Other")
    sessions = SessionService(InMemorySessionRepository(), workstations=places, clients=clients)
    session = await sessions.start(source.id, "test", client_id=player.id, source="local_ledger")
    await sessions.start(busy.id, "test", client_id=other.id, source="local_ledger")
    targets = V2TransferTargetService(sessions, workstations, Booking(), Holds())
    tokens = JwtTokenService(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))

    def metadata(device_id: str):
        token, _ = tokens.issue_access_token(
            Principal(
                device_id,
                SubjectType.DEVICE,
                frozenset({"device"}),
                frozenset({"workstations.connect"}),
            )
        )
        return (("authorization", f"Bearer {token}"),)

    server = grpc.aio.server()
    offline_session_service_pb2_grpc.add_OfflineSessionServiceServicer_to_server(
        OfflineSessionGrpcService(None, tokens, transfer_targets=targets), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = offline_session_service_pb2_grpc.OfflineSessionServiceStub(channel)
            request = offline_session_service_pb2.ListTransferTargetsRequest(
                device_id="source", session_id=str(session.id)
            )
            response = await stub.ListTransferTargets(request, metadata=metadata("source"))
            assert [item.workstation_id for item in response.targets] == [str(free.id)]

            with pytest.raises(grpc.aio.AioRpcError) as mismatch:
                await stub.ListTransferTargets(request, metadata=metadata("free"))
            assert mismatch.value.code() is grpc.StatusCode.PERMISSION_DENIED

            request.device_id = "free"
            with pytest.raises(grpc.aio.AioRpcError) as wrong_owner:
                await stub.ListTransferTargets(request, metadata=metadata("free"))
            assert wrong_owner.value.code() is grpc.StatusCode.PERMISSION_DENIED

            request.device_id = "source"
            request.session_id = "invalid"
            with pytest.raises(grpc.aio.AioRpcError) as malformed:
                await stub.ListTransferTargets(request, metadata=metadata("source"))
            assert malformed.value.code() is grpc.StatusCode.INVALID_ARGUMENT
    finally:
        await server.stop(None)
