"""Real PostgreSQL races between coordinated updates and session admission."""

import asyncio
import contextvars
import dataclasses
import datetime
import os
import uuid
from types import SimpleNamespace

import grpc
import pytest
from sqlalchemy import String, delete, select, text, update
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub.v2 import offline_session_service_pb2 as transfer_api
from gameclub.v2 import offline_session_service_pb2_grpc
from gameclub.v2 import offline_session_snapshot_pb2 as snapshots_api
from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.audit_postgres import AuditEventModel
from gameclub_backend.infrastructure.database import application_transaction
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.catalog.domain import BillingMode, Tariff
from gameclub_backend.modules.clients.domain import Client
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.direct_payments.domain import DirectPaymentStatus, GuestSessionPayment
from gameclub_backend.modules.direct_payments.infrastructure.postgres import (
    GuestSessionPaymentModel,
    PostgresGuestSessionPaymentRepository,
)
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.domain import Entitlement, EntitlementStatus
from gameclub_backend.modules.entitlements.infrastructure.postgres import (
    EntitlementModel,
    PostgresEntitlementRepository,
)
from gameclub_backend.modules.eventing_v2.application.guest_access import GuestAccessGrant
from gameclub_backend.modules.eventing_v2.application.guest_transfer_time import GuestTransferClock
from gameclub_backend.modules.eventing_v2.application.lease import V2SessionLease
from gameclub_backend.modules.eventing_v2.application.snapshot_issue import V2SignedSnapshotIssue
from gameclub_backend.modules.eventing_v2.application.transfer_commit import V2TransferCommitService
from gameclub_backend.modules.eventing_v2.application.transfer_start import V2TransferStartService
from gameclub_backend.modules.eventing_v2.application.update_readiness import (
    V2ClientUpdateReadiness,
)
from gameclub_backend.modules.eventing_v2.domain import V2SessionChain
from gameclub_backend.modules.eventing_v2.infrastructure.bonus_budget_postgres import (
    V2BonusBudgetModel,
)
from gameclub_backend.modules.eventing_v2.infrastructure.guest_access_postgres import (
    GuestAccessGrantModel,
    GuestTransferAccessModel,
    PostgresGuestAccessGrantRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.lease_postgres import V2SessionLeaseModel
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
    PostgresV2SessionChainRepository,
    V2ServerOutboxModel,
    V2SessionChainModel,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_ed25519 import (
    V2Ed25519SnapshotSigner,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_issue_postgres import (
    PostgresV2SnapshotIssueRepository,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    sign_offline_session_snapshot,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.domain import Reservation, ReservationStatus
from gameclub_backend.modules.reservations.infrastructure.postgres import (
    PostgresReservationRepository,
    ReservationModel,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.v2_transfer import (
    V2TransferCheckpoint,
    V2TransferPreparationService,
    V2TransferStatus,
    V2TransferTargetService,
)
from gameclub_backend.modules.sessions.domain import (
    Session,
    SessionStatus,
    SessionTransferOffer,
    TransferStatus,
)
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionAdmission,
    PostgresSessionRepository,
    PostgresSessionTransactionWriter,
    SessionAdmissionBlockModel,
    SessionModel,
    V2TransferReservationModel,
)
from gameclub_backend.modules.sessions.infrastructure.transfers_postgres import (
    PostgresSessionTransferRepository,
    SessionTransferOfferModel,
)
from gameclub_backend.modules.sessions.infrastructure.v2_transfers_postgres import (
    PostgresV2TransferReservations,
)
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import Workstation
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.presentation.grpc.services import OfflineSessionGrpcService

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.concurrency]


@pytest.fixture
async def admission_context():
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to test session admission")
    engine = create_async_engine(dsn)

    def provider():
        return engine

    deployment_id = uuid.uuid4()
    workstation_ids = (uuid.uuid4(), uuid.uuid4())
    try:
        yield provider, deployment_id, workstation_ids
    finally:
        async with engine.begin() as transaction:
            session_ids = select(SessionModel.id).where(
                SessionModel.workstation_id.in_(workstation_ids)
            )
            await transaction.execute(
                delete(AuditEventModel).where(
                    AuditEventModel.action == "v2.snapshot.issued",
                    AuditEventModel.request_id.in_(
                        select(V2ServerOutboxModel.event_id.cast(String)).where(
                            V2ServerOutboxModel.session_id.in_(session_ids)
                        )
                    ),
                )
            )
            await transaction.execute(
                delete(V2ServerOutboxModel).where(V2ServerOutboxModel.session_id.in_(session_ids))
            )
            await transaction.execute(
                delete(EntitlementModel).where(
                    EntitlementModel.client_id.in_(
                        select(SessionModel.client_id).where(SessionModel.id.in_(session_ids))
                    ),
                    EntitlementModel.idempotency_key.like("test-transfer-active-%"),
                )
            )
            await transaction.execute(
                delete(V2BonusBudgetModel).where(V2BonusBudgetModel.session_id.in_(session_ids))
            )
            await transaction.execute(
                delete(GuestTransferAccessModel).where(
                    GuestTransferAccessModel.session_id.in_(session_ids)
                )
            )
            await transaction.execute(
                delete(GuestSessionPaymentModel).where(
                    GuestSessionPaymentModel.workstation_id.in_(workstation_ids)
                )
            )
            await transaction.execute(
                delete(GuestAccessGrantModel).where(
                    GuestAccessGrantModel.session_id.in_(session_ids)
                )
            )
            await transaction.execute(
                delete(V2SessionLeaseModel).where(V2SessionLeaseModel.session_id.in_(session_ids))
            )
            await transaction.execute(
                delete(V2SessionChainModel).where(
                    V2SessionChainModel.session_id.in_(
                        select(SessionModel.id).where(
                            SessionModel.workstation_id.in_(workstation_ids)
                        )
                    )
                )
            )
            await transaction.execute(
                delete(V2TransferReservationModel).where(
                    V2TransferReservationModel.source_workstation_id.in_(workstation_ids)
                )
            )
            await transaction.execute(
                delete(SessionTransferOfferModel).where(
                    SessionTransferOfferModel.source_workstation_id.in_(workstation_ids)
                )
            )
            await transaction.execute(
                delete(SessionAdmissionBlockModel).where(
                    SessionAdmissionBlockModel.deployment_id == deployment_id
                )
            )
            await transaction.execute(
                delete(SessionModel).where(SessionModel.workstation_id.in_(workstation_ids))
            )
        await engine.dispose()


def new_session(workstation_id: uuid.UUID, *, client: bool = False) -> Session:
    now = datetime.datetime.now(datetime.UTC)
    return Session(
        id=uuid.uuid4(),
        workstation_id=workstation_id,
        client_id=uuid.uuid4() if client else None,
        guest_name=None if client else "deployment-test",
        status=SessionStatus.ACTIVE,
        started_at=now,
        ended_at=None,
        source="local_ledger",
        created_by="deployment-test",
        created_at=now,
    )


async def test_one_active_session_blocks_entire_barrier(admission_context):
    """Один активный сеанс запрещает барьер для всего парка."""
    provider, deployment_id, ids = admission_context
    sessions = PostgresSessionRepository(provider)
    await sessions.save(new_session(ids[1]))
    with pytest.raises(ApplicationError, match="active session"):
        await PostgresSessionAdmission(provider).block(deployment_id, ids)
    # Failed preparation did not accidentally close the other workstation.
    await sessions.save(new_session(ids[0]))


async def test_barrier_survives_new_repository_and_rejects_new_starts(admission_context):
    """Барьер сохраняется после пересоздания репозитория и снимается только своим выпуском."""
    provider, deployment_id, ids = admission_context
    await PostgresSessionAdmission(provider).block(deployment_id, ids)
    await PostgresSessionAdmission(provider).block(deployment_id, ids)
    await PostgresSessionAdmission(provider).unblock(uuid.uuid4())
    sessions = PostgresSessionRepository(provider)
    for workstation_id in ids:
        with pytest.raises(ApplicationError, match="blocks new sessions"):
            await sessions.save(new_session(workstation_id))
    await PostgresSessionAdmission(provider).unblock(deployment_id)
    await sessions.save(new_session(ids[0]))


async def test_reactivation_and_move_cannot_bypass_barrier(admission_context):
    """Повторная активация и перенос не обходят барьер, исторические исправления разрешены."""
    provider, deployment_id, ids = admission_context
    sessions = PostgresSessionRepository(provider)
    old = new_session(ids[0])
    completed = old.stop(datetime.datetime.now(datetime.UTC))
    await sessions.save(completed)
    await PostgresSessionAdmission(provider).block(deployment_id, ids)
    with pytest.raises(ApplicationError, match="blocks new sessions"):
        await sessions.save(old)
    # Updating historical data remains possible without opening a session.
    await sessions.save(dataclasses.replace(completed, guest_name="historical correction"))
    with pytest.raises(ApplicationError, match="blocks new sessions"):
        await sessions.save(dataclasses.replace(old, workstation_id=ids[1]))


@pytest.mark.parametrize("client_session", [False, True], ids=["guest", "client"])
async def test_in_flight_session_commits_before_barrier_can_check(
    admission_context, client_session
):
    """Барьер ждёт незавершённую транзакцию входа и обнаруживает её сеанс."""
    provider, deployment_id, ids = admission_context
    started = asyncio.Event()
    gate = PostgresSessionAdmission(provider)

    async def prepare():
        started.set()
        await gate.block(deployment_id, ids)

    async with application_transaction(provider) as transaction:
        await PostgresSessionTransactionWriter().save(
            transaction, new_session(ids[0], client=client_session)
        )
        task = asyncio.create_task(prepare(), context=contextvars.Context())
        await started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 0.1)
    with pytest.raises(ApplicationError, match="active session"):
        await asyncio.wait_for(task, 3)


@pytest.mark.parametrize("client_session", [False, True], ids=["guest", "client"])
async def test_in_flight_barrier_commits_before_new_session_can_start(
    admission_context, client_session
):
    """Новый вход ждёт фиксации барьера и получает отказ."""
    provider, deployment_id, ids = admission_context
    started = asyncio.Event()

    async def start():
        started.set()
        await PostgresSessionRepository(provider).save(new_session(ids[0], client=client_session))

    async with application_transaction(provider):
        await PostgresSessionAdmission(provider).block(deployment_id, ids)
        task = asyncio.create_task(start(), context=contextvars.Context())
        await started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 0.1)
    with pytest.raises(ApplicationError, match="blocks new sessions"):
        await asyncio.wait_for(task, 3)


async def test_existing_deployment_cannot_change_membership(admission_context):
    """Повтор подготовки не меняет список ПК и не вытесняет другую доставку."""
    provider, deployment_id, ids = admission_context
    admission = PostgresSessionAdmission(provider)
    await admission.block(deployment_id, ids)
    with pytest.raises(ApplicationError, match="list changed"):
        await admission.block(deployment_id, ids[:1])
    with pytest.raises(ApplicationError, match="Another deployment"):
        await admission.block(uuid.uuid4(), ids)


async def test_access_grant_recovery_cannot_bypass_durable_barrier(admission_context):
    """Даже повторная выдача snapshot проверяет барьер для существующей или новой сессии."""
    provider, deployment_id, ids = admission_context
    sessions = PostgresSessionRepository(provider)
    old = new_session(ids[0]).stop(datetime.datetime.now(datetime.UTC))
    await sessions.save(old)
    await PostgresSessionAdmission(provider).block(deployment_id, ids)
    writer = PostgresSessionTransactionWriter()
    for session_id in [old.id, uuid.uuid4()]:
        with pytest.raises(ApplicationError, match="blocks new"):
            async with application_transaction(provider) as transaction:
                await writer.require_access(transaction, session_id)


async def transfer_offer(provider, ids):
    """Создаёт сеанс и предложение для настоящего transaction writer переноса."""
    current = new_session(ids[0], client=True)
    await PostgresSessionRepository(provider).save(current)
    now = datetime.datetime.now(datetime.UTC)
    pending = SessionTransferOffer(
        id=uuid.uuid4(),
        session_id=current.id,
        client_id=current.client_id,
        source_workstation_id=ids[0],
        target_workstation_id=ids[1],
        token=uuid.uuid4().hex,
        status=TransferStatus.PENDING,
        requires_package_burn=False,
        warning=None,
        idempotency_key=uuid.uuid4().hex,
        confirm_idempotency_key=None,
        created_at=now,
        expires_at=now + datetime.timedelta(minutes=1),
    )
    repository = PostgresSessionTransferRepository(provider)
    await repository.save(pending)
    return (
        repository,
        pending.confirm(uuid.uuid4().hex, now),
        dataclasses.replace(current, workstation_id=ids[1]),
    )


async def test_transfer_waits_for_committing_target_barrier_and_preserves_source(admission_context):
    """Перенос ждёт фиксации барьера и не меняет сеанс/offer при отказе целевого PC."""
    provider, deployment_id, ids = admission_context
    repository, offer, moved = await transfer_offer(provider, ids)
    started = asyncio.Event()

    async def transfer():
        started.set()
        return await repository.commit_transfer(offer, moved)

    async with application_transaction(provider):
        await PostgresSessionAdmission(provider).block(deployment_id, (ids[1],))
        task = asyncio.create_task(transfer(), context=contextvars.Context())
        await started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 0.1)
    with pytest.raises(ApplicationError, match="blocks new sessions"):
        await asyncio.wait_for(task, 3)
    assert (await PostgresSessionRepository(provider).get(moved.id)).workstation_id == ids[0]
    assert (await repository.get(offer.id)).status is TransferStatus.PENDING


async def test_barrier_waits_for_transfer_and_observes_moved_active_session(
    admission_context, monkeypatch
):
    """Незавершённый перенос удерживает admission lock до атомарного move/confirm."""
    from gameclub_backend.modules.sessions.infrastructure import transfers_postgres

    provider, deployment_id, ids = admission_context
    repository, offer, moved = await transfer_offer(provider, ids)
    entered, resume, preparing = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = transfers_postgres.require_session_admission

    async def pause_transfer(transaction, workstation_id):
        await original(transaction, workstation_id)
        if workstation_id == ids[1]:
            entered.set()
            await resume.wait()

    async def prepare():
        preparing.set()
        await PostgresSessionAdmission(provider).block(deployment_id, ids)

    monkeypatch.setattr(transfers_postgres, "require_session_admission", pause_transfer)
    transfer = asyncio.create_task(
        repository.commit_transfer(offer, moved), context=contextvars.Context()
    )
    gate = None
    try:
        await asyncio.wait_for(entered.wait(), 3)
        gate = asyncio.create_task(prepare(), context=contextvars.Context())
        await preparing.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(gate), 0.1)
        resume.set()
        confirmed, session = await asyncio.wait_for(transfer, 3)
        assert confirmed.status is TransferStatus.CONFIRMED and session.workstation_id == ids[1]
        with pytest.raises(ApplicationError, match="active session"):
            await asyncio.wait_for(gate, 3)
    finally:
        resume.set()
        tasks = [task for task in (transfer, gate) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_independent_barriers_do_not_block_or_release_other_pcs(admission_context):
    """Два ПК обновляются отдельно; снятие одного барьера не открывает другой."""
    provider, first, ids = admission_context
    second = uuid.uuid4()
    gate = PostgresSessionAdmission(provider)
    sessions = PostgresSessionRepository(provider)
    try:
        await gate.block(first, (ids[0],))
        await gate.block(second, (ids[1],))
        with pytest.raises(ApplicationError, match="Another deployment"):
            await gate.block(uuid.uuid4(), (ids[1],))
        await gate.unblock(first)
        await sessions.save(new_session(ids[0]))
        with pytest.raises(ApplicationError):
            await sessions.save(new_session(ids[1]))
        await gate.unblock(second)
        await sessions.save(new_session(ids[1]))
    finally:
        await gate.unblock(second)


async def test_new_access_grant_uses_its_pc_instead_of_unrelated_barrier(admission_context):
    """Барьер первого ПК не запрещает snapshot новой сессии второго ПК."""
    provider, deployment, ids = admission_context
    await PostgresSessionAdmission(provider).block(deployment, (ids[0],))
    writer = PostgresSessionTransactionWriter()
    async with application_transaction(provider) as transaction:
        await writer.require_access(transaction, uuid.uuid4(), ids[1])
    with pytest.raises(ApplicationError, match="blocks new sessions"):
        async with application_transaction(provider) as transaction:
            await writer.require_access(transaction, uuid.uuid4(), ids[0])


async def test_v2_transfer_target_rejects_new_sessions_until_cancel(admission_context):
    provider, _, (source_id, target_id) = admission_context
    sessions = PostgresSessionRepository(provider)
    source = await sessions.save(new_session(source_id, client=True))
    reservations = PostgresV2TransferReservations(provider)
    operation_id = uuid.uuid4()

    prepared = await reservations.prepare(operation_id, source.id, source_id, target_id)
    assert prepared.status is V2TransferStatus.PREPARING
    assert target_id in await reservations.list_reserved_targets()
    assert (
        await PostgresV2TransferReservations(provider).prepare(
            operation_id, source.id, source_id, target_id
        )
        == prepared
    )
    with pytest.raises(ApplicationError, match="parameters changed"):
        await reservations.prepare(operation_id, source.id, source_id, uuid.uuid4())
    with pytest.raises(ApplicationError, match="reserves this workstation"):
        await sessions.save(new_session(target_id))
    with pytest.raises(ApplicationError, match="not found"):
        await reservations.cancel(operation_id, target_id)
    cancelled = await reservations.cancel(operation_id, source_id)
    assert cancelled.status is V2TransferStatus.CANCELLED
    assert target_id not in await reservations.list_reserved_targets()
    assert await reservations.prepare(operation_id, source.id, source_id, target_id) == cancelled
    await sessions.save(new_session(target_id))


async def test_v2_transfer_reservation_expiry_cannot_renew_old_operation(admission_context):
    provider, _, (source_id, target_id) = admission_context
    sessions = PostgresSessionRepository(provider)
    guest = dataclasses.replace(new_session(source_id), source="guest_local_ledger")
    await sessions.save(guest)
    reservations = PostgresV2TransferReservations(provider)
    operation_id = uuid.uuid4()
    await reservations.prepare(operation_id, guest.id, source_id, target_id)

    async with provider().begin() as transaction:
        await transaction.execute(
            update(V2TransferReservationModel)
            .where(V2TransferReservationModel.operation_id == operation_id)
            .values(expires_at=text("clock_timestamp() - interval '1 second'"))
        )

    assert await reservations.expire_due() == 1
    assert await reservations.expire_due() == 0
    async with provider().connect() as connection:
        assert (
            await connection.scalar(
                select(V2TransferReservationModel.status).where(
                    V2TransferReservationModel.operation_id == operation_id
                )
            )
            == V2TransferStatus.EXPIRED
        )

    await sessions.save(new_session(target_id))
    assert target_id not in await reservations.list_reserved_targets()
    expired = await reservations.prepare(operation_id, guest.id, source_id, target_id)
    assert expired.status is V2TransferStatus.EXPIRED
    with pytest.raises(ApplicationError, match="active session"):
        await reservations.prepare(uuid.uuid4(), guest.id, source_id, target_id)


async def test_v2_transfer_target_has_one_winner_against_new_start(admission_context):
    provider, _, (source_id, target_id) = admission_context
    sessions = PostgresSessionRepository(provider)
    source = await sessions.save(new_session(source_id, client=True))
    reservations = PostgresV2TransferReservations(provider)

    outcomes = await asyncio.gather(
        reservations.prepare(uuid.uuid4(), source.id, source_id, target_id),
        sessions.save(new_session(target_id)),
        return_exceptions=True,
    )
    assert sum(isinstance(outcome, ApplicationError) for outcome in outcomes) == 1
    transfer, start = outcomes
    if isinstance(transfer, ApplicationError):
        assert "active session" in str(transfer)
        assert isinstance(start, Session)
    else:
        assert transfer.status is V2TransferStatus.PREPARING
        assert "reserves this workstation" in str(start)


async def test_two_v2_sources_cannot_reserve_same_target(admission_context):
    provider, _, source_ids = admission_context
    sessions = PostgresSessionRepository(provider)
    sources = [await sessions.save(new_session(item, client=True)) for item in source_ids]
    reservations = PostgresV2TransferReservations(provider)
    target_id = uuid.uuid4()

    outcomes = await asyncio.gather(
        *(
            reservations.prepare(uuid.uuid4(), item.id, item.workstation_id, target_id)
            for item in sources
        ),
        return_exceptions=True,
    )

    (conflict,) = (item for item in outcomes if isinstance(item, ApplicationError))
    assert "reserves this workstation" in str(conflict)
    (winner,) = (item for item in outcomes if not isinstance(item, ApplicationError))
    assert winner.status is V2TransferStatus.PREPARING


async def test_v2_transfer_recovers_readiness_and_source_checkpoint(admission_context):
    provider, _, (source_id, target_id) = admission_context
    source = await PostgresSessionRepository(provider).save(new_session(source_id, client=True))
    repo = PostgresV2TransferReservations(provider)
    operation = await repo.prepare(uuid.uuid4(), source.id, source_id, target_id)
    assert await repo.pending_for_target(target_id) == operation
    assert await repo.pending_for_target(source_id) is None

    with pytest.raises(ApplicationError, match="not found"):
        await repo.ready_target(operation.operation_id, source_id)
    with pytest.raises(ApplicationError, match="not found"):
        await repo.record_source_checkpoint(
            operation.operation_id, target_id, V2TransferCheckpoint(0, None)
        )
    with pytest.raises(ApplicationError, match="Invalid transfer checkpoint"):
        V2TransferCheckpoint(1, None)

    await repo.ready_target(operation.operation_id, target_id)
    checkpoint = V2TransferCheckpoint(1, "a" * 64)
    confirmed = await repo.record_source_checkpoint(operation.operation_id, source_id, checkpoint)

    restarted = PostgresV2TransferReservations(provider)
    assert await restarted.get_for_workstation(operation.operation_id, source_id) == confirmed
    assert await restarted.ready_target(operation.operation_id, target_id) == confirmed
    assert (
        await restarted.record_source_checkpoint(operation.operation_id, source_id, checkpoint)
        == confirmed
    )
    assert confirmed.target_ready and confirmed.source_checkpoint == checkpoint
    with pytest.raises(ApplicationError, match="checkpoint changed"):
        await restarted.record_source_checkpoint(
            operation.operation_id, source_id, V2TransferCheckpoint(2, "b" * 64)
        )


async def test_expired_v2_transfer_cannot_gain_readiness(admission_context):
    provider, _, (source_id, target_id) = admission_context
    source = await PostgresSessionRepository(provider).save(new_session(source_id, client=True))
    repo = PostgresV2TransferReservations(provider)
    operation = await repo.prepare(uuid.uuid4(), source.id, source_id, target_id)
    async with provider().begin() as db:
        await db.execute(
            update(V2TransferReservationModel)
            .where(V2TransferReservationModel.operation_id == operation.operation_id)
            .values(expires_at=text("clock_timestamp() - interval '1 second'"))
        )

    assert await repo.pending_for_target(target_id) is None
    late = await repo.ready_target(operation.operation_id, target_id)
    assert late.status is V2TransferStatus.EXPIRED
    assert not late.target_ready
    assert (
        await repo.record_source_checkpoint(
            operation.operation_id, source_id, V2TransferCheckpoint(0, None)
        )
        == late
    )


async def test_transfer_grpc_requires_confirmed_source_chain_and_authenticated_devices(
    admission_context,
):
    provider, _, (source_id, target_id) = admission_context
    source_session = await PostgresSessionRepository(provider).save(
        new_session(source_id, client=True)
    )
    assert source_session.client_id is not None
    operations = PostgresV2TransferReservations(provider)

    workstations = InMemoryWorkstationRepository()
    await workstations.save(
        Workstation(id=source_id, device_id="source", name="source", group_id="vip")
    )
    await workstations.save(Workstation(id=target_id, device_id="target", name="target"))
    devices = WorkstationService(workstations)
    await devices.heartbeat("source")
    await devices.heartbeat("target")
    sessions = SessionService(
        PostgresSessionRepository(provider), workstations, InMemoryClientRepository()
    )
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=2)
    expired_package = Tariff(uuid.uuid4(), "Пакет VIP", "vip", 60, 500, now, None, True)
    minute_tariff = Tariff(
        uuid.uuid4(),
        "Поминутный",
        None,
        1,
        0,
        now,
        None,
        True,
        billing_mode=BillingMode.PER_MINUTE,
        price_per_minute_cents=0,
    )
    active_package = Entitlement(
        uuid.uuid4(),
        source_session.client_id,
        expired_package.id,
        "vip",
        60,
        15,
        500,
        1,
        EntitlementStatus.ACTIVE,
        f"test-transfer-active-{source_session.id}",
        now,
        activated_at=now,
    )

    packages = PostgresEntitlementRepository(provider)
    await packages.create(active_package)
    account = Client(source_session.client_id, "Player", None, None, 1000, 0, now, now)

    reservation_repo = PostgresReservationRepository(provider)
    booking = ReservationService(reservation_repo, workstations, InMemoryClientRepository())
    conflict = Reservation(
        id=uuid.uuid4(),
        workstation_ids=(target_id,),
        client_id=None,
        guest_name="Другой гость",
        start_at=now - datetime.timedelta(minutes=1),
        end_at=now + datetime.timedelta(minutes=20),
        status=ReservationStatus.CONFIRMED,
        notes=None,
        tariff_id=None,
        created_by="test",
        created_at=now,
    )

    class Portal:
        tariffs = ()

        async def v2_offline_snapshot_for_device(self, client_id, device_id):
            assert client_id == source_session.client_id and device_id == "target"
            return SimpleNamespace(
                client=account,
                tariffs=self.tariffs,
                entitlements=(await packages.get(active_package.id),),
            )

    class Catalog:
        async def get_tariff(self, tariff_id):
            assert tariff_id == expired_package.id
            return expired_package

    portal = Portal()
    targets = V2TransferTargetService(sessions, devices, booking, operations)
    start = V2TransferStartService(sessions, devices, targets, operations, portal, Catalog(), 0)

    chains = PostgresV2SessionChainRepository(provider)
    preparation = V2TransferPreparationService(
        WorkstationService(workstations), operations, V2ClientUpdateReadiness(chains)
    )
    snapshots = PostgresV2SnapshotIssueRepository(provider)
    original_lease = V2SessionLease(
        session_id=source_session.id,
        client_id=account.id,
        device_id="source",
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test",
        issued_at=now,
    )
    initial_payload = snapshots_api.OfflineSessionSnapshotPayload(
        snapshot_id=str(original_lease.snapshot_id),
        schema_version=1,
        snapshot_version=1,
        client_id=str(account.id),
        session_id=str(source_session.id),
        device_id="source",
        policy_version="test",
        login_grant_remaining_minutes=3,
    )
    initial_payload.issued_at.FromDatetime(now)
    signer = V2Ed25519SnapshotSigner("nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A=")
    await snapshots.issue(
        V2SignedSnapshotIssue(
            original_lease, sign_offline_session_snapshot(initial_payload, "test-key", signer)
        )
    )

    bonus_id = uuid.uuid4()
    async with application_transaction(provider) as db:
        db.add(
            V2BonusBudgetModel(
                id=bonus_id,
                client_id=account.id,
                session_id=source_session.id,
                device_id="source",
                snapshot_id=original_lease.snapshot_id,
                snapshot_version=1,
                last_sequence=0,
                last_payload_hash=None,
                idempotency_key=str(bonus_id),
                version=1,
                budget_cents=900,
                spent_cents=220,
                payment_limit_bps=5000,
                issued_at=now,
                active=True,
                cancelled=False,
            )
        )

    class Groups:
        async def get_default(self):
            return SimpleNamespace(active=True, allow_negative_balance=False)

    complete = V2TransferCommitService(
        workstations=devices,
        reservations=booking,
        operations=operations,
        chains=chains,
        snapshots=snapshots,
        start=start,
        portal=portal,
        client_groups=Groups(),
        entitlements=EntitlementService(packages, Catalog(), object()),
        signing_key_id="test-key",
        signer=signer,
        clock=lambda: now,
    )
    tokens = JwtTokenService(Settings(jwt_secret="transfer-test-secret-minimum-32-bytes"))

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
        OfflineSessionGrpcService(
            None,
            tokens,
            transfer_preparation=preparation,
            transfer_start=start,
            transfer_commit=complete,
        ),
        server,
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            client = offline_session_service_pb2_grpc.OfflineSessionServiceStub(channel)
            quote_request = transfer_api.QuoteTransferRequest(
                device_id="source",
                session_id=str(source_session.id),
                target_workstation_id=str(target_id),
            )
            fallback = await client.QuoteTransfer(quote_request, metadata=metadata("source"))
            assert (
                fallback.HasField("fallback_grant_minutes") and fallback.fallback_grant_minutes == 0
            )
            assert not fallback.HasField("per_minute_price_cents")
            assert fallback.burned_package_name == expired_package.name
            assert fallback.burned_package_minutes == 15

            portal.tariffs = (minute_tariff,)
            request = transfer_api.BeginTransferRequest(
                device_id="source",
                session_id=str(source_session.id),
                target_workstation_id=str(target_id),
                operation_id=str(uuid.uuid4()),
                quote_token=fallback.token,
            )
            with pytest.raises(grpc.aio.AioRpcError) as stale_quote:
                await client.BeginTransfer(request, metadata=metadata("source"))
            assert stale_quote.value.code() is grpc.StatusCode.ALREADY_EXISTS

            quote = await client.QuoteTransfer(quote_request, metadata=metadata("source"))
            assert quote.HasField("per_minute_price_cents") and quote.per_minute_price_cents == 0
            assert not quote.HasField("fallback_grant_minutes")
            request.quote_token = quote.token
            first, replay = await asyncio.gather(
                client.BeginTransfer(request, metadata=metadata("source")),
                client.BeginTransfer(request, metadata=metadata("source")),
            )
            assert first == replay
            assert await client.BeginTransfer(request, metadata=metadata("source")) == first
            pending = await client.GetPendingTransfer(
                transfer_api.GetPendingTransferRequest(device_id="target"),
                metadata=metadata("target"),
            )
            assert pending.operation == first
            assert not pending.operation.HasField("source_checkpoint")

            target_request = transfer_api.TransferOperationRequest(
                device_id="target", operation_id=pending.operation.operation_id
            )
            with pytest.raises(grpc.aio.AioRpcError) as forged_device:
                await client.ReadyTransferTarget(target_request, metadata=metadata("source"))
            assert forged_device.value.code() is grpc.StatusCode.PERMISSION_DENIED
            assert (
                await client.ReadyTransferTarget(target_request, metadata=metadata("target"))
            ).target_ready

            submitted = transfer_api.ConfirmTransferSourceRequest(
                device_id="source",
                operation_id=pending.operation.operation_id,
                checkpoint=transfer_api.TransferSourceCheckpoint(sequence=1, payload_hash="a" * 64),
            )
            with pytest.raises(grpc.aio.AioRpcError) as missing_chain:
                await client.ConfirmTransferSource(submitted, metadata=metadata("source"))
            assert missing_chain.value.code() is grpc.StatusCode.ALREADY_EXISTS
            assert await chains.save_if_current(
                V2SessionChain(
                    source_session.client_id,
                    source_session.id,
                    "source",
                    "source",
                    last_sequence=1,
                    last_payload_hash="a" * 64,
                ),
                expected_last_sequence=None,
            )
            confirmed = await client.ConfirmTransferSource(submitted, metadata=metadata("source"))
            assert confirmed.target_ready
            assert confirmed.source_checkpoint == submitted.checkpoint
            assert (
                await client.GetTransferOperation(target_request, metadata=metadata("target"))
                == confirmed
            )
            with pytest.raises(grpc.aio.AioRpcError) as target_cannot_cancel:
                await client.CancelTransfer(target_request, metadata=metadata("target"))
            assert target_cannot_cancel.value.code() is grpc.StatusCode.NOT_FOUND

            cancelled = await client.CancelTransfer(
                transfer_api.TransferOperationRequest(
                    device_id="source", operation_id=confirmed.operation_id
                ),
                metadata=metadata("source"),
            )
            assert cancelled.status == "cancelled"
            assert not (
                await client.GetPendingTransfer(
                    transfer_api.GetPendingTransferRequest(device_id="target"),
                    metadata=metadata("target"),
                )
            ).HasField("operation")
            assert (await packages.get(active_package.id)).status is EntitlementStatus.ACTIVE
            request.operation_id = str(uuid.uuid4())
            await client.BeginTransfer(request, metadata=metadata("source"))
            target_request.operation_id = request.operation_id
            submitted.operation_id = request.operation_id
            await client.ReadyTransferTarget(target_request, metadata=metadata("target"))
            await client.ConfirmTransferSource(submitted, metadata=metadata("source"))
            source_request = transfer_api.TransferOperationRequest(
                device_id="source",
                operation_id=request.operation_id,
            )
            with pytest.raises(grpc.aio.AioRpcError) as before_commit:
                await client.GetTransferredSnapshot(target_request, metadata=metadata("target"))
            assert before_commit.value.code() is grpc.StatusCode.NOT_FOUND

            portal.tariffs = ()
            with pytest.raises(grpc.aio.AioRpcError) as changed_conditions:
                await client.CommitTransfer(source_request, metadata=metadata("source"))
            assert changed_conditions.value.code() is grpc.StatusCode.ALREADY_EXISTS
            assert (await packages.get(active_package.id)).status is EntitlementStatus.ACTIVE
            portal.tariffs = (minute_tariff,)

            async with application_transaction(provider):
                await reservation_repo.save(conflict)
                pending_commit = asyncio.ensure_future(
                    client.CommitTransfer(source_request, metadata=metadata("source"), timeout=5)
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(pending_commit), 0.1)
            with pytest.raises(grpc.aio.AioRpcError) as booked:
                await pending_commit
            assert booked.value.code() is grpc.StatusCode.ALREADY_EXISTS
            assert "entry is no longer allowed" in booked.value.details()
            assert (await sessions.get(source_session.id)).workstation_id == source_id
            assert (await packages.get(active_package.id)).status is EntitlementStatus.ACTIVE
            cancelled_booking = conflict.cancel(now)
            await reservation_repo.save(cancelled_booking)

            async with application_transaction(provider):
                assert (await booking.check_entry_for_transfer(target_id)).allowed
                pending_booking = asyncio.create_task(
                    reservation_repo.save(cancelled_booking), context=contextvars.Context()
                )
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(pending_booking), 0.1)
            await asyncio.wait_for(pending_booking, 3)

            committed = await client.CommitTransfer(source_request, metadata=metadata("source"))
            assert committed.status == "committed"
            recovered_target = await client.GetPendingTransfer(
                transfer_api.GetPendingTransferRequest(device_id="target"),
                metadata=metadata("target"),
            )
            assert recovered_target.operation == committed
            assert (
                await client.CommitTransfer(source_request, metadata=metadata("source"))
                == committed
            )
            assert (await packages.get(active_package.id)).status is EntitlementStatus.BURNED
            assert (await sessions.get(source_session.id)).workstation_id == target_id
            signed = await client.GetTransferredSnapshot(
                target_request, metadata=metadata("target")
            )
            assert signed.payload.device_id == "target"
            assert signed.payload.session_id == str(source_session.id)
            assert signed.payload.login_grant_remaining_minutes == 3
            assert signed.payload.transfer_handoff.last_sequence == 1
            bonus = signed.payload.transfer_handoff.minute_bonus
            assert bonus.grant_id == str(bonus_id) and bonus.remaining_cents == 680
            assert bonus.payment_limit_bps == 5000 and bonus.version == 1
            assert not signed.payload.packages
            assert (
                await client.GetTransferredSnapshot(target_request, metadata=metadata("target"))
                == signed
            )
            with pytest.raises(grpc.aio.AioRpcError) as source_recovery:
                await client.GetTransferredSnapshot(source_request, metadata=metadata("source"))
            assert source_recovery.value.code() is grpc.StatusCode.NOT_FOUND
        async with application_transaction(provider) as db:
            budget = await db.get(V2BonusBudgetModel, bonus_id)
            assert budget.device_id == "target"
            assert budget.snapshot_id == uuid.UUID(signed.payload.snapshot_id)
            assert budget.spent_cents == 220 and budget.budget_cents == 900
    finally:
        await server.stop(None)
        async with provider().begin() as db:
            await db.execute(delete(ReservationModel).where(ReservationModel.id == conflict.id))


async def test_v2_transfer_commits_session_and_confirmed_chain_in_one_transaction(
    admission_context,
):
    provider, _, (source_id, target_id) = admission_context
    sessions = PostgresSessionRepository(provider)
    source = await sessions.save(new_session(source_id, client=True))
    assert source.client_id is not None
    transfers = PostgresV2TransferReservations(provider)
    op = await transfers.prepare(uuid.uuid4(), source.id, source_id, target_id)
    chains = PostgresV2SessionChainRepository(provider)
    initial_chain = V2SessionChain(
        source.client_id,
        source.id,
        "old",
        "workstation:old",
        last_sequence=1,
        last_payload_hash="a" * 64,
    )
    assert await chains.save_if_current(initial_chain, None)
    snapshots = PostgresV2SnapshotIssueRepository(provider)
    original_lease = V2SessionLease(
        session_id=source.id,
        client_id=source.client_id,
        device_id="old",
        snapshot_id=uuid.uuid4(),
        snapshot_version=1,
        policy_version="test",
        issued_at=datetime.datetime.now(datetime.UTC),
    )
    target_lease = dataclasses.replace(
        original_lease, device_id="new", snapshot_id=uuid.uuid4(), snapshot_version=2
    )
    signer = V2Ed25519SnapshotSigner("nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A=")

    def sign(lease, operation=None):
        payload = snapshots_api.OfflineSessionSnapshotPayload(
            snapshot_id=str(lease.snapshot_id),
            schema_version=1,
            snapshot_version=lease.snapshot_version,
            client_id=str(lease.client_id),
            session_id=str(lease.session_id),
            device_id=lease.device_id,
            policy_version=lease.policy_version,
        )
        payload.issued_at.FromDatetime(lease.issued_at)
        if operation is not None:
            payload.transfer_handoff.operation_id = str(operation.operation_id)
            payload.transfer_handoff.last_sequence = operation.source_checkpoint.sequence
            payload.transfer_handoff.last_payload_hash = operation.source_checkpoint.payload_hash
        return V2SignedSnapshotIssue(
            lease, sign_offline_session_snapshot(payload, "test-key", signer)
        )

    await snapshots.issue(sign(original_lease))

    applied_rights = 0

    async def write_rights(operation, session):
        nonlocal applied_rights
        assert session.workstation_id == source_id
        assert operation.source_checkpoint is not None
        await snapshots.transfer_lease(operation, "old", sign(target_lease, operation))
        applied_rights += 1

    async with chains.transfer_transaction(source.id):
        with pytest.raises(ApplicationError, match="devices are not ready"):
            await transfers.commit(op.operation_id, source_id, write_rights)

    await transfers.ready_target(op.operation_id, target_id)
    await transfers.record_source_checkpoint(
        op.operation_id, source_id, V2TransferCheckpoint(1, "a" * 64)
    )

    async def interrupted_write(operation, session):
        await write_rights(operation, session)
        raise RuntimeError("signing failed")

    with pytest.raises(RuntimeError, match="signing failed"):
        async with chains.transfer_transaction(source.id):
            await transfers.commit(op.operation_id, source_id, interrupted_write)
    assert await chains.get(source.id) == initial_chain
    assert await snapshots.has_active_lease(source.id, source.client_id, "old")
    assert not await snapshots.has_active_lease(source.id, source.client_id, "new")
    assert (await sessions.get(source.id)).workstation_id == source_id

    # The canonical chain may advance after the source sent its confirmation.
    advanced_chain = dataclasses.replace(initial_chain, last_sequence=2, last_payload_hash="b" * 64)
    assert await chains.save_if_current(advanced_chain, 1)
    with pytest.raises(ApplicationError, match="checkpoint is no longer current"):
        async with chains.transfer_transaction(source.id):
            await transfers.commit(op.operation_id, source_id, write_rights)
    assert await chains.get(source.id) == advanced_chain
    assert (
        await transfers.get_for_workstation(op.operation_id, target_id)
    ).status is V2TransferStatus.PREPARING
    await transfers.cancel(op.operation_id, source_id)

    op = await transfers.prepare(uuid.uuid4(), source.id, source_id, target_id)
    await transfers.ready_target(op.operation_id, target_id)
    await transfers.record_source_checkpoint(
        op.operation_id, source_id, V2TransferCheckpoint(2, "b" * 64)
    )

    async def commit():
        async with chains.transfer_transaction(source.id):
            return await transfers.commit(op.operation_id, source_id, write_rights)

    first, second = await asyncio.gather(commit(), commit())
    assert first == second and first.status is V2TransferStatus.COMMITTED
    assert applied_rights == 2
    signed = await snapshots.get_transfer_snapshot(first, "new")
    assert signed == sign(target_lease, first).signed_snapshot
    assert signed.payload.transfer_handoff.last_sequence == 2
    assert await snapshots.get_transfer_snapshot(first, "old") is None
    assert not await snapshots.has_active_lease(source.id, source.client_id, "old")
    assert await snapshots.has_active_lease(source.id, source.client_id, "new")
    assert await chains.get(source.id) == dataclasses.replace(
        advanced_chain, device_id="new", producer_id="workstation:new"
    )
    moved = await sessions.get(source.id)
    assert moved == dataclasses.replace(source, workstation_id=target_id)
    with pytest.raises(ApplicationError, match="workstation changed"):
        await sessions.save(source.stop(datetime.datetime.now(datetime.UTC)))
    assert await sessions.get(source.id) == moved


async def test_guest_commit_preserves_receipts_and_does_not_restore_burned_time(admission_context):
    provider, _, (source_id, target_id) = admission_context
    sessions_repo = PostgresSessionRepository(provider)
    payment_id = uuid.uuid4()
    saved = await sessions_repo.save(
        dataclasses.replace(
            new_session(source_id),
            source="guest_local_ledger",
            guest_payment_id=payment_id,
        )
    )
    devices_repo = InMemoryWorkstationRepository()
    await devices_repo.save(Workstation(source_id, "guest-source", "VIP", group_id="vip"))
    await devices_repo.save(Workstation(target_id, "guest-target", "Standard", group_id="standard"))
    devices = WorkstationService(devices_repo)
    await devices.heartbeat("guest-source")
    await devices.heartbeat("guest-target")
    sessions = SessionService(sessions_repo, devices_repo, InMemoryClientRepository())
    grants = PostgresGuestAccessGrantRepository(provider)
    transfers = PostgresV2TransferReservations(provider)
    now = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=2)

    async def issue(minutes, *, extension=False):
        grant_id = uuid.uuid4()
        receipt_id = uuid.uuid4() if extension else payment_id
        payload = snapshots_api.GuestSessionAccessPayload(
            grant_id=str(grant_id),
            payment_id=str(receipt_id),
            session_id=str(saved.id),
            tariff_id="guest-vip",
            tariff_name="VIP",
            workstation_zone_id="vip",
            duration_minutes=minutes,
            tariff_quantity=1,
        )
        payload.issued_at.FromDatetime(now - datetime.timedelta(minutes=2 if not extension else 1))
        await grants.save(
            GuestAccessGrant(
                id=grant_id,
                payment_id=receipt_id,
                workstation_id=source_id,
                expires_at=now + datetime.timedelta(minutes=8),
                session_id=saved.id,
                is_extension=extension,
                payload=payload.SerializeToString(),
                signature=b"paid",
                signing_key_id="original",
            )
        )
        return grant_id

    initial_id = await issue(10)
    queued_id = await issue(20, extension=True)
    waiting_id = uuid.uuid4()
    await grants.save(
        GuestAccessGrant(
            id=waiting_id,
            payment_id=uuid.uuid4(),
            workstation_id=source_id,
            expires_at=now + datetime.timedelta(minutes=8),
            session_id=saved.id,
            is_extension=True,
        )
    )

    booking = ReservationService(
        PostgresReservationRepository(provider), devices_repo, InMemoryClientRepository()
    )
    targets = V2TransferTargetService(sessions, devices, booking, transfers)
    start = V2TransferStartService(
        sessions,
        devices,
        targets,
        transfers,
        None,
        None,
        1,
        clock=lambda: now,
        guest_clock=GuestTransferClock(grants, grants),
    )
    chains = PostgresV2SessionChainRepository(provider)
    snapshots = PostgresV2SnapshotIssueRepository(provider)
    commit = V2TransferCommitService(
        workstations=devices,
        reservations=booking,
        operations=transfers,
        chains=chains,
        snapshots=snapshots,
        start=start,
        portal=None,
        client_groups=None,
        entitlements=None,
        signing_key_id="test",
        signer=V2Ed25519SnapshotSigner("nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A="),
        clock=lambda: now,
        guest_transfers=grants,
        sessions=sessions,
    )

    async def move(device_id, from_id, to_id):
        quote = await start.quote(device_id, saved.id, to_id)
        op = await start.begin(device_id, saved.id, to_id, uuid.uuid4(), quote.token)
        await transfers.ready_target(op.operation_id, to_id)
        await transfers.record_source_checkpoint(
            op.operation_id, from_id, V2TransferCheckpoint(0, None)
        )
        return quote, await commit.commit(device_id, op.operation_id)

    quote, first = await move("guest-source", source_id, target_id)
    assert quote.burned_package_minutes == 8 and quote.fallback_grant_minutes == 1
    assert await commit.commit("guest-source", first.operation_id) == first
    assert first.status is V2TransferStatus.COMMITTED
    snapshot = await commit.get_snapshot("guest-target", first.operation_id)
    assert snapshot.payload.login_grant_remaining_minutes == 1
    assert list(snapshot.payload.transfer_handoff.guest.applied_grant_ids) == [
        str(initial_id),
        str(queued_id),
    ]
    (package,) = snapshot.payload.packages
    assert package.package_id == str(queued_id) and package.remaining_minutes == 20
    assert await grants.get_pending_for_workstation(source_id, now) is None
    waiting = await grants.get_pending_for_workstation(target_id, now, saved.id)
    assert waiting is not None and waiting.id == waiting_id

    quote, second = await move("guest-target", target_id, source_id)
    assert quote.burned_package_id is None
    restored = await commit.get_snapshot("guest-source", second.operation_id)
    assert restored.payload.snapshot_version == 3
    (carried,) = restored.payload.packages
    assert carried.package_id == str(queued_id) and carried.remaining_minutes == 20
    assert await grants.get_pending_for_workstation(source_id, now) is None
    with pytest.raises(ApplicationError, match="access not found"):
        await commit.get_snapshot("guest-target", first.operation_id)


@pytest.mark.parametrize("sale_first", [True, False])
async def test_v2_transfer_and_guest_checkout_cannot_reserve_the_same_target(
    admission_context, sale_first
):
    provider, _, (source_id, target_id) = admission_context
    source = await PostgresSessionRepository(provider).save(new_session(source_id, client=True))
    payments = PostgresGuestSessionPaymentRepository(provider, PostgresSessionTransactionWriter())
    grants = PostgresGuestAccessGrantRepository(provider, payments.release_transfer_hold)

    async def sale_hold(workstation_id, session_id):
        return await payments.has_transfer_hold(workstation_id, session_id) or (
            session_id is None and await grants.has_initial_access_pending(workstation_id)
        )

    transfers = PostgresV2TransferReservations(provider, sale_hold=sale_hold)
    now = datetime.datetime.now(datetime.UTC)
    payment = GuestSessionPayment(
        id=uuid.uuid4(),
        workstation_id=target_id,
        tariff_id=uuid.uuid4(),
        tariff_quantity=1,
        guest_id=None,
        guest_name="Гость",
        total_price_cents=100,
        payment_parts=(PaymentPart("transfer", 100),),
        cash_shift_id=None,
        status=DirectPaymentStatus.PENDING,
        idempotency_key=str(uuid.uuid4()),
        created_at=now,
    )
    entered = asyncio.Event()
    allow_commit = asyncio.Event()

    async def sell():
        async with application_transaction(provider):
            result = await payments.save(payment)
            if sale_first:
                entered.set()
                await allow_commit.wait()
            return result

    async def reserve():
        async with application_transaction(provider):
            result = await transfers.prepare(uuid.uuid4(), source.id, source_id, target_id)
            if not sale_first:
                entered.set()
                await allow_commit.wait()
            return result

    winner_task = asyncio.create_task(sell() if sale_first else reserve())
    await asyncio.wait_for(entered.wait(), timeout=2)
    loser_task = asyncio.create_task(reserve() if sale_first else sell())
    allow_commit.set()
    await winner_task
    with pytest.raises(ApplicationError, match="pending guest sale|pending transfer"):
        await loser_task

    if sale_first:
        assert await payments.has_transfer_hold(target_id, None)
        await payments.save(payment.mark_confirmed(now))
        assert await payments.has_transfer_hold(target_id, None)
        await grants.save(
            GuestAccessGrant(
                id=uuid.uuid4(),
                payment_id=payment.id,
                workstation_id=target_id,
                expires_at=now + datetime.timedelta(minutes=10),
            )
        )
        assert not await payments.has_transfer_hold(target_id, None)
        assert await grants.has_initial_access_pending(target_id)
        with pytest.raises(ApplicationError, match="pending guest sale"):
            await reserve()
        async with provider().begin() as db:
            await db.execute(
                update(GuestAccessGrantModel)
                .where(GuestAccessGrantModel.payment_id == payment.id)
                .values(expires_at=now - datetime.timedelta(seconds=1))
            )
        assert (await reserve()).status is V2TransferStatus.PREPARING
    else:
        assert await payments.get(payment.id) is None
