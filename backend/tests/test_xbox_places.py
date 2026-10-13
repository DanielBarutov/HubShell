import asyncio
import datetime
import os
import uuid
from types import SimpleNamespace

import httpx
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.presentation.http.app import create_app


@pytest.fixture(params=["memory", "postgres"])
async def xbox_context(request):
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN") if request.param == "postgres" else None
    if request.param == "postgres" and not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN for real Xbox transactions")
    app = create_app(
        Settings(
            postgres_dsn=dsn,
            jwt_secret="test-secret-with-at-least-32-bytes-long",
            dev_operator_username="operator",
            dev_operator_password="password",
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            token = await client.post(
                "/api/v1/auth/token", json={"username": "operator", "password": "password"}
            )
            token.raise_for_status()
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
            place = await client.post(
                "/api/v1/workstations",
                headers=headers,
                json={"name": f"Xbox-{uuid.uuid4().hex[:8]}", "equipment_type": "xbox"},
            )
            place.raise_for_status()
            tariff = await client.post(
                "/api/v1/catalog/tariffs",
                headers=headers,
                json={
                    "name": "Xbox час",
                    "equipment_type": "xbox",
                    "duration_minutes": 60,
                    "price_cents": 10000,
                    "valid_from": "2026-01-01T00:00:00Z",
                },
            )
            tariff.raise_for_status()
            yield SimpleNamespace(
                app=app,
                client=client,
                headers=headers,
                place=place.json(),
                tariff=tariff.json(),
                postgres=bool(dsn),
            )


async def sell(ctx, key=None, session_id=None, **overrides):
    body = {
        "workstation_id": ctx.place["id"],
        "tariff_id": ctx.tariff["id"],
        "payment_parts": [{"method": "transfer", "amount_cents": 10000}],
    }
    if session_id:
        body["session_id"] = session_id
    body.update(overrides)
    return await ctx.client.post(
        "/api/v1/xbox/sales",
        headers={**ctx.headers, "Idempotency-Key": key or str(uuid.uuid4())},
        json=body,
    )


async def active_session(ctx):
    result = await ctx.client.get(
        "/api/v1/sessions",
        headers=ctx.headers,
        params={"workstation_id": ctx.place["id"], "active_only": "true"},
    )
    result.raise_for_status()
    return result.json()[0]


async def test_xbox_endpoints_require_operator_and_pc_catalog_excludes_xbox(xbox_context):
    """Xbox не продаётся без авторизации и не попадает в тарифы клиента ПК."""
    ctx = xbox_context
    unauthenticated = await ctx.client.post(
        "/api/v1/xbox/sales",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "workstation_id": ctx.place["id"],
            "tariff_id": ctx.tariff["id"],
            "payment_parts": [{"method": "transfer", "amount_cents": 10000}],
        },
    )
    assert unauthenticated.status_code == 401
    available = await ctx.client.get(
        "/api/v1/catalog/available-tariffs", headers=ctx.headers, params={"audience": "guest"}
    )
    assert available.status_code == 200, available.text
    assert all(tariff["equipment_type"] == "pc" for tariff in available.json())


async def test_xbox_sale_extension_and_retry_preserve_one_session(xbox_context):
    """Оплата запускает гостя, повтор не добавляет время, допродажа продлевает тот же сеанс."""
    ctx = xbox_context
    assert ctx.place["device_id"] is None
    assert ctx.place["status"] == "online"
    key = str(uuid.uuid4())
    first = await sell(ctx, key)
    assert first.status_code == 200, first.text
    session = await active_session(ctx)
    assert session["source"] == "xbox"
    assert session["client_id"] is None
    assert session["login_grant_minutes"] == 0
    first_end = datetime.datetime.fromisoformat(session["expires_at"])
    repeated = await sell(ctx, key)
    assert repeated.json()["id"] == first.json()["id"]
    extension_key = str(uuid.uuid4())
    extended = await sell(ctx, extension_key, session["id"])
    assert extended.status_code == 200, extended.text
    assert (await sell(ctx, extension_key, session["id"])).json()["id"] == extended.json()["id"]
    current = await active_session(ctx)
    assert current["id"] == session["id"]
    assert datetime.datetime.fromisoformat(current["expires_at"]) == first_end + datetime.timedelta(
        hours=1
    )
    # Archiving a tariff cannot rewrite the purchased duration or snapshot name.
    await ctx.client.post(
        f"/api/v1/catalog/tariffs/{ctx.tariff['id']}/archive", headers=ctx.headers
    )
    places = await ctx.client.get("/api/v1/workstations", headers=ctx.headers)
    snapshot = next(p for p in places.json() if p["id"] == ctx.place["id"])["session_snapshot"]
    assert snapshot["active_tariff"]["name"] == "Xbox час"
    assert snapshot["active_tariff"]["remaining_minutes"] == 120
    assert snapshot["device_id"] is None


async def test_xbox_concurrent_sales_do_not_collect_second_payment(xbox_context):
    """Две продажи на свободное место дают один сеанс и один подтверждённый платёж."""
    ctx = xbox_context
    results = await asyncio.gather(sell(ctx), sell(ctx))
    assert sorted(r.status_code for r in results) == [200, 409]
    session = await active_session(ctx)
    assert len(await ctx.app.state.sessions.list(workstation_id=uuid.UUID(ctx.place["id"]))) == 1
    if ctx.postgres:
        finance = await ctx.client.get(
            "/api/analytics/finance",
            headers=ctx.headers,
            params={
                "start_at": "2026-01-01T00:00:00Z",
                "end_at": "2027-01-01T00:00:00Z",
                "equipment_type": "xbox",
                "workstation_key": ctx.place["id"],
                "tariff_key": ctx.tariff["id"],
            },
        )
        assert finance.status_code == 200, finance.text
        assert finance.json()["flow"]["payment_received_cents"] == 10000
    assert session["guest_payment_id"] is not None


async def test_xbox_stop_burns_time_without_restart_or_new_payment(xbox_context):
    """Досрочное завершение сжигает время; повтор безопасен и новая допродажа запрещена."""
    ctx = xbox_context
    key = str(uuid.uuid4())
    payment = await sell(ctx, key)
    assert payment.status_code == 200
    session = await active_session(ctx)
    stopped = await ctx.client.post(
        f"/api/v1/xbox/sessions/{session['id']}/stop", headers=ctx.headers
    )
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "completed"
    again = await ctx.client.post(
        f"/api/v1/xbox/sessions/{session['id']}/stop", headers=ctx.headers
    )
    assert again.json()["ended_at"] == stopped.json()["ended_at"]
    assert (await sell(ctx, session_id=session["id"])).status_code == 409
    assert (await sell(ctx, key)).json()["id"] == payment.json()["id"]
    assert not await ctx.app.state.sessions.list(
        workstation_id=uuid.UUID(ctx.place["id"]), active_only=True
    )


async def test_xbox_expiration_uses_saved_deadline_after_downtime(xbox_context):
    """После простоя сервер закрывает сеанс по сохранённому сроку без лишнего времени."""
    ctx = xbox_context
    assert (await sell(ctx)).status_code == 200
    session = await active_session(ctx)
    deadline = datetime.datetime.fromisoformat(session["expires_at"])
    clock = SimpleNamespace(now=lambda: deadline + datetime.timedelta(hours=4))
    ctx.app.state.xbox._clock = clock
    ctx.app.state.sessions._clock = clock
    assert await ctx.app.state.xbox.expire() >= 1
    completed = await ctx.app.state.sessions.get(uuid.UUID(session["id"]))
    assert completed.ended_at == deadline
    assert await ctx.app.state.xbox.expire() == 0


async def test_xbox_rejects_pc_tariffs_balance_device_commands_and_profiles(xbox_context):
    """Сервер отклоняет ПК-тарифы, депозит, профиль гостя и команды ПК на Xbox."""
    ctx = xbox_context
    pc_tariff = await ctx.client.post(
        "/api/v1/catalog/tariffs",
        headers=ctx.headers,
        json={
            "name": "PC общий",
            "duration_minutes": 60,
            "price_cents": 10000,
            "valid_from": "2026-01-01T00:00:00Z",
        },
    )
    assert (await sell(ctx, tariff_id=pc_tariff.json()["id"])).status_code == 409
    assert (
        await sell(ctx, payment_parts=[{"method": "balance", "amount_cents": 10000}])
    ).status_code == 400
    assert (await sell(ctx, guest_id=str(uuid.uuid4()))).status_code == 422
    direct = await ctx.client.post(
        "/api/v1/guest-payments",
        headers={**ctx.headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "workstation_id": ctx.place["id"],
            "tariff_id": ctx.tariff["id"],
            "payment_parts": [{"method": "transfer", "amount_cents": 10000}],
        },
    )
    assert direct.status_code == 409
    start = await ctx.client.post(
        "/api/v1/sessions",
        headers={**ctx.headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"workstation_id": ctx.place["id"], "source": "xbox"},
    )
    assert start.status_code == 409
    command = await ctx.client.post(
        f"/api/v1/workstations/{ctx.place['id']}/commands",
        headers={**ctx.headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"command_type": "display.lock"},
    )
    assert command.status_code == 409


async def test_xbox_rejects_minute_tariff_and_pc_sale_of_xbox_tariff(xbox_context):
    """Поминутный Xbox-тариф и продажа Xbox-времени на ПК отвергаются сервером."""
    ctx = xbox_context
    invalid = await ctx.client.post(
        "/api/v1/catalog/tariffs",
        headers=ctx.headers,
        json={
            "name": "Xbox поминутно",
            "equipment_type": "xbox",
            "duration_minutes": 1,
            "price_cents": 100,
            "billing_mode": "per_minute",
            "price_per_minute_cents": 100,
            "valid_from": "2026-01-01T00:00:00Z",
        },
    )
    assert invalid.status_code == 400
    pc = await ctx.client.post(
        "/api/v1/workstations",
        headers=ctx.headers,
        json={"name": "PC", "device_id": str(uuid.uuid4())},
    )
    assert pc.status_code == 201
    assert (await sell(ctx, workstation_id=pc.json()["id"])).status_code == 409
    direct = await ctx.client.post(
        "/api/v1/guest-payments",
        headers={**ctx.headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "workstation_id": pc.json()["id"],
            "tariff_id": ctx.tariff["id"],
            "payment_parts": [{"method": "transfer", "amount_cents": 10000}],
        },
    )
    assert direct.status_code == 409


async def test_xbox_cash_sale_is_atomic_with_session_and_duplicate(xbox_context, monkeypatch):
    """PostgreSQL откатывает наличную оплату при сбое сессии; повтор даёт один приход."""
    ctx = xbox_context
    if not ctx.postgres:
        pytest.skip("Transaction rollback requires PostgreSQL")
    cash = ctx.app.state.cash_shifts
    shift = await cash.open(
        register_id=f"xbox-{uuid.uuid4()}",
        opening_balance_cents=0,
        opened_by="operator",
        idempotency_key=str(uuid.uuid4()),
    )
    original = ctx.app.state.sessions.apply_xbox_payment

    async def failed_session(payment):
        raise RuntimeError("Injected session persistence failure")

    monkeypatch.setattr(ctx.app.state.sessions, "apply_xbox_payment", failed_session)
    key = str(uuid.uuid4())
    with pytest.raises(RuntimeError, match="Injected"):
        await sell(
            ctx,
            key,
            cash_shift_id=str(shift.id),
            payment_parts=[{"method": "cash", "amount_cents": 10000}],
        )
    assert await ctx.app.state.guest_payments.get_by_idempotency_key(key) is None
    assert (await cash.get(shift.id)).expected_close_cents == 0
    assert not await ctx.app.state.sessions.list(
        workstation_id=uuid.UUID(ctx.place["id"]), active_only=True
    )
    monkeypatch.setattr(ctx.app.state.sessions, "apply_xbox_payment", original)
    first = await sell(
        ctx,
        key,
        cash_shift_id=str(shift.id),
        payment_parts=[{"method": "cash", "amount_cents": 10000}],
    )
    assert first.status_code == 200, first.text
    repeated = await sell(
        ctx,
        key,
        cash_shift_id=str(shift.id),
        payment_parts=[{"method": "cash", "amount_cents": 10000}],
    )
    assert repeated.json()["id"] == first.json()["id"]
    assert (await cash.get(shift.id)).expected_close_cents == 10000


async def test_xbox_extension_and_expiration_race_cannot_resurrect_session(xbox_context):
    """Допродажа одновременно с закрытием не возобновляет завершённую сессию."""
    ctx = xbox_context
    assert (await sell(ctx)).status_code == 200
    session = await active_session(ctx)
    stop, extend = await asyncio.gather(
        ctx.client.post(f"/api/v1/xbox/sessions/{session['id']}/stop", headers=ctx.headers),
        sell(ctx, session_id=session["id"]),
    )
    assert stop.status_code == 200
    assert extend.status_code in {200, 409}
    result = await ctx.app.state.sessions.get(uuid.UUID(session["id"]))
    assert result.status.value == "completed"
    assert not await ctx.app.state.sessions.list(
        workstation_id=uuid.UUID(ctx.place["id"]), active_only=True
    )
