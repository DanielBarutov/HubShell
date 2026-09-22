import datetime

import httpx
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.presentation.http.app import create_app

pytestmark = pytest.mark.api


async def test_cash_correction_requires_separate_permission() -> None:
    """
    Проверяет поведение публичного API в заявленном сценарии.
    """
    application = create_app(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    async with application.router.lifespan_context(application):
        token, _ = application.state.jwt_service.issue_access_token(
            Principal(
                subject_id="cashier-01",
                subject_type=SubjectType.OPERATOR,
                roles=frozenset({"cashier"}),
                permissions=frozenset({"cashier.read", "cashier.manage"}),
            )
        )
        headers = {"Authorization": f"Bearer {token}"}
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            shift_response = await client.post(
                "/api/v1/cash-shifts",
                headers={**headers, "Idempotency-Key": "cash-open-permission"},
                json={"register_id": "permission-register", "opening_balance_cents": 0},
            )
            correction_response = await client.post(
                f"/api/v1/cash-shifts/{shift_response.json()['id']}/movements",
                headers={**headers, "Idempotency-Key": "cash-correction-permission"},
                json={
                    "direction": "correction",
                    "amount_cents": 10,
                    "reason": "Unauthorized correction",
                },
            )

    assert shift_response.status_code == 201
    assert correction_response.status_code == 403


async def test_operator_can_use_persisted_guest_for_reservation_and_session() -> None:
    """
    Проверяет поведение публичного API в заявленном сценарии.
    """
    application = create_app(
        Settings(
            jwt_secret="test-secret-with-at-least-32-bytes-long",
            dev_operator_username="operator",
            dev_operator_password="password",
        )
    )
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                json={"username": "operator", "password": "password"},
            )
            headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
            guest_response = await client.post(
                "/api/v1/guests",
                headers=headers,
                json={
                    "nickname": "WalkInApiFox",
                    "phone": "+7 (999) 555-44-33",
                    "discount_category": "student",
                },
            )
            guest_id = guest_response.json()["id"]
            search_response = await client.get(
                "/api/v1/guests/search",
                headers=headers,
                params={"q": "wal", "field": "nickname"},
            )
            workstation_response = await client.post(
                "/api/v1/workstations",
                headers=headers,
                json={"device_id": "guest-api-device", "name": "Guest API PC"},
            )
            workstation_id = workstation_response.json()["id"]
            start_at = datetime.datetime(2035, 1, 1, 12, tzinfo=datetime.UTC)
            reservation_response = await client.post(
                "/api/v1/reservations",
                headers={**headers, "Idempotency-Key": "guest-api-reservation"},
                json={
                    "workstation_ids": [workstation_id],
                    "guest_id": guest_id,
                    "start_at": start_at.isoformat(),
                    "end_at": (start_at + datetime.timedelta(hours=1)).isoformat(),
                },
            )
            session_response = await client.post(
                "/api/v1/sessions",
                headers={**headers, "Idempotency-Key": "guest-api-session"},
                json={"workstation_id": workstation_id, "guest_id": guest_id},
            )

    assert token_response.status_code == 200
    assert guest_response.status_code == 201
    assert guest_response.json()["phone"] == "79995554433"
    assert search_response.status_code == 200
    assert search_response.json()[0]["id"] == guest_id
    assert reservation_response.status_code == 201
    assert reservation_response.json()["guest_id"] == guest_id
    assert reservation_response.json()["guest_name"] == "WalkInApiFox"
    assert session_response.status_code == 201
    assert session_response.json()["guest_id"] == guest_id
    assert session_response.json()["guest_name"] == "WalkInApiFox"


async def test_supervisor_approval_guards_cash_correction_and_close_difference() -> None:
    """
    Проверяет поведение публичного API в заявленном сценарии.
    """
    application = create_app(
        Settings(
            jwt_secret="test-secret-with-at-least-32-bytes-long",
            dev_operator_username="operator",
            dev_operator_password="password",
        )
    )
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                json={"username": "operator", "password": "password"},
            )
            headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
            shift_response = await client.post(
                "/api/v1/cash-shifts",
                headers={**headers, "Idempotency-Key": "approval-open-api"},
                json={"register_id": "approval-register", "opening_balance_cents": 100},
            )
            shift_id = shift_response.json()["id"]
            correction_approval = await client.post(
                f"/api/v1/cash-shifts/{shift_id}/approvals",
                headers={**headers, "Idempotency-Key": "approval-correction-api"},
                json={
                    "kind": "correction",
                    "target_key": "approval-correction-movement",
                    "reason": "Supervisor verified the drawer",
                },
            )
            correction_response = await client.post(
                f"/api/v1/cash-shifts/{shift_id}/movements",
                headers={**headers, "Idempotency-Key": "approval-correction-movement"},
                json={
                    "direction": "correction",
                    "amount_cents": -10,
                    "reason": "Corrected count",
                    "approval_id": correction_approval.json()["id"],
                },
            )
            close_approval = await client.post(
                f"/api/v1/cash-shifts/{shift_id}/approvals",
                headers={**headers, "Idempotency-Key": "approval-close-api"},
                json={
                    "kind": "close_difference",
                    "target_key": "approval-close-movement",
                    "reason": "Supervisor verified the final count",
                },
            )
            close_response = await client.post(
                f"/api/v1/cash-shifts/{shift_id}/close",
                headers={**headers, "Idempotency-Key": "approval-close-movement"},
                json={
                    "actual_close_cents": 100,
                    "approval_id": close_approval.json()["id"],
                },
            )

    assert shift_response.status_code == 201
    assert correction_approval.status_code == 201
    assert correction_response.status_code == 201
    assert close_approval.status_code == 201
    assert close_response.status_code == 200
    assert close_response.json()["difference_cents"] == 10


async def test_operator_can_manage_client_password_and_product_inventory() -> None:
    """
    Проверяет поведение публичного API в заявленном сценарии.
    """
    application = create_app(
        Settings(
            jwt_secret="test-secret-with-at-least-32-bytes-long",
            dev_operator_username="operator",
            dev_operator_password="password",
        )
    )
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                json={"username": "operator", "password": "password"},
            )
            headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
            client_response = await client.post(
                "/api/v1/clients",
                headers=headers,
                json={"nickname": "ManageMe", "phone": "89991234567"},
            )
            client_id = client_response.json()["id"]
            update_response = await client.put(
                f"/api/v1/clients/{client_id}",
                headers=headers,
                json={
                    "nickname": "ManagedClient",
                    "phone": "+7 (999) 765-43-21",
                    "discount_category": "vip",
                },
            )
            reset_response = await client.post(
                f"/api/v1/clients/{client_id}/reset-password",
                headers=headers,
            )
            delete_response = await client.delete(
                f"/api/v1/clients/{client_id}",
                headers=headers,
            )
            product_response = await client.post(
                "/api/v1/catalog/products",
                headers=headers,
                json={
                    "name": "Energy drink",
                    "category": "drinks",
                    "price_cents": 250,
                    "cost_price_cents": 120,
                    "stock_quantity": 12,
                },
            )
            product_id = product_response.json()["id"]
            product_update_response = await client.put(
                f"/api/v1/catalog/products/{product_id}",
                headers=headers,
                json={
                    "name": "Energy drink XL",
                    "category": "drinks",
                    "price_cents": 300,
                    "cost_price_cents": 150,
                    "stock_quantity": 8,
                    "active": True,
                },
            )
            product_delete_response = await client.delete(
                f"/api/v1/catalog/products/{product_id}",
                headers=headers,
            )

    assert client_response.status_code == 201
    assert update_response.status_code == 200
    assert update_response.json()["nickname"] == "ManagedClient"
    assert update_response.json()["phone"] == "79997654321"
    assert update_response.json()["discount_category"] == "vip"
    assert reset_response.status_code == 200
    assert reset_response.json() == {"password_reset_required": True}
    assert delete_response.status_code == 204
    assert product_response.status_code == 201
    assert product_response.json()["stock_quantity"] == 12
    assert product_response.json()["cost_price_cents"] == 120
    assert product_update_response.status_code == 200
    assert product_update_response.json()["name"] == "Energy drink XL"
    assert product_delete_response.status_code == 204
