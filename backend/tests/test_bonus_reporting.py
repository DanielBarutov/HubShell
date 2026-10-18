import datetime
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.clients.application.bonus import BonusCommand, BonusEarningCommand
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.bonus import BonusOperationKind as Kind
from gameclub_backend.modules.clients.bonus import BonusPolicy, BonusSource
from gameclub_backend.modules.clients.infrastructure.bonus_postgres import BonusBase
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.clients.infrastructure.postgres import (
    ClientBase,
    PostgresClientRepository,
)


@pytest.fixture(
    params=[
        "memory",
        pytest.param("postgres", marks=[pytest.mark.postgres, pytest.mark.integration]),
    ]
)
async def report_repository(request):
    if request.param == "memory":
        yield InMemoryClientRepository()
        return
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN")
    schema = f"bonus_report_{uuid.uuid4().hex}"
    admin = create_async_engine(dsn)
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as connection:
            await connection.run_sync(ClientBase.metadata.create_all)
            await connection.run_sync(BonusBase.metadata.create_all)
        yield PostgresClientRepository(lambda: engine)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def test_report_separates_period_flows_from_current_balances(report_repository):
    """Отчёт отделяет реальные начисления, корректировки, резерв и текущий остаток."""
    start = datetime.datetime(2026, 10, 17, tzinfo=datetime.UTC)
    end = start + datetime.timedelta(minutes=1)

    class Clock:
        value = start

        def now(self):
            return self.value

    clock = Clock()
    service = ClientService(report_repository, clock=clock)
    client = await service.create("Bonus report")
    owner = Principal("owner", SubjectType.OPERATOR, frozenset(), frozenset({"clients.manage"}))
    await service.adjust_bonus(client.id, 200, owner, "Manual", "manual")
    await service.confirm_bonus_earning(
        BonusEarningCommand(
            uuid.uuid4(),
            client.id,
            "sale",
            BonusSource.PRODUCT,
            BonusPolicy(),
            external_paid_cents=1000,
        )
    )
    session = uuid.uuid4()
    for kind, amount in [(Kind.RESERVE, 0), (Kind.CONSUME, 50), (Kind.RELEASE, 0)]:
        await service.apply_bonus_operation(
            BonusCommand(client.id, kind, amount, "owner", "Game", kind.value, session)
        )
    await service.adjust_bonus(client.id, -30, owner, "Correction", "correction")
    clock.value = end
    await service.apply_bonus_operation(
        BonusCommand(client.id, Kind.DEBIT, 20, "owner", "Boundary", "boundary")
    )
    await service.apply_bonus_operation(
        BonusCommand(client.id, Kind.RESERVE, 0, "owner", "Current reserve", "current", session)
    )
    pending_session = uuid.uuid4()
    await service.begin_bonus_session(client.id, pending_session)
    await service.confirm_bonus_earning(
        BonusEarningCommand(
            uuid.uuid4(),
            client.id,
            "pending-game",
            BonusSource.GAME,
            BonusPolicy(),
            external_paid_cents=1000,
            session_id=pending_session,
        )
    )
    report = await service.read_bonus_report(start, end)
    assert report.period.credited_cents == 20
    assert report.period.adjustments_cents == 170
    assert report.period.spent_cents == 50
    assert report.period.reserved_in_cents == 220
    assert report.period.released_cents == 170
    assert report.period.opening_cents == 0
    assert (
        report.total_cents,
        report.available_cents,
        report.reserved_cents,
        report.pending_cents,
    ) == (120, 0, 120, 50)
    assert (
        await service.read_bonus_report(end, end + datetime.timedelta(seconds=1))
    ).period.spent_cents == 20


async def test_report_api_requires_auth_and_valid_dates(api_context):
    """Отчёт требует авторизацию и корректный полуоткрытый период."""
    path = "/api/analytics/bonuses"
    dates = {"start_at": "2026-10-16T00:00:00Z", "end_at": "2026-10-17T00:00:00Z"}
    assert (await api_context.client.get(path, params=dates)).status_code == 401
    response = await api_context.client.get(path, params=dates, headers=api_context.headers)
    assert response.status_code == 200
    assert response.json()["total_cents"] == 0
    for invalid in [
        {**dates, "end_at": dates["start_at"]},
        {**dates, "start_at": "2026-10-16T00:00:00"},
    ]:
        assert (
            await api_context.client.get(path, params=invalid, headers=api_context.headers)
        ).status_code == 422


async def test_legacy_balance_is_read_without_creating_opening_operations(report_repository):
    """Чтение старого остатка не создаёт финансовых операций; перенос не становится наградой."""
    import dataclasses

    service = ClientService(report_repository)
    client = await service.create("Legacy bonus report")
    client = dataclasses.replace(client, id=uuid.uuid4(), balance_bonus=2)
    await report_repository.save(client)
    start = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
    end = datetime.datetime(2100, 1, 1, tzinfo=datetime.UTC)
    assert (await service.read_bonus_report(start, end)).total_cents == 200
    assert await report_repository.list_bonus_operations(client.id) == []
    owner = Principal("owner", SubjectType.OPERATOR, frozenset(), frozenset({"clients.manage"}))
    await service.adjust_bonus(client.id, 1, owner, "Correction", "legacy-correction")
    report = await service.read_bonus_report(start, end)
    assert report.total_cents == 201
    assert report.period.opening_cents == 200
    assert report.period.adjustments_cents == 1
    assert report.period.credited_cents == 0


async def test_report_api_requires_analytics_permission(api_context):
    """Доступ к отчёту требует analytics.read, а не только авторизацию оператора."""
    from gameclub_backend.config import Settings
    from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService

    token, _ = JwtTokenService(
        Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    ).issue_access_token(
        Principal(
            "limited", SubjectType.OPERATOR, frozenset({"operator"}), frozenset({"dashboard.read"})
        )
    )
    result = await api_context.client.get(
        "/api/analytics/bonuses",
        params={"start_at": "2026-10-16T00:00:00Z", "end_at": "2026-10-17T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert result.status_code == 403
