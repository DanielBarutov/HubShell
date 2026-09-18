import datetime

import httpx
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.presentation.http.app import create_app

pytestmark = pytest.mark.api


async def test_workstation_list_includes_snapshot_for_active_session_over_http() -> None:
    """
    Проверяет, что карта мест получает подробные данные активной сессии,
    без которых нельзя показать карточку при наведении на занятое место.
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
            workstation_response = await client.post(
                "/api/v1/workstations",
                headers=headers,
                json={"device_id": "map-hover-device", "name": "Map hover PC"},
            )
            client_response = await client.post(
                "/api/v1/clients",
                headers=headers,
                json={"nickname": "MapHoverFox"},
            )
            session_response = await client.post(
                "/api/v1/sessions",
                headers={**headers, "Idempotency-Key": "map-hover-session"},
                json={
                    "workstation_id": workstation_response.json()["id"],
                    "client_id": client_response.json()["id"],
                },
            )
            list_response = await client.get("/api/v1/workstations", headers=headers)

    assert token_response.status_code == 200
    assert workstation_response.status_code == 201
    assert client_response.status_code == 201
    assert session_response.status_code == 201
    assert list_response.status_code == 200
    workstation = next(
        item
        for item in list_response.json()
        if item["id"] == workstation_response.json()["id"]
    )
    assert workstation["active_session_id"] == session_response.json()["id"]
    assert workstation["session_snapshot"]["session"]["id"] == session_response.json()["id"]
    assert workstation["session_snapshot"]["server_time"]


async def test_operator_can_move_reservation_through_lifecycle_over_http() -> None:
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
            workstation_response = await client.post(
                "/api/v1/workstations",
                headers=headers,
                json={"device_id": "device-lifecycle-http", "name": "PC-01"},
            )
            workstation_id = workstation_response.json()["id"]
            start_at = datetime.datetime(2026, 8, 28, 18, tzinfo=datetime.UTC)
            payload = {
                "workstation_ids": [workstation_id],
                "guest_name": "Lifecycle guest",
                "start_at": start_at.isoformat(),
                "end_at": (start_at + datetime.timedelta(hours=1)).isoformat(),
            }
            reservation_response = await client.post(
                "/api/v1/reservations",
                headers={**headers, "Idempotency-Key": "reservation-lifecycle-001"},
                json=payload,
            )
            reservation_id = reservation_response.json()["id"]
            update_response = await client.patch(
                f"/api/v1/reservations/{reservation_id}",
                headers=headers,
                json={
                    **payload,
                    "guest_name": "Updated lifecycle guest",
                    "notes": "Updated from API",
                },
            )
            activate_response = await client.post(
                f"/api/v1/reservations/{reservation_id}/activate",
                headers=headers,
            )
            complete_response = await client.post(
                f"/api/v1/reservations/{reservation_id}/complete",
                headers=headers,
            )
            no_show_start = datetime.datetime(2026, 8, 26, 18, tzinfo=datetime.UTC)
            no_show_payload = {
                **payload,
                "start_at": no_show_start.isoformat(),
                "end_at": (no_show_start + datetime.timedelta(hours=1)).isoformat(),
            }
            no_show_reservation_response = await client.post(
                "/api/v1/reservations",
                headers={**headers, "Idempotency-Key": "reservation-lifecycle-002"},
                json=no_show_payload,
            )
            no_show_response = await client.post(
                f"/api/v1/reservations/{no_show_reservation_response.json()['id']}/no-show",
                headers=headers,
            )

    assert token_response.status_code == 200
    assert workstation_response.status_code == 201
    assert reservation_response.status_code == 201
    assert update_response.status_code == 200
    assert update_response.json()["guest_name"] == "Updated lifecycle guest"
    assert update_response.json()["notes"] == "Updated from API"
    assert activate_response.status_code == 200
    assert activate_response.json()["status"] == "active"
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"
    assert no_show_reservation_response.status_code == 201
    assert no_show_response.status_code == 200
    assert no_show_response.json()["status"] == "no_show"


async def test_operator_can_start_and_stop_session_over_http() -> None:
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
            workstation_response = await client.post(
                "/api/v1/workstations",
                headers=headers,
                json={"device_id": "device-session-http", "name": "PC-Session"},
            )
            workstation_id = workstation_response.json()["id"]
            payload = {
                "workstation_id": workstation_id,
                "guest_name": "HTTP guest",
                "source": "operator",
            }
            session_response = await client.post(
                "/api/v1/sessions",
                headers={**headers, "Idempotency-Key": "session-http-001"},
                json=payload,
            )
            repeated_response = await client.post(
                "/api/v1/sessions",
                headers={**headers, "Idempotency-Key": "session-http-001"},
                json=payload,
            )
            mismatch_response = await client.post(
                "/api/v1/sessions",
                headers={**headers, "Idempotency-Key": "session-http-001"},
                json={**payload, "guest_name": "Different retry payload"},
            )
            active_response = await client.get(
                "/api/v1/sessions?active_only=true",
                headers=headers,
            )
            stop_response = await client.post(
                f"/api/v1/sessions/{session_response.json()['id']}/stop",
                headers=headers,
            )
            repeated_stop_response = await client.post(
                f"/api/v1/sessions/{session_response.json()['id']}/stop",
                headers=headers,
            )
            second_session_response = await client.post(
                "/api/v1/sessions",
                headers={**headers, "Idempotency-Key": "session-http-002"},
                json=payload,
            )
            interrupt_headers = {**headers, "Idempotency-Key": "interrupt-http-001"}
            interrupt_response = await client.post(
                f"/api/v1/sessions/{second_session_response.json()['id']}/interrupt",
                headers=interrupt_headers,
                json={"reason": "Клиент закончил раньше"},
            )
            repeated_interrupt_response = await client.post(
                f"/api/v1/sessions/{second_session_response.json()['id']}/interrupt",
                headers=interrupt_headers,
                json={"reason": "Клиент закончил раньше"},
            )

    assert token_response.status_code == 200
    assert session_response.status_code == 201
    assert repeated_response.status_code == 201
    assert repeated_response.json()["id"] == session_response.json()["id"]
    assert mismatch_response.status_code == 409
    assert active_response.status_code == 200
    assert len(active_response.json()) == 1
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "completed"
    assert repeated_stop_response.status_code == 200
    assert repeated_stop_response.json()["status"] == "completed"
    assert second_session_response.status_code == 201
    assert interrupt_response.status_code == 200
    assert interrupt_response.json()["status"] == "completed"
    assert repeated_interrupt_response.status_code == 200
    assert repeated_interrupt_response.json()["id"] == interrupt_response.json()["id"]


async def test_operator_can_charge_completed_session_over_http() -> None:
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
            workstation_response = await client.post(
                "/api/v1/workstations",
                headers=headers,
                json={"device_id": "device-billing-http", "name": "Billing PC"},
            )
            client_response = await client.post(
                "/api/v1/clients",
                headers=headers,
                json={"nickname": "BillingHttpFox"},
            )
            client_id = client_response.json()["id"]
            await client.post(
                f"/api/v1/clients/{client_id}/top-up",
                headers={**headers, "Idempotency-Key": "billing-http-deposit"},
                json={"amount_cents": 1_000, "reason": "Test balance"},
            )
            now = datetime.datetime.now(datetime.UTC)
            tariff_response = await client.post(
                "/api/v1/catalog/tariffs",
                headers=headers,
                json={
                    "name": "HTTP billing hour",
                    "duration_minutes": 60,
                    "price_cents": 500,
                    "valid_from": (now - datetime.timedelta(days=1)).isoformat(),
                },
            )
            session_response = await client.post(
                "/api/v1/sessions",
                headers={**headers, "Idempotency-Key": "billing-http-session"},
                json={
                    "workstation_id": workstation_response.json()["id"],
                    "client_id": client_id,
                },
            )
            await client.post(
                f"/api/v1/sessions/{session_response.json()['id']}/stop",
                headers=headers,
            )
            charge_response = await client.post(
                f"/api/v1/billing/sessions/{session_response.json()['id']}/charge",
                headers={**headers, "Idempotency-Key": "billing-http-charge"},
            )
            repeated_response = await client.post(
                f"/api/v1/billing/sessions/{session_response.json()['id']}/charge",
                headers={**headers, "Idempotency-Key": "billing-http-charge"},
            )
            get_response = await client.get(
                f"/api/v1/billing/sessions/{session_response.json()['id']}/charge",
                headers=headers,
            )
            reconciliation_response = await client.get(
                "/api/v1/billing/reconciliation",
                headers=headers,
            )
            revenue_response = await client.get(
                "/api/v1/billing/revenue",
                params={
                    "start_at": (now - datetime.timedelta(days=1)).isoformat(),
                    "end_at": (now + datetime.timedelta(days=1)).isoformat(),
                },
                headers=headers,
            )

    assert token_response.status_code == 200
    assert tariff_response.status_code == 201
    assert charge_response.status_code == 200
    assert charge_response.json()["amount_cents"] == 500
    assert charge_response.json()["client_balance_cents"] == 500
    assert repeated_response.json()["id"] == charge_response.json()["id"]
    assert get_response.status_code == 200
    assert get_response.json()["tariff_id"] == tariff_response.json()["id"]
    assert reconciliation_response.status_code == 200
    assert reconciliation_response.json()[0]["status"] == "completed"
    assert reconciliation_response.json()[0]["charge_id"] == charge_response.json()["id"]
    assert revenue_response.status_code == 200
    assert revenue_response.json()["amount_cents"] == 500
    assert revenue_response.json()["charge_count"] == 1
