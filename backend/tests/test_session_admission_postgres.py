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
from gameclub_backend.modules.sessions.domain import Session, SessionStatus
from gameclub_backend.modules.sessions.infrastructure.postgres import (
    PostgresSessionAdmission,
    PostgresSessionRepository,
    PostgresSessionTransactionWriter,
    SessionAdmissionBlockModel,
    SessionModel,
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
                delete(SessionAdmissionBlockModel).where(
                    SessionAdmissionBlockModel.deployment_id == deployment_id
                )
            )
            await transaction.execute(
                delete(SessionModel).where(SessionModel.workstation_id.in_(workstation_ids))
            )
        await engine.dispose()


def new_session(workstation_id: uuid.UUID) -> Session:
    now = datetime.datetime.now(datetime.UTC)
    return Session(
        id=uuid.uuid4(),
        workstation_id=workstation_id,
        client_id=None,
        guest_name="deployment-test",
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


async def test_in_flight_session_commits_before_barrier_can_check(admission_context):
    """Барьер ждёт незавершённую транзакцию входа и обнаруживает её сеанс."""
    provider, deployment_id, ids = admission_context
    started = asyncio.Event()
    gate = PostgresSessionAdmission(provider)

    async def prepare():
        started.set()
        await gate.block(deployment_id, ids)

    async with application_transaction(provider) as transaction:
        await PostgresSessionTransactionWriter().save(transaction, new_session(ids[0]))
        task = asyncio.create_task(prepare(), context=contextvars.Context())
        await started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 0.1)
    with pytest.raises(ApplicationError, match="active session"):
        await asyncio.wait_for(task, 3)


async def test_in_flight_barrier_commits_before_new_session_can_start(admission_context):
    """Новый вход ждёт фиксации барьера и получает отказ."""
    provider, deployment_id, ids = admission_context
    started = asyncio.Event()

    async def start():
        started.set()
        await PostgresSessionRepository(provider).save(new_session(ids[0]))

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
