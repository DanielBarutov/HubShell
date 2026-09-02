import datetime
import uuid

import grpc
import pytest

from gameclub.v1 import clients_pb2, clients_pb2_grpc
from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.billing.infrastructure.memory import InMemoryChargeRepository
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.clients.application.portal import ClientPortalService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.presentation.grpc.services import ClientPortalGrpcService


class ChargeHistoryReader:
    def __init__(self, repository: InMemoryChargeRepository) -> None:
        self._repository = repository

    async def list_charges_for_client(self, client_id, limit):
        return await self._repository.list_for_client(client_id, limit)


@pytest.mark.asyncio
async def test_client_portal_grpc_scopes_snapshot_to_enrolled_device() -> None:
    settings = Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    token_service = JwtTokenService(settings)
    client_service = ClientService(InMemoryClientRepository())
    catalog = CatalogService(InMemoryCatalogRepository())
    tariff = await catalog.create_tariff(
        "Ночной тариф",
        None,
        60,
        1_000,
        datetime.datetime.now(datetime.UTC),
        None,
    )
    session_repository = InMemorySessionRepository()
    sales = ProductSaleService(
        InMemoryProductSaleRepository(),
        products=catalog,
        clients=client_service,
    )
    charge_repository = InMemoryChargeRepository()
    portal = ClientPortalService(
        clients=client_service,
        sessions=session_repository,
        charges=ChargeHistoryReader(charge_repository),
        sales=sales,
        tariffs=catalog,
    )

    server = grpc.aio.server()
    clients_pb2_grpc.add_ClientPortalServiceServicer_to_server(
        ClientPortalGrpcService(portal, token_service),
        server,
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    client = clients_pb2_grpc.ClientPortalServiceStub(channel)
    device_token, _ = token_service.issue_access_token(
        Principal(
            subject_id="device-01",
            subject_type=SubjectType.DEVICE,
            roles=frozenset({"device"}),
            permissions=frozenset({"workstations.connect"}),
        )
    )

    try:
        registered = await client.Register(
            clients_pb2.RegisterPortalRequest(
                nickname="NightFox",
                phone="79991234567",
                pin="1234",
                device_id="device-01",
            ),
            metadata=(("authorization", f"Bearer {device_token}"),),
        )
        await session_repository.save(
            Session(
                id=uuid.uuid4(),
                workstation_id=uuid.uuid4(),
                client_id=uuid.UUID(registered.snapshot.client.id),
                guest_name=None,
                status=SessionStatus.COMPLETED,
                started_at=datetime.datetime.now(datetime.UTC),
                ended_at=datetime.datetime.now(datetime.UTC),
                source="test",
                created_by="test",
                created_at=datetime.datetime.now(datetime.UTC),
                tariff_id=tariff.id,
            )
        )
        snapshot = await client.Get(
            clients_pb2.GetPortalRequest(device_id="device-01"),
            metadata=(("authorization", f"Bearer {registered.access_token}"),),
        )

        with pytest.raises(grpc.aio.AioRpcError) as error:
            await client.Get(
                clients_pb2.GetPortalRequest(device_id="other-device"),
                metadata=(("authorization", f"Bearer {registered.access_token}"),),
            )
    finally:
        await channel.close()
        await server.stop(0)

    assert registered.snapshot.client.nickname == "NightFox"
    assert snapshot.client.id == registered.snapshot.client.id
    assert snapshot.available_time_minutes == 0
    assert snapshot.sessions[0].tariff_name == "Ночной тариф"
    assert error.value.code() is grpc.StatusCode.PERMISSION_DENIED
