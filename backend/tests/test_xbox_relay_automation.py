import asyncio
import datetime
import uuid
from types import SimpleNamespace

import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.direct_payments.application.xbox import XboxService
from test_xbox_places import active_session, sell, xbox_context  # noqa: F401

RELAY = {"ip": "192.168.3.10", "port": 8081, "deviceid": "1001ee63f1"}


class FakeRelay:
    def __init__(self):
        self.calls = []
        self.fail_on = False
        self.fail_off = False
        self.entered = None
        self.release = None

    async def set_state(self, settings, on):
        self.calls.append((settings, on))
        if not on and self.entered is not None:
            self.entered.set()
            await self.release.wait()
        if self.fail_on if on else self.fail_off:
            raise ApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Injected relay failure")
        return "on" if on else "off"


@pytest.fixture
async def automated(xbox_context):  # noqa: F811
    ctx = xbox_context
    result = await ctx.client.put(
        f"/api/v1/workstations/{ctx.place['id']}",
        headers=ctx.headers,
        json={
            "name": ctx.place["name"],
            "group_id": None,
            "position": None,
            "relay_settings": RELAY,
        },
    )
    assert result.status_code == 200, result.text
    ctx.relay = FakeRelay()
    ctx.app.state.xbox._relay = ctx.relay
    return ctx


async def stop(ctx, session_id):
    return await ctx.client.post(f"/api/v1/xbox/sessions/{session_id}/stop", headers=ctx.headers)


async def test_on_failure_has_no_payment_session_or_cash_and_retry_is_once(automated):
    """Отказ ON не сохраняет продажу/деньги; тот же ключ после восстановления безопасен."""
    ctx = automated
    cash = ctx.app.state.cash_shifts
    shift = await cash.open(
        register_id=f"relay-{uuid.uuid4()}",
        opening_balance_cents=0,
        opened_by="operator",
        idempotency_key=str(uuid.uuid4()),
    )
    key = str(uuid.uuid4())
    parts = {
        "cash_shift_id": str(shift.id),
        "payment_parts": [{"method": "cash", "amount_cents": 10000}],
    }
    ctx.relay.fail_on = True
    result = await sell(ctx, key, **parts)
    assert result.status_code == 503, result.text
    assert "включение" in result.text
    assert await ctx.app.state.guest_payments.get_by_idempotency_key(key) is None
    assert (await cash.get(shift.id)).expected_close_cents == 0
    assert not await ctx.app.state.sessions.list(uuid.UUID(ctx.place["id"]), active_only=True)
    ctx.relay.fail_on = False
    first = await sell(ctx, key, **parts)
    assert first.status_code == 200, first.text
    session = await active_session(ctx)
    calls = len(ctx.relay.calls)
    assert (await sell(ctx, key, **parts)).json()["id"] == first.json()["id"]
    assert len(ctx.relay.calls) == calls
    assert (await cash.get(shift.id)).expected_close_cents == 10000
    await stop(ctx, session["id"])
    ctx.relay.fail_on = True
    calls = len(ctx.relay.calls)
    assert (await sell(ctx, key, **parts)).json()["id"] == first.json()["id"]
    assert len(ctx.relay.calls) == calls
    assert not await ctx.app.state.xbox.relay_warnings()


async def test_extension_on_failure_preserves_deadline_and_payment(automated):
    """Неподтверждённый ON при допродаже не продлевает время и не подтверждает оплату."""
    ctx = automated
    assert (await sell(ctx)).status_code == 200
    session = await active_session(ctx)
    key = str(uuid.uuid4())
    ctx.relay.fail_on = True
    assert (await sell(ctx, key, session["id"])).status_code == 503
    assert (await active_session(ctx))["expires_at"] == session["expires_at"]
    assert await ctx.app.state.guest_payments.get_by_idempotency_key(key) is None
    ctx.relay.fail_on = False
    assert (await sell(ctx, key, session["id"])).status_code == 200
    assert (
        len((await ctx.app.state.sessions.get(uuid.UUID(session["id"]))).applied_payment_ids) == 2
    )


async def test_failed_off_completes_and_is_visible_durable_and_retried(automated):
    """Отказ OFF сохраняет завершение и предупреждение; новый сервис повторяет durable OFF."""
    ctx = automated
    key = str(uuid.uuid4())
    payment = await sell(ctx, key)
    session = await active_session(ctx)
    ctx.relay.fail_off = True
    result = await stop(ctx, session["id"])
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed"
    assert result.json()["relay_off_pending"] is True
    ended = result.json()["ended_at"]
    assert (await stop(ctx, session["id"])).json()["ended_at"] == ended
    assert (await sell(ctx, key)).json()["id"] == payment.json()["id"]
    places = await ctx.client.get("/api/v1/workstations", headers=ctx.headers)
    assert next(p for p in places.json() if p["id"] == ctx.place["id"])["relay_off_pending"]
    old = ctx.app.state.xbox
    repository = old._relay_repository
    if ctx.postgres:
        # A fresh adapter has no shared in-process state.
        repository = type(repository)(repository._provider)
    recovered = XboxService(
        old._payments,
        old._sessions,
        old._workstations,
        old._transaction,
        old._clock,
        relay=ctx.relay,
        relay_repository=repository,
    )
    assert any(o.session_id == uuid.UUID(session["id"]) for o in await recovered.relay_warnings())
    ctx.relay.fail_off = False
    assert await recovered.expire() == 0
    assert not any(
        o.session_id == uuid.UUID(session["id"]) for o in await recovered.relay_warnings()
    )
    calls = len(ctx.relay.calls)
    await stop(ctx, session["id"])
    assert len(ctx.relay.calls) == calls
    assert ctx.relay.calls[-1][1] is False


async def test_expire_off_failure_and_recovery_keep_deadline(automated):
    """Истечение завершает по сроку даже без OFF и повторяет выключение после восстановления."""
    ctx = automated
    assert (await sell(ctx)).status_code == 200
    session = await active_session(ctx)
    deadline = datetime.datetime.fromisoformat(session["expires_at"])
    clock = SimpleNamespace(now=lambda: deadline + datetime.timedelta(hours=4))
    ctx.app.state.xbox._clock = ctx.app.state.sessions._clock = clock
    ctx.relay.fail_off = True
    assert await ctx.app.state.xbox.expire() >= 1
    completed = await ctx.app.state.sessions.get(uuid.UUID(session["id"]))
    assert completed.ended_at == deadline
    assert any(o.session_id == completed.id for o in await ctx.app.state.xbox.relay_warnings())
    ctx.relay.fail_off = False
    assert await ctx.app.state.xbox.expire() == 0
    assert not any(o.session_id == completed.id for o in await ctx.app.state.xbox.relay_warnings())


async def test_old_off_and_old_sale_never_switch_new_session(automated):
    """Новый ON отменяет старый OFF; старые stop/продажа и захваченный retry безопасны."""
    ctx = automated
    key = str(uuid.uuid4())
    assert (await sell(ctx, key)).status_code == 200
    old = await active_session(ctx)
    ctx.relay.fail_off = True
    await stop(ctx, old["id"])
    assert (await sell(ctx)).status_code == 200
    new = await active_session(ctx)
    assert new["id"] != old["id"]
    calls = len(ctx.relay.calls)
    ctx.relay.fail_off = False
    await ctx.app.state.xbox._retry_off(uuid.UUID(old["id"]))
    await stop(ctx, old["id"])
    await sell(ctx, key)
    await ctx.app.state.xbox.expire()
    assert len(ctx.relay.calls) == calls
    assert (await active_session(ctx))["id"] == new["id"]


async def test_off_in_flight_serializes_new_on(automated):
    """Новая продажа ждёт выполняющийся OFF и включает реле после него, а не наоборот."""
    ctx = automated
    assert (await sell(ctx)).status_code == 200
    old = await active_session(ctx)
    ctx.relay.entered, ctx.relay.release = asyncio.Event(), asyncio.Event()
    stopping = asyncio.create_task(stop(ctx, old["id"]))
    await asyncio.wait_for(ctx.relay.entered.wait(), 5)
    selling = asyncio.create_task(sell(ctx))
    await asyncio.sleep(0.05)
    assert not selling.done()
    ctx.relay.release.set()
    results = await asyncio.wait_for(asyncio.gather(stopping, selling), 10)
    assert [r.status_code for r in results] == [200, 200]
    assert [on for _, on in ctx.relay.calls] == [True, False, True]


async def test_invalid_sale_never_sends_on(automated):
    """Неверная сумма отклоняется до физического ON."""
    ctx = automated
    result = await sell(ctx, payment_parts=[{"method": "transfer", "amount_cents": 1}])
    assert result.status_code == 400, result.text
    assert not ctx.relay.calls
