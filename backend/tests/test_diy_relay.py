import json
import os
import uuid
from types import SimpleNamespace

import httpx
import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.config import Settings
from gameclub_backend.modules.workstations.domain_relay import RelaySettings
from gameclub_backend.modules.workstations.infrastructure.cache_redis import (
    RedisWorkstationSnapshotCache,
)
from gameclub_backend.modules.workstations.infrastructure.relay_http import DiyHttpRelayControl
from gameclub_backend.presentation.http.app import create_app

RELAY = {"ip": "192.168.3.10", "port": 8081, "deviceid": "1001ee63f1"}


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "169.254.169.254",
        "8.8.8.8",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "http://192.168.1.2",
        "router.local",
    ],
)
def test_relay_rejects_addresses_outside_private_lan(ip):
    """Конфигурация не позволяет backend обращаться к публичным адресам и служебным интерфейсам."""
    with pytest.raises(ValueError):
        RelaySettings(**{**RELAY, "ip": ip})


@pytest.mark.parametrize("on", [True, False])
async def test_diy_http_sets_explicit_state_and_checks_info(on):
    """Адаптер передаёт deviceid, задаёт ON/OFF и подтверждает состояние отдельным запросом."""
    calls = []
    state = "on" if on else "off"

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"error": 0, "data": {"switch": state}})

    result = await DiyHttpRelayControl(httpx.MockTransport(handler)).set_state(
        RelaySettings(**RELAY), on
    )
    assert result == state
    assert [r.url.path for r in calls] == ["/zeroconf/switch", "/zeroconf/info"]
    assert str(calls[0].url) == "http://192.168.3.10:8081/zeroconf/switch"
    assert json.loads(calls[0].content) == {
        "deviceid": RELAY["deviceid"],
        "data": {"switch": state},
    }
    assert json.loads(calls[1].content) == {"deviceid": RELAY["deviceid"], "data": {}}


@pytest.mark.parametrize(
    "failure", ["error", "redirect", "invalid", "timeout", "mismatch", "oversize"]
)
async def test_diy_failure_is_not_reported_as_confirmed(failure):
    """Ошибка DIY/HTTP, timeout и неподтверждённый выход не считаются успешным тестом."""
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test timeout", request=request)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
        if failure == "error":
            return httpx.Response(200, json={"error": 401})
        if failure == "invalid":
            return httpx.Response(200, text="not json")
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 16385)
        return httpx.Response(200, json={"error": 0, "data": {"switch": "off"}})

    with pytest.raises(ApplicationError) as error:
        await DiyHttpRelayControl(httpx.MockTransport(handler)).set_state(
            RelaySettings(**RELAY), True
        )
    assert error.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert len(calls) == (2 if failure == "mismatch" else 1)


@pytest.fixture(params=["memory", "postgres"])
async def relay_context(request):
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN") if request.param == "postgres" else None
    if request.param == "postgres" and not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN for relay persistence")
    app = create_app(
        Settings(
            postgres_dsn=dsn,
            jwt_secret="test-secret-with-at-least-32-bytes-long",
            dev_operator_username="operator",
            dev_operator_password="password",
        )
    )
    calls = []
    output = {"switch": "off"}

    def handler(request):
        payload = json.loads(request.content)
        calls.append((request.url.path, payload))
        if request.url.path == "/zeroconf/switch":
            output.update(payload["data"])
        return httpx.Response(200, json={"error": 0, "data": output})

    app.state.workstations._relay = DiyHttpRelayControl(httpx.MockTransport(handler))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            token = await client.post(
                "/api/v1/auth/token", json={"username": "operator", "password": "password"}
            )
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
            yield SimpleNamespace(app=app, client=client, headers=headers, calls=calls)


async def test_relay_configuration_persists_preserves_on_old_updates_and_clears(relay_context):
    """Настройки сохраняются без команды, прежний PUT их не стирает, явный null удаляет."""
    ctx = relay_context
    result = await ctx.client.post(
        "/api/v1/workstations",
        headers=ctx.headers,
        json={"equipment_type": "xbox", "name": "Relay Xbox", "relay_settings": RELAY},
    )
    assert result.status_code == 201, result.text
    workstation = result.json()
    place_id = workstation["id"]
    assert workstation["relay_settings"] == RELAY
    assert not ctx.calls
    updated = await ctx.client.put(
        f"/api/v1/workstations/{place_id}",
        headers=ctx.headers,
        json={"name": "Renamed Xbox", "position": 5},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["relay_settings"] == RELAY
    places = await ctx.client.get("/api/v1/workstations", headers=ctx.headers)
    assert next(p for p in places.json() if p["id"] == place_id)["relay_settings"] == RELAY
    place = await ctx.app.state.workstations.get(uuid.UUID(place_id))
    cache = RedisWorkstationSnapshotCache._from_payload(
        RedisWorkstationSnapshotCache._to_payload(place)
    )
    assert cache.relay_settings == RelaySettings(**RELAY)
    for state in ["on", "off"]:
        tested = await ctx.client.post(
            f"/api/v1/workstations/{place_id}/relay/{state}", headers=ctx.headers
        )
        assert tested.status_code == 200, tested.text
        assert tested.json() == {"state": state}
    assert len(ctx.calls) == 4
    sessions = await ctx.client.get(
        "/api/v1/sessions", headers=ctx.headers, params={"workstation_id": place_id}
    )
    assert sessions.json() == []
    audit = await ctx.client.get("/api/v1/audit/events", headers=ctx.headers)
    assert any(
        e["resource_path"] == f"/api/v1/workstations/{place_id}/relay/off"
        and e["outcome"] == "success"
        for e in audit.json()
    )
    removed = await ctx.client.put(
        f"/api/v1/workstations/{place_id}",
        headers=ctx.headers,
        json={"name": "Xbox", "relay_settings": None},
    )
    assert removed.json()["relay_settings"] is None
    blocked = await ctx.client.post(
        f"/api/v1/workstations/{place_id}/relay/on", headers=ctx.headers
    )
    assert blocked.status_code == 409
    assert len(ctx.calls) == 4


async def test_relay_api_rejects_pc_invalid_settings_and_unauthenticated_calls(relay_context):
    """API проверяет тип места, адрес, порт, deviceid и авторизацию до сетевого запроса."""
    ctx = relay_context
    result = await ctx.client.post(
        "/api/v1/workstations",
        headers=ctx.headers,
        json={"name": "PC", "device_id": str(uuid.uuid4()), "relay_settings": RELAY},
    )
    assert result.status_code == 400, result.text
    place = await ctx.client.post(
        "/api/v1/workstations", headers=ctx.headers, json={"equipment_type": "xbox", "name": "Xbox"}
    )
    place_id = place.json()["id"]
    for settings in [
        {**RELAY, "ip": "127.0.0.1"},
        {**RELAY, "port": 0},
        {**RELAY, "deviceid": ""},
        {**RELAY, "deviceid": "x\n"},
    ]:
        invalid = await ctx.client.put(
            f"/api/v1/workstations/{place_id}",
            headers=ctx.headers,
            json={"name": "Xbox", "relay_settings": settings},
        )
        assert invalid.status_code == 422, invalid.text
    unauthenticated = await ctx.client.post(f"/api/v1/workstations/{place_id}/relay/on")
    assert unauthenticated.status_code == 401
    assert not ctx.calls
