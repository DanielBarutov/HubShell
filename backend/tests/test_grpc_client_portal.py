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
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.infrastructure.memory import (
    InMemoryEntitlementRepository,
)
from gameclub_backend.modules.reservations.domain import Reservation, ReservationStatus
from gameclub_backend.modules.reservations.infrastructure.memory import (
    InMemoryReservationRepository,
)
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
    reservation_repository = InMemoryReservationRepository()
    sales = ProductSaleService(
        InMemoryProductSaleRepository(),
        products=catalog,
        clients=client_service,
    )
    charge_repository = InMemoryChargeRepository()
    entitlement_service = EntitlementService(
        InMemoryEntitlementRepository(),
        tariffs=catalog,
        clients=client_service,
    )
    portal = ClientPortalService(
        clients=client_service,
        sessions=session_repository,
        charges=ChargeHistoryReader(charge_repository),
        sales=sales,
        tariffs=catalog,
        entitlements=entitlement_service,
        reservations=reservation_repository,
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
                password="1234",
                device_id="device-01",
            ),
            metadata=(("authorization", f"Bearer {device_token}"),),
        )
        await client_service.top_up(
            uuid.UUID(registered.snapshot.client.id),
            1_000,
            0,
            "Package test balance",
            "operator",
            "grpc-portal-top-up",
        )
        purchased = await client.PurchaseEntitlement(
            clients_pb2.PurchaseEntitlementRequest(
                tariff_id=str(tariff.id),
                device_id="device-01",
                idempotency_key="grpc-portal-package",
            ),
            metadata=(("authorization", f"Bearer {registered.access_token}"),),
        )
        reservation_start = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)
        await reservation_repository.save(
            Reservation(
                id=uuid.uuid4(),
                workstation_ids=(uuid.UUID("00000000-0000-0000-0000-000000000009"),),
                client_id=uuid.UUID(registered.snapshot.client.id),
                guest_name=None,
                start_at=reservation_start,
                end_at=reservation_start + datetime.timedelta(hours=1),
                status=ReservationStatus.CONFIRMED,
                notes=None,
                tariff_id=tariff.id,
                created_by="operator",
                created_at=datetime.datetime.now(datetime.UTC),
            )
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
        activated = await client.ActivateEntitlement(
            clients_pb2.ActivateEntitlementRequest(
                entitlement_id=snapshot.entitlements[0].id,
                device_id="device-01",
            ),
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
    assert snapshot.entitlements[0].status == "queued"
    assert purchased.entitlements[0].status == "queued"
    assert len(snapshot.reservations) == 1
    assert snapshot.reservations[0].workstation_ids == ["00000000-0000-0000-0000-000000000009"]
    assert snapshot.tariffs[0].name == "Ночной тариф"
    assert activated.entitlements[0].status == "active"
    assert error.value.code() is grpc.StatusCode.PERMISSION_DENIED
