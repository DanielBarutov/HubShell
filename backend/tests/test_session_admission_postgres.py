"""Real PostgreSQL races between coordinated updates and session admission."""

import asyncio
import contextvars
import dataclasses
import datetime
import os
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.infrastructure.database import application_transaction
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
)
from gameclub_backend.modules.sessions.infrastructure.transfers_postgres import (
    PostgresSessionTransferRepository,
    SessionTransferOfferModel,
)

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
