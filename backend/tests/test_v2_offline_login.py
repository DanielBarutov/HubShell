import datetime
import uuid

import grpc
import pytest

from gameclub.v2 import offline_session_service_pb2, offline_session_service_pb2_grpc
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.billing.infrastructure.memory import InMemoryChargeRepository
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.client_groups.application.service import ClientGroupService
from gameclub_backend.modules.client_groups.infrastructure.memory import (
    InMemoryClientGroupRepository,
)
from gameclub_backend.modules.clients.application.portal import ClientPortalService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.domain import Client
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.infrastructure.memory import (
    InMemoryEntitlementRepository,
)
from gameclub_backend.modules.eventing_v2.application.login import V2OfflineLoginService
from gameclub_backend.modules.eventing_v2.application.snapshot_issue import (
    V2SignedSnapshotIssue,
    V2SnapshotIssueResult,
    V2SnapshotIssueService,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_ed25519 import (
    V2Ed25519SnapshotSigner,
)
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import Session
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationSessionMode
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.presentation.grpc.services import OfflineSessionGrpcService

pytestmark = pytest.mark.unit


class SnapshotIssueMemoryRepository:
    def __init__(self, sessions: InMemorySessionRepository) -> None:
        self._items = {}
        self._sessions = sessions

    async def issue(self, value: V2SignedSnapshotIssue) -> V2SnapshotIssueResult:
        existing = self._items.get(value.lease.session_id)
        if existing is not None:
            return V2SnapshotIssueResult(
                signed_snapshot=existing,
                login_event_id=value.lease.snapshot_id,
                is_duplicate=True,
            )
        self._items[value.lease.session_id] = value.signed_snapshot
        return V2SnapshotIssueResult(
            signed_snapshot=value.signed_snapshot,
            login_event_id=value.lease.snapshot_id,
            is_duplicate=False,
        )

    async def issue_with_new_session(
        self,
        value: V2SignedSnapshotIssue,
        session: Session,
    ) -> V2SnapshotIssueResult:
        await self._sessions.save(session)
        return await self.issue(value)


async def build_service(
    mode: WorkstationSessionMode,
) -> tuple[V2OfflineLoginService, SessionService, ClientPortalService, ClientService, Client]:
    client_groups = InMemoryClientGroupRepository()
    clients = ClientService(InMemoryClientRepository(), groups=client_groups)
    catalog = CatalogService(InMemoryCatalogRepository())
    workstations = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstations)
    await workstation_service.register(
        "v2-device-01",
        "V2 PC",
        session_mode=mode,
    )
    session_repository = InMemorySessionRepository()
    await catalog.create_tariff(
        "V2 час",
        None,
        60,
        500,
        datetime.datetime.now(datetime.UTC),
        None,
    )
    sessions = SessionService(
        session_repository,
        workstations=workstations,
        clients=clients,
    )
    entitlements = EntitlementService(
        InMemoryEntitlementRepository(),
        tariffs=catalog,
        clients=clients,
    )
    portal = ClientPortalService(
        clients=clients,
        sessions=sessions,
        charges=InMemoryChargeRepository(),
        sales=ProductSaleService(
            InMemoryProductSaleRepository(),
            products=catalog,
            clients=clients,
        ),
        tariffs=catalog,
        entitlements=entitlements,
        workstations=workstations,
    )
    client = await portal.register("V2 Player", "79991230001", "safe-password")
    service = V2OfflineLoginService(
        workstations=workstation_service,
        client_portal=portal,
        sessions=sessions,
        client_groups=ClientGroupService(client_groups),
        snapshot_issues=V2SnapshotIssueService(SnapshotIssueMemoryRepository(session_repository)),
        signing_key_id="test-v2-key",
        signer=V2Ed25519SnapshotSigner("nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A="),
        policy_version="v2-local-ledger-1",
        token_service=JwtTokenService(
            Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
        ),
    )
    return service, sessions, portal, clients, client


async def test_v2_login_creates_only_v2_session_and_reuses_signed_snapshot_on_retry() -> None:
    service, sessions, _, _, _ = await build_service(WorkstationSessionMode.V2_LOCAL_LEDGER)

    first = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="v2-login-001",
    )
    repeated = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="v2-login-001",
    )

    active = await sessions.list(active_only=True)
    assert len(active) == 1
    assert active[0].source == "v2_local_ledger"
    assert active[0].login_grant_minutes == 5
    assert first.payload.session_id == str(active[0].id)
    assert first.SerializeToString() == repeated.SerializeToString()


async def test_v2_login_rejects_a_workstation_that_remains_in_v1_mode() -> None:
    service, sessions, _, _, _ = await build_service(WorkstationSessionMode.V1_SERVER_OWNED)

    with pytest.raises(ApplicationError) as error:
        await service.login(
            device_id="v2-device-01",
            identifier="V2 Player",
            password="safe-password",
            idempotency_key="v2-login-001",
        )

    assert error.value.code is ErrorCode.CONFLICT
    assert await sessions.list(active_only=True) == []


async def test_v2_password_reset_challenge_completes_before_session_creation() -> None:
    service, sessions, portal, clients, client = await build_service(
        WorkstationSessionMode.V2_LOCAL_LEDGER
    )
    await clients.reset_password(client.id)

    challenge = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="",
        idempotency_key="v2-reset-login-001",
    )

    assert challenge.password_reset_required is True
    assert challenge.password_reset_token
    assert not challenge.HasField("payload")
    assert await sessions.list(active_only=True) == []

    await service.change_password(
        client_id=client.id,
        device_id="v2-device-01",
        new_password="new-safe-password",
    )
    snapshot = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="new-safe-password",
        idempotency_key="v2-reset-login-002",
    )

    assert snapshot.payload.device_id == "v2-device-01"
    assert (await portal.authenticate("V2 Player", "new-safe-password")).id == client.id
    assert len(await sessions.list(active_only=True)) == 1


async def test_v2_register_creates_profile_and_only_v2_session() -> None:
    service, sessions, _, _, _ = await build_service(WorkstationSessionMode.V2_LOCAL_LEDGER)

    snapshot = await service.register(
        device_id="v2-device-01",
        nickname="V2 New Player",
        phone="79991230002",
        password="safe-password",
        idempotency_key="v2-register-001",
    )

    active = await sessions.list(active_only=True)
    assert len(active) == 1
    assert active[0].source == "v2_local_ledger"
    assert snapshot.payload.client_id == str(active[0].client_id)


async def test_v2_grpc_login_requires_the_same_device_identity() -> None:
    service, sessions, _, clients, registered_client = await build_service(
        WorkstationSessionMode.V2_LOCAL_LEDGER
    )
    token_service = JwtTokenService(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    device_token, _ = token_service.issue_access_token(
        Principal(
            subject_id="v2-device-01",
            subject_type=SubjectType.DEVICE,
            roles=frozenset({"device"}),
            permissions=frozenset({"workstations.connect"}),
        )
    )
    server = grpc.aio.server()
    offline_session_service_pb2_grpc.add_OfflineSessionServiceServicer_to_server(
        OfflineSessionGrpcService(service, token_service),
        server,
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    client = offline_session_service_pb2_grpc.OfflineSessionServiceStub(channel)

    try:
        snapshot = await client.Login(
            offline_session_service_pb2.LoginOfflineSessionRequest(
                device_id="v2-device-01",
                identifier="V2 Player",
                password="safe-password",
                idempotency_key="v2-login-grpc-001",
            ),
            metadata=(("authorization", f"Bearer {device_token}"),),
        )
        assert snapshot.payload.device_id == "v2-device-01"
        portal_snapshot = await client.GetPortalSnapshot(
            offline_session_service_pb2.GetOfflinePortalSnapshotRequest(
                device_id="v2-device-01",
                limit=50,
            ),
            metadata=(
                ("authorization", f"Bearer {snapshot.portal_access_token}"),
            ),
        )
        assert portal_snapshot.client_id == str(registered_client.id)
        assert portal_snapshot.nickname == "V2 Player"
        assert [item.name for item in portal_snapshot.tariffs] == ["V2 час"]
        assert len(portal_snapshot.sessions) == 1
        await sessions.stop(uuid.UUID(snapshot.payload.session_id))

        with pytest.raises(grpc.aio.AioRpcError) as error:
            await client.Login(
                offline_session_service_pb2.LoginOfflineSessionRequest(
                    device_id="another-device",
                    identifier="V2 Player",
                    password="safe-password",
                    idempotency_key="v2-login-grpc-002",
                ),
                metadata=(("authorization", f"Bearer {device_token}"),),
            )
        assert error.value.code() is grpc.StatusCode.PERMISSION_DENIED

        await clients.reset_password(registered_client.id)
        challenge = await client.Login(
            offline_session_service_pb2.LoginOfflineSessionRequest(
                device_id="v2-device-01",
                identifier="V2 Player",
                password="",
                idempotency_key="v2-reset-login-grpc-001",
            ),
            metadata=(("authorization", f"Bearer {device_token}"),),
        )
        assert challenge.password_reset_required is True
        await client.ChangePassword(
            offline_session_service_pb2.ChangeOfflinePasswordRequest(
                device_id="v2-device-01",
                new_password="new-safe-password",
            ),
            metadata=(("authorization", f"Bearer {challenge.password_reset_token}"),),
        )
        changed = await client.Login(
            offline_session_service_pb2.LoginOfflineSessionRequest(
                device_id="v2-device-01",
                identifier="V2 Player",
                password="new-safe-password",
                idempotency_key="v2-reset-login-grpc-002",
            ),
            metadata=(("authorization", f"Bearer {device_token}"),),
        )
        assert changed.payload.client_id == str(registered_client.id)
        await sessions.stop(uuid.UUID(changed.payload.session_id))

        registered = await client.Register(
            offline_session_service_pb2.RegisterOfflineSessionRequest(
                device_id="v2-device-01",
                nickname="V2 gRPC Register",
                phone="79991230003",
                password="safe-password",
                idempotency_key="v2-register-grpc-001",
            ),
            metadata=(("authorization", f"Bearer {device_token}"),),
        )
        assert registered.payload.device_id == "v2-device-01"
    finally:
        await channel.close()
        await server.stop(None)
