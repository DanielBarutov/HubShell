import base64
import datetime
import uuid

import grpc
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from gameclub.v2 import offline_session_service_pb2, offline_session_service_pb2_grpc
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.billing.infrastructure.memory import InMemoryChargeRepository
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import BillingMode
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.client_groups.application.service import ClientGroupService
from gameclub_backend.modules.client_groups.domain import ClientGroup
from gameclub_backend.modules.client_groups.infrastructure.memory import (
    InMemoryClientGroupRepository,
)
from gameclub_backend.modules.clients.application.bonus import BonusCommand
from gameclub_backend.modules.clients.application.portal import ClientPortalService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.bonus import BonusOperationKind, BonusPolicy
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
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    serialize_snapshot_payload,
)
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationSessionMode
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.presentation.grpc.services import OfflineSessionGrpcService

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("interrupt", [False, True])
async def test_v2_server_stop_keeps_bonus_reserve_until_ordered_client_stop(
    interrupt: bool,
) -> None:
    """Серверная остановка не освобождает резерв до подтверждения накопленных V2-фактов."""
    service, sessions, _, clients, client = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER, bonuses=True
    )
    await clients.top_up(client.id, 10000, 100, "Opening", "owner", "opening")
    login = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="stop-bonus",
    )
    session_id = uuid.UUID(login.payload.session_id)
    await clients.apply_bonus_operation(
        BonusCommand(
            client.id, BonusOperationKind.RESERVE, 0, "owner", "Reserve", "reserve", session_id
        )
    )
    if interrupt:
        await sessions.interrupt(session_id, "owner", "Interrupt", "interrupt")
    else:
        await sessions.stop(session_id)
        await sessions.stop(session_id)
    assert (await clients.get_bonus_wallet(client.id)).reserved_cents == 10000


@pytest.mark.parametrize("limit", [2000, 10000])
async def test_v2_bonus_package_quote_confirmation_and_signed_money(limit: int) -> None:
    """Подтверждает по JWT бонусную покупку и подписывает только её денежную часть."""
    service, _, portal, clients, client = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER, bonuses=True
    )
    admin = Principal("owner", SubjectType.OPERATOR, frozenset(), frozenset({"settings.manage"}))
    await clients.update_bonus_policy(BonusPolicy(payment_limit_bps=limit), admin, "policy")
    await clients.top_up(client.id, 10000, 100, "Opening", "owner", "opening")
    login = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="bonus-login",
    )
    tariff = await portal._tariffs.create_tariff(
        "Bonus package", None, 60, 10000, datetime.datetime.now(datetime.UTC), None
    )
    server = grpc.aio.server()
    offline_session_service_pb2_grpc.add_OfflineSessionServiceServicer_to_server(
        OfflineSessionGrpcService(service, service._token_service), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    metadata = (("authorization", f"Bearer {login.portal_access_token}"),)
    try:
        rpc = offline_session_service_pb2_grpc.OfflineSessionServiceStub(channel)
        request = offline_session_service_pb2.QuoteOfflineEntitlementRequest(
            device_id="v2-device-01", tariff_id=str(tariff.id), use_bonus=True
        )
        with pytest.raises(grpc.aio.AioRpcError) as denied:
            await rpc.QuoteEntitlement(request)
        assert denied.value.code() == grpc.StatusCode.UNAUTHENTICATED
        quote = await rpc.QuoteEntitlement(request, metadata=metadata)
        assert quote.bonus_cents == limit
        assert quote.money_cents == 10000 - limit
        confirmation = offline_session_service_pb2.OfflineBonusPurchaseConfirmation(
            price_cents=quote.price_cents,
            bonus_cents=quote.bonus_cents,
            money_cents=quote.money_cents,
            earned_bonus_cents=quote.earned_bonus_cents,
        )
        purchase_request = offline_session_service_pb2.PurchaseOfflineEntitlementRequest(
            device_id="v2-device-01",
            tariff_id=str(tariff.id),
            idempotency_key="bonus-purchase",
            bonus_confirmation=confirmation,
        )
        purchase_request.bonus_confirmation.price_cents += 1
        with pytest.raises(grpc.aio.AioRpcError) as stale:
            await rpc.PurchaseEntitlement(purchase_request, metadata=metadata)
        assert stale.value.code() == grpc.StatusCode.FAILED_PRECONDITION
        assert (await clients.get(client.id)).balance_cents == 10000
        purchase_request.bonus_confirmation.CopyFrom(confirmation)
        response = await rpc.PurchaseEntitlement(purchase_request, metadata=metadata)
        repeated = await rpc.PurchaseEntitlement(purchase_request, metadata=metadata)
        payload = response.purchased_package.payload
        assert payload.HasField("purchase_money_cents")
        assert payload.purchase_money_cents == quote.money_cents
        assert payload.purchase_bonus_cents == quote.bonus_cents
        assert payload.tariffs[0].package_price_cents == 10000
        assert repeated.purchased_package.payload.snapshot_id == payload.snapshot_id
        assert response.HasField("bonus_wallet")
        assert response.bonus_wallet.total_cents == 10000 - limit
        assert response.bonus_wallet.available_cents == 10000 - limit
        assert response.bonus_wallet.reserved_cents == 0
        assert response.bonus_wallet.pending_cents == quote.earned_bonus_cents
        assert (await clients.get(client.id)).balance_cents == limit
        assert (await clients.get_bonus_wallet(client.id)).total_cents == 10000 - limit
        assert await clients.get_pending_bonus_cents(client.id) == quote.earned_bonus_cents
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode("11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=")
        )
        public_key.verify(response.purchased_package.signature, serialize_snapshot_payload(payload))
        payload.purchase_money_cents += 1
        with pytest.raises(InvalidSignature):
            public_key.verify(
                response.purchased_package.signature, serialize_snapshot_payload(payload)
            )
    finally:
        await channel.close()
        await server.stop(None)


class SnapshotIssueMemoryRepository:
    def __init__(self, sessions: InMemorySessionRepository) -> None:
        self._items = {}
        self._leases = {}
        self._sessions = sessions

    async def has_active_lease(
        self,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
        device_id: str,
    ) -> bool:
        lease = self._leases.get(session_id)
        return bool(
            lease is not None and lease.client_id == client_id and lease.device_id == device_id
        )

    async def issue(self, value: V2SignedSnapshotIssue) -> V2SnapshotIssueResult:
        existing = self._items.get(value.lease.session_id)
        if existing is not None:
            return V2SnapshotIssueResult(
                signed_snapshot=existing,
                login_event_id=value.lease.snapshot_id,
                is_duplicate=True,
            )
        self._items[value.lease.session_id] = value.signed_snapshot
        self._leases[value.lease.session_id] = value.lease
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


class RecordingV2SessionLeaseRevoker:
    def __init__(self) -> None:
        self.revocations: list[tuple[uuid.UUID, datetime.datetime]] = []

    async def revoke(self, session_id: uuid.UUID, revoked_at: datetime.datetime) -> None:
        self.revocations.append((session_id, revoked_at))


async def build_service(
    mode: WorkstationSessionMode,
    *,
    minute_rates: tuple[int, ...] = (),
    allow_debt: bool = False,
    discount_bps: int | None = None,
    free_minutes: int = 0,
    bonuses: bool = False,
) -> tuple[V2OfflineLoginService, SessionService, ClientPortalService, ClientService, Client]:
    client_groups = InMemoryClientGroupRepository()
    if allow_debt:
        await client_groups.save(
            ClientGroup(
                id="regular",
                name="Credit",
                is_default=True,
                allow_negative_balance=True,
                negative_balance_limit_cents=1000,
            )
        )
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
    for rate in minute_rates:
        await catalog.create_tariff(
            f"Rate {rate}",
            None,
            1,
            0,
            datetime.datetime.now(datetime.UTC),
            None,
            billing_mode=BillingMode.PER_MINUTE,
            price_per_minute_cents=rate,
            free_minutes=free_minutes,
        )
    sessions = SessionService(
        session_repository,
        workstations=workstations,
        clients=clients,
        bonuses=clients if bonuses else None,
    )
    entitlements = EntitlementService(
        InMemoryEntitlementRepository(),
        tariffs=catalog,
        clients=clients,
        bonuses=clients if bonuses else None,
        active_sessions=session_repository if bonuses else None,
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
    if discount_bps is not None:
        await catalog.create_discount_rule(
            "admin",
            percent_bps=discount_bps,
            priority=0,
            valid_from=datetime.datetime.now(datetime.UTC),
            valid_to=None,
        )
        client = await clients.update(client.id, client.nickname, client.phone, " ADMIN ")
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


@pytest.mark.parametrize("discount_bps, expected_rate", [(0, 100), (1250, 88), (10000, 0)])
@pytest.mark.parametrize("free_minutes", [0, 3])
async def test_v2_login_signs_discounted_minute_rate(
    discount_bps: int, expected_rate: int, free_minutes: int
) -> None:
    service, _, _, _, _ = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER,
        minute_rates=(150, 100),
        discount_bps=discount_bps,
        free_minutes=free_minutes,
    )
    signed = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="discount-login",
    )
    rate = next(item for item in signed.payload.tariffs if item.name == "Rate 100")
    assert rate.per_minute_price_cents == expected_rate
    assert rate.is_per_minute
    assert all(
        not item.is_per_minute for item in signed.payload.tariffs if item.package_minutes == 60
    )


async def test_v2_discount_does_not_create_a_missing_minute_rate() -> None:
    service, _, _, _, _ = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER, discount_bps=10000
    )
    signed = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="disabled-rate-login",
    )
    assert all(not item.is_per_minute for item in signed.payload.tariffs)


@pytest.mark.asyncio
async def test_stop_and_interrupt_revoke_v2_session_leases() -> None:
    """Проверяет, что обычное и досрочное завершение освобождают V2 lease."""
    now = datetime.datetime.now(datetime.UTC)
    started_at = now - datetime.timedelta(minutes=3)
    sessions = [
        Session(
            id=uuid.uuid4(),
            workstation_id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            guest_name=None,
            status=SessionStatus.ACTIVE,
            started_at=started_at,
            ended_at=None,
            source="local_ledger",
            created_by="v2-stop-test",
            created_at=started_at,
        )
        for _ in range(2)
    ]
    repository = InMemorySessionRepository()
    for session in sessions:
        await repository.save(session)
    leases = RecordingV2SessionLeaseRevoker()
    service = SessionService(
        repository,
        workstations=None,
        clients=None,
        v2_session_leases=leases,
    )

    stopped = await service.stop(sessions[0].id)
    interrupted = await service.interrupt(
        sessions[1].id,
        interrupted_by="operator-test",
        reason="premature stop",
        idempotency_key="v2-stop-test",
    )

    assert stopped.status is SessionStatus.COMPLETED
    assert interrupted.status is SessionStatus.COMPLETED
    assert leases.revocations == [
        (sessions[0].id, stopped.ended_at),
        (sessions[1].id, interrupted.ended_at),
    ]


async def test_v2_login_creates_only_v2_session_and_reuses_signed_snapshot_on_retry() -> None:
    """Проверяет заявленное поведение backend."""
    service, sessions, _, _, _ = await build_service(WorkstationSessionMode.LOCAL_LEDGER)

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
    assert active[0].source == "local_ledger"
    assert active[0].login_grant_minutes == 1
    assert first.payload.session_id == str(active[0].id)
    assert first.SerializeToString() == repeated.SerializeToString()


@pytest.mark.asyncio
async def test_v2_device_stop_completes_only_its_client_session() -> None:
    """Проверяет, что V2 device может завершить только привязанную к нему сессию."""
    service, sessions, _, _, client = await build_service(WorkstationSessionMode.LOCAL_LEDGER)
    signed_snapshot = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="v2-stop-login",
    )
    session_id = uuid.UUID(signed_snapshot.payload.session_id)

    await service.stop_session(
        device_id="v2-device-01",
        session_id=session_id,
        client_id=client.id,
    )

    stopped = await sessions.get(session_id)
    assert stopped is not None
    assert stopped.status is SessionStatus.COMPLETED
    assert stopped.ended_at is not None
    assert await sessions.list(active_only=True) == []


async def test_v2_portal_resume_issues_token_for_the_same_active_session_and_device() -> None:
    """После перезапуска восстанавливает portal-доступ только для lease текущего аккаунта."""
    service, sessions, _, _, client = await build_service(WorkstationSessionMode.LOCAL_LEDGER)
    signed_snapshot = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="v2-resume-login",
    )

    resumed = await service.resume_portal(
        device_id="v2-device-01",
        session_id=uuid.UUID(signed_snapshot.payload.session_id),
        client_id=client.id,
    )
    principal = JwtTokenService(
        Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    ).validate_access_token(resumed.portal_access_token)

    active = await sessions.list(active_only=True)
    assert len(active) == 1
    assert principal.subject_id == str(client.id)
    assert principal.device_id == "v2-device-01"
    assert resumed.client_id == client.id
    assert resumed.portal_access_expires_in > 0


async def test_v2_login_rejects_a_workstation_that_remains_in_v1_mode() -> None:
    """Проверяет заявленное поведение backend."""
    service, sessions, _, _, _ = await build_service(WorkstationSessionMode.SERVER_OWNED)

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
    """Проверяет заявленное поведение backend."""
    service, sessions, portal, clients, client = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER
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
    """Проверяет заявленное поведение backend."""
    service, sessions, _, _, _ = await build_service(WorkstationSessionMode.LOCAL_LEDGER)

    snapshot = await service.register(
        device_id="v2-device-01",
        nickname="V2 New Player",
        phone="79991230002",
        password="safe-password",
        idempotency_key="v2-register-001",
    )

    active = await sessions.list(active_only=True)
    assert len(active) == 1
    assert active[0].source == "local_ledger"
    assert snapshot.payload.client_id == str(active[0].client_id)


async def test_v2_grpc_login_requires_the_same_device_identity() -> None:
    """Проверяет заявленное поведение backend."""
    service, sessions, _, clients, registered_client = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER
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
            metadata=(("authorization", f"Bearer {snapshot.portal_access_token}"),),
        )
        assert portal_snapshot.client_id == str(registered_client.id)
        assert portal_snapshot.nickname == "V2 Player"
        assert [item.name for item in portal_snapshot.tariffs] == ["V2 час"]
        assert len(portal_snapshot.sessions) == 1
        resumed = await client.ResumePortal(
            offline_session_service_pb2.ResumeOfflinePortalRequest(
                device_id="v2-device-01",
                session_id=snapshot.payload.session_id,
                client_id=registered_client.id.hex,
            ),
            metadata=(("authorization", f"Bearer {device_token}"),),
        )
        assert resumed.client_id == str(registered_client.id)
        resumed_portal = await client.GetPortalSnapshot(
            offline_session_service_pb2.GetOfflinePortalSnapshotRequest(
                device_id="v2-device-01",
                limit=50,
            ),
            metadata=(("authorization", f"Bearer {resumed.portal_access_token}"),),
        )
        assert resumed_portal.client_id == str(registered_client.id)
        assert resumed_portal.nickname == "V2 Player"
        with pytest.raises(grpc.aio.AioRpcError) as wrong_client:
            await client.ResumePortal(
                offline_session_service_pb2.ResumeOfflinePortalRequest(
                    device_id="v2-device-01",
                    session_id=snapshot.payload.session_id,
                    client_id=str(uuid.uuid4()),
                ),
                metadata=(("authorization", f"Bearer {device_token}"),),
            )
        assert wrong_client.value.code() is grpc.StatusCode.ALREADY_EXISTS

        await sessions.stop(uuid.UUID(snapshot.payload.session_id))
        with pytest.raises(grpc.aio.AioRpcError) as stopped_session:
            await client.ResumePortal(
                offline_session_service_pb2.ResumeOfflinePortalRequest(
                    device_id="v2-device-01",
                    session_id=snapshot.payload.session_id,
                    client_id=str(registered_client.id),
                ),
                metadata=(("authorization", f"Bearer {device_token}"),),
            )
        assert stopped_session.value.code() is grpc.StatusCode.ALREADY_EXISTS

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


async def test_login_snapshot_has_only_server_selected_per_minute_rate() -> None:
    service, _, _, _, _ = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER, minute_rates=(150, 100)
    )
    snapshot = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="v2-login-rates",
    )
    rates = [item for item in snapshot.payload.tariffs if item.per_minute_price_cents > 0]
    assert len(rates) == 1
    assert rates[0].per_minute_price_cents == 100
    assert any(item.name == "V2 час" for item in snapshot.payload.tariffs)


async def test_new_package_after_login_is_signed_and_purchased_with_debt_once() -> None:
    """Покупает новый тариф в долг и повторяет ответ без второго списания."""
    service, _, portal, clients, client = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER,
        allow_debt=True,
    )
    await clients.debit(
        client.id, 500, "Test debt", "test", "test-debt", allow_negative_balance=True
    )
    login = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="login-new-package",
    )
    tariff = await portal._tariffs.create_tariff(
        "Test 2 minutes", None, 2, 100, datetime.datetime.now(datetime.UTC), None
    )
    assert str(tariff.id) not in {item.tariff_id for item in login.payload.tariffs}
    server = grpc.aio.server()
    offline_session_service_pb2_grpc.add_OfflineSessionServiceServicer_to_server(
        OfflineSessionGrpcService(service, service._token_service),
        server,
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    try:
        rpc = offline_session_service_pb2_grpc.OfflineSessionServiceStub(channel)
        response = await rpc.PurchaseEntitlement(
            offline_session_service_pb2.PurchaseOfflineEntitlementRequest(
                device_id="v2-device-01",
                tariff_id=str(tariff.id),
                idempotency_key="purchase-new-package",
            ),
            metadata=(("authorization", f"Bearer {login.portal_access_token}"),),
        )
        assert response.purchased_package.payload.purchase_idempotency_key == "purchase-new-package"
        assert response.purchased_package.payload.tariffs[0].package_price_cents == 100
        assert response.purchased_package.signature
    finally:
        await channel.close()
        await server.stop(None)
    purchase = await service.purchase_entitlement(
        client_id=client.id,
        device_id="v2-device-01",
        tariff_id=tariff.id,
        idempotency_key="purchase-new-package",
    )
    repeated = await service.purchase_entitlement(
        client_id=client.id,
        device_id="v2-device-01",
        tariff_id=tariff.id,
        idempotency_key="purchase-new-package",
    )
    receipt = purchase.purchased_package
    public_key = Ed25519PublicKey.from_public_bytes(
        base64.b64decode("11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=")
    )
    public_key.verify(receipt.signature, serialize_snapshot_payload(receipt.payload))
    changed = type(receipt.payload)()
    changed.CopyFrom(receipt.payload)
    changed.purchase_idempotency_key = "another-purchase"
    with pytest.raises(InvalidSignature):
        public_key.verify(receipt.signature, serialize_snapshot_payload(changed))
    assert receipt.payload.session_id == login.payload.session_id
    assert receipt.payload.purchase_idempotency_key == "purchase-new-package"
    assert receipt.payload.packages[0].package_id == str(purchase.portal.purchased_entitlement.id)
    assert receipt.payload.packages[0].remaining_minutes == 2
    assert receipt.payload.tariffs[0].package_price_cents == 100
    assert repeated.purchased_package.payload.snapshot_id == receipt.payload.snapshot_id
    assert (await clients.get(client.id)).balance_cents == -600


async def test_night_activation_and_refresh_return_signed_session_bound_package() -> None:
    service, sessions, portal, clients, client = await build_service(
        WorkstationSessionMode.LOCAL_LEDGER, minute_rates=(100,)
    )
    now = datetime.datetime(2026, 10, 19, 23, tzinfo=datetime.UTC)

    class FixedClock:
        def now(self) -> datetime.datetime:
            return now

    for component in (service, portal, portal._tariffs, portal._entitlements):
        component._clock = FixedClock()
    tariff = await portal._tariffs.create_tariff(
        "Night",
        None,
        660,
        500,
        now - datetime.timedelta(days=1),
        None,
        time_restricted=True,
        sale_window_start_minute=22 * 60,
        sale_window_end_minute=8 * 60,
        usage_window_start_minute=22 * 60,
        usage_window_end_minute=8 * 60,
        window_timezone="Etc/UTC",
    )
    await clients.top_up(client.id, 1000, 0, "Opening", "owner", "night-opening")
    package = await portal._entitlements.purchase(client.id, tariff.id, "test", "night-package")
    login = await service.login(
        device_id="v2-device-01",
        identifier="V2 Player",
        password="safe-password",
        idempotency_key="night-login",
    )
    initial = next(item for item in login.payload.packages if item.package_id == str(package.id))
    assert initial.usage_window_start_minute == 1320
    assert initial.usage_window_end_minute == 480
    assert initial.window_timezone == "Etc/UTC"
    server = grpc.aio.server()
    offline_session_service_pb2_grpc.add_OfflineSessionServiceServicer_to_server(
        OfflineSessionGrpcService(service, service._token_service), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    metadata = (("authorization", f"Bearer {login.portal_access_token}"),)
    try:
        stub = offline_session_service_pb2_grpc.OfflineSessionServiceStub(channel)
        response = await stub.ActivateEntitlement(
            offline_session_service_pb2.ActivateOfflineEntitlementRequest(
                device_id="v2-device-01", entitlement_id=str(package.id)
            ),
            metadata=metadata,
        )
        receipt = response.active_package
        assert receipt.payload.session_id == login.payload.session_id
        assert receipt.payload.client_id == str(client.id)
        assert receipt.payload.device_id == "v2-device-01"
        assert len(receipt.payload.packages) == 1
        active = receipt.payload.packages[0]
        assert active.package_id == str(package.id)
        assert active.remaining_minutes == 660
        assert active.usage_window_closes_at.ToDatetime(tzinfo=datetime.UTC) == datetime.datetime(
            2026, 10, 20, 8, tzinfo=datetime.UTC
        )
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode("11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=")
        )
        public_key.verify(receipt.signature, serialize_snapshot_payload(receipt.payload))
        refreshed = await stub.GetPortalSnapshot(
            offline_session_service_pb2.GetOfflinePortalSnapshotRequest(device_id="v2-device-01"),
            metadata=metadata,
        )
        assert refreshed.active_package.payload.snapshot_id == receipt.payload.snapshot_id
        assert (await clients.get(client.id)).balance_cents == 500
        await sessions.stop(uuid.UUID(login.payload.session_id))
        assert (
            await service.get_active_package_snapshot(client_id=client.id, device_id="v2-device-01")
            is None
        )
    finally:
        await channel.close()
        await server.stop(None)
