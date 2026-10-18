import uuid

import pytest

pytestmark = pytest.mark.api


async def test_exact_adjustments_history_and_legacy_top_up(api_context):
    """API сохраняет дробные бонусы, историю и совместимость старого пополнения."""
    api = api_context
    created = await api.client.post(
        "/api/v1/clients", json={"nickname": "Bonus API client"}, headers=api.headers
    )
    client_id = created.json()["id"]
    base = f"/api/v1/clients/{client_id}"
    adjustment = {"amount_cents": 55, "reason": "Manual fractional bonus"}
    headers = {**api.headers, "Idempotency-Key": "bonus-adjust"}
    first = await api.client.post(f"{base}/bonus-adjustments", json=adjustment, headers=headers)
    assert first.status_code == 200
    assert first.json()["wallet_after"] == {
        "total_cents": 55,
        "reserved_cents": 0,
        "available_cents": 55,
    }
    assert first.json()["actor_id"]
    top_up = await api.client.post(
        f"{base}/top-up",
        json={"amount_cents": 0, "bonus_amount": 2, "reason": "Old UI"},
        headers={**api.headers, "Idempotency-Key": "old-topup"},
    )
    assert top_up.status_code == 200
    assert top_up.json()["client"]["balance_bonus"] == 2
    repeated = await api.client.post(f"{base}/bonus-adjustments", json=adjustment, headers=headers)
    assert repeated.json() == first.json()
    changed = await api.client.post(
        f"{base}/bonus-adjustments", json={**adjustment, "amount_cents": 56}, headers=headers
    )
    assert changed.status_code == 409
    wallet = await api.client.get(f"{base}/bonuses", headers=api.headers)
    assert wallet.json() == {
        "total_cents": 255,
        "reserved_cents": 0,
        "available_cents": 255,
        "pending_cents": 0,
    }
    history = await api.client.get(f"{base}/bonus-operations", headers=api.headers)
    assert history.status_code == 200
    assert len(history.json()) == 2
    assert sum(row["total_delta_cents"] for row in history.json()) == 255


@pytest.mark.parametrize("suffix", ["bonuses", "bonus-operations", "bonus-adjustments"])
async def test_bonus_endpoints_require_authentication(api_context, suffix):
    """Бонусные операции и чтение остатков требуют авторизации."""
    path = f"/api/v1/clients/{uuid.uuid4()}/{suffix}"
    if suffix == "bonus-adjustments":
        result = await api_context.client.post(
            path,
            json={"amount_cents": 1, "reason": "Test"},
            headers={"Idempotency-Key": "unauthorized"},
        )
    else:
        result = await api_context.client.get(path)
    assert result.status_code == 401


@pytest.mark.parametrize("amount,status", [(True, 422), (1.5, 422), (0, 400), (-1, 409)])
async def test_invalid_or_unfunded_adjustment_does_not_change_wallet(api_context, amount, status):
    """Некорректная или необеспеченная корректировка не меняет остаток."""
    api = api_context
    created = await api.client.post(
        "/api/v1/clients", json={"nickname": "Bonus validation"}, headers=api.headers
    )
    base = f"/api/v1/clients/{created.json()['id']}"
    result = await api.client.post(
        f"{base}/bonus-adjustments",
        json={"amount_cents": amount, "reason": "Test"},
        headers={**api.headers, "Idempotency-Key": "invalid-bonus"},
    )
    assert result.status_code == status
    assert (await api.client.get(f"{base}/bonuses", headers=api.headers)).json()["total_cents"] == 0
    assert (await api.client.get(f"{base}/bonus-operations", headers=api.headers)).json() == []


async def test_bonus_management_requires_permission(api_context):
    """Авторизованный пользователь без clients.manage не может читать или менять бонусы."""
    from gameclub_backend.config import Settings
    from gameclub_backend.modules.auth.domain import Principal, SubjectType
    from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService

    settings = Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    token, _ = JwtTokenService(settings).issue_access_token(
        Principal(
            subject_id="limited",
            subject_type=SubjectType.OPERATOR,
            roles=frozenset({"operator"}),
            permissions=frozenset({"dashboard.read"}),
        )
    )
    path = f"/api/v1/clients/{uuid.uuid4()}"
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "forbidden"}
    for suffix in ("bonuses", "bonus-operations"):
        assert (
            await api_context.client.get(f"{path}/{suffix}", headers=headers)
        ).status_code == 403
    result = await api_context.client.post(
        f"{path}/bonus-adjustments", json={"amount_cents": 100, "reason": "Test"}, headers=headers
    )
    assert result.status_code == 403


async def test_bonus_adjustment_preserves_reserved_v2_budget(api_context):
    """Корректировка доступна во время V2-игры, но не удаляет уже подписанный резерв."""
    from gameclub_backend.modules.clients.application.bonus import BonusCommand
    from gameclub_backend.modules.clients.bonus import BonusOperationKind
    from gameclub_backend.modules.clients.presentation.http import create_router

    class ActiveLease:
        async def has_active_lease_for_client(self, client_id):
            return True

    api = api_context
    service = api.application.state.clients
    client = await service.create("Active bonus client")
    await service.apply_bonus_operation(
        BonusCommand(client.id, BonusOperationKind.ADJUST, 1000, "owner", "Opening", "opening")
    )
    await service.apply_bonus_operation(
        BonusCommand(
            client.id,
            BonusOperationKind.RESERVE,
            0,
            "owner",
            "Signed budget",
            "budget",
            uuid.uuid4(),
        )
    )
    api.application.include_router(create_router(service, ActiveLease()), prefix="/active-test")
    response = await api.client.post(
        f"/active-test/api/v1/clients/{client.id}/bonus-adjustments",
        json={"amount_cents": 55, "reason": "Test"},
        headers={**api.headers, "Idempotency-Key": "active-correction"},
    )
    assert response.status_code == 200
    denied = await api.client.post(
        f"/active-test/api/v1/clients/{client.id}/bonus-adjustments",
        json={"amount_cents": -56, "reason": "Cannot spend reserved"},
        headers={**api.headers, "Idempotency-Key": "over-reserve"},
    )
    assert denied.status_code == 409
    wallet = await service.get_bonus_wallet(client.id)
    assert (wallet.total_cents, wallet.reserved_cents, wallet.available_cents) == (1055, 1000, 55)
    assert (await service.get(client.id)).balance_cents == 0


async def test_bonus_program_settings_are_persisted_and_retries_are_checked(api_context):
    """API хранит общий выключатель и три процента, проверяя границы и повторный запрос."""
    api = api_context
    original = await api.client.get("/api/v1/bonus-program", headers=api.headers)
    assert original.status_code == 200
    assert original.json() == {
        "enabled": True,
        "game_rate_bps": 500,
        "product_rate_bps": 200,
        "payment_limit_bps": 2000,
    }
    body = {**original.json(), "payment_limit_bps": 10000, "product_rate_bps": 255}
    headers = {**api.headers, "Idempotency-Key": "program-settings"}
    changed = await api.client.put("/api/v1/bonus-program", json=body, headers=headers)
    assert changed.status_code == 200
    assert changed.json() == body
    assert (
        await api.client.put("/api/v1/bonus-program", json=body, headers=headers)
    ).json() == body
    assert (
        await api.client.put(
            "/api/v1/bonus-program", json={**body, "enabled": False}, headers=headers
        )
    ).status_code == 409
    assert (
        await api.client.put(
            "/api/v1/bonus-program", json={**body, "game_rate_bps": 10001}, headers=headers
        )
    ).status_code == 422
    assert (await api.client.get("/api/v1/bonus-program", headers=api.headers)).json() == body


async def test_http_package_quote_and_bonus_payment_use_server_amounts(api_context):
    """Оператор подтверждает серверный расчёт и оплачивает пакет бонусами и депозитом."""
    import datetime

    api = api_context
    catalog = api.application.state.catalog
    tariff = await catalog.create_tariff(
        "Bonus API package",
        None,
        60,
        10_000,
        datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        None,
    )
    created = await api.client.post(
        "/api/v1/clients", json={"nickname": "Bonus package API"}, headers=api.headers
    )
    client_id = created.json()["id"]
    await api.client.post(
        f"/api/v1/clients/{client_id}/top-up",
        json={"amount_cents": 10_000, "bonus_amount": 20, "reason": "Opening"},
        headers={**api.headers, "Idempotency-Key": "opening"},
    )
    base = f"/api/v1/clients/{client_id}/entitlements"
    result = await api.client.post(
        f"{base}/quote", json={"tariff_id": str(tariff.id), "use_bonus": True}, headers=api.headers
    )
    assert result.status_code == 200
    quote = result.json()
    assert (quote["price_cents"], quote["bonus_cents"], quote["money_cents"]) == (10000, 2000, 8000)
    body = {
        "tariff_id": str(tariff.id),
        "use_bonus": True,
        "expected_price_cents": quote["price_cents"],
        "expected_bonus_cents": quote["bonus_cents"],
        "expected_money_cents": quote["money_cents"],
        "expected_earned_bonus_cents": quote["earned_bonus_cents"],
    }
    headers = {**api.headers, "Idempotency-Key": "bonus-package"}
    first = await api.client.post(base, json=body, headers=headers)
    assert first.status_code == 201
    assert first.json()["bonus_amount_cents"] == 2000
    assert first.json()["bonus_requested"] is True
    repeated = await api.client.post(base, json=body, headers=headers)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]
    changed = await api.client.post(base, json={**body, "use_bonus": False}, headers=headers)
    assert changed.status_code == 409
    wallet = await api.client.get(f"/api/v1/clients/{client_id}/bonuses", headers=api.headers)
    assert wallet.json()["available_cents"] == 400
    assert wallet.json()["pending_cents"] == 0
    assert (await api.application.state.clients.get(uuid.UUID(client_id))).balance_cents == 2000
