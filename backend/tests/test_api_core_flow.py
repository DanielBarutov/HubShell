import datetime

import httpx
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.presentation.http.app import create_app

pytestmark = pytest.mark.api

async def test_operator_can_complete_core_api_flow() -> None:
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
            group_response = await client.put(
                "/api/v1/workstation-groups/vip",
                headers=headers,
                json={"name": "VIP-зона", "theme": "vip"},
            )
            groups_response = await client.get(
                "/api/v1/workstation-groups",
                headers=headers,
            )
            workstation_response = await client.post(
                "/api/v1/workstations",
                headers=headers,
                json={
                    "device_id": "device-01",
                    "name": "VIP-01",
                    "group_id": "vip",
                    "capabilities": ["theme.v1", "commands.v1", "theme.v1"],
                },
            )
            client_response = await client.post(
                "/api/v1/clients",
                headers=headers,
                json={"nickname": "NightFox", "phone": "+7 (999) 123-45-67"},
            )
            clients_response = await client.get("/api/v1/clients", headers=headers)
            heartbeat_response = await client.post(
                "/api/v1/workstations/heartbeat",
                headers=headers,
                json={"device_id": "device-01", "client_version": "0.1.0"},
            )
            moment = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)
            tariff_response = await client.post(
                "/api/v1/catalog/tariffs",
                headers=headers,
                json={
                    "name": "VIP hour",
                    "group_id": "vip",
                    "duration_minutes": 60,
                    "price_cents": 500,
                    "valid_from": moment.isoformat(),
                },
            )
            draft_tariff_response = await client.post(
                "/api/v1/catalog/tariffs",
                headers=headers,
                json={
                    "name": "Draft tariff",
                    "group_id": "vip",
                    "duration_minutes": 30,
                    "price_cents": 300,
                    "valid_from": moment.isoformat(),
                    "lifecycle": "draft",
                },
            )
            publish_tariff_response = await client.post(
                f"/api/v1/catalog/tariffs/{draft_tariff_response.json()['id']}/publish",
                headers=headers,
            )
            archive_tariff_response = await client.post(
                f"/api/v1/catalog/tariffs/{draft_tariff_response.json()['id']}/archive",
                headers=headers,
            )
            product_response = await client.post(
                "/api/v1/catalog/products",
                headers=headers,
                json={"name": "Coffee", "category": "drinks", "price_cents": 250},
            )
            products_response = await client.get("/api/v1/catalog/products", headers=headers)
            discount_response = await client.post(
                "/api/v1/catalog/discount-rules",
                headers=headers,
                json={
                    "category": "vip",
                    "percent_bps": 1_000,
                    "priority": 1,
                    "valid_from": moment.isoformat(),
                },
            )
            quote_response = await client.post(
                "/api/v1/catalog/quote",
                headers=headers,
                json={
                    "duration_minutes": 60,
                    "group_id": "vip",
                    "moment": moment.isoformat(),
                    "discount_category": "vip",
                },
            )
            tariffs_response = await client.get("/api/v1/catalog/tariffs", headers=headers)
            discount_rules_response = await client.get(
                "/api/v1/catalog/discount-rules",
                headers=headers,
            )
            snapshot_response = await client.get("/api/v1/catalog/snapshot", headers=headers)
            workstation_id = workstation_response.json()["id"]
            client_id = client_response.json()["id"]
            tariff_id = tariff_response.json()["id"]
            command_response = await client.post(
                f"/api/v1/workstations/{workstation_id}/commands",
                headers={**headers, "Idempotency-Key": "command-001"},
                json={
                    "command_type": "display.lock",
                    "payload": {"reason": "operator"},
                },
            )
            repeated_command_response = await client.post(
                f"/api/v1/workstations/{workstation_id}/commands",
                headers={**headers, "Idempotency-Key": "command-001"},
                json={
                    "command_type": "display.lock",
                    "payload": {"reason": "operator"},
                },
            )
            command_status_response = await client.get(
                f"/api/v1/workstations/{workstation_id}/commands/{command_response.json()['id']}",
                headers=headers,
            )
            reservation_response = await client.post(
                "/api/v1/reservations",
                json={
                    "workstation_ids": [workstation_id],
                    "client_id": client_id,
                    "tariff_id": tariff_id,
                    "start_at": moment.isoformat(),
                    "end_at": (moment + datetime.timedelta(hours=1)).isoformat(),
                },
                headers={**headers, "Idempotency-Key": "reservation-001"},
            )
            availability_response = await client.post(
                "/api/v1/reservations/check-availability",
                headers=headers,
                json={
                    "workstation_ids": [workstation_id],
                    "start_at": moment.isoformat(),
                    "end_at": (moment + datetime.timedelta(hours=1)).isoformat(),
                },
            )
            get_reservation_response = await client.get(
                f"/api/v1/reservations/{reservation_response.json()['id']}",
                headers=headers,
            )
            top_up_response = await client.post(
                f"/api/v1/clients/{client_id}/top-up",
                headers={**headers, "Idempotency-Key": "deposit-001"},
                json={"amount_cents": 1_000, "bonus_amount": 100, "reason": "Deposit"},
            )
            cash_shift_response = await client.post(
                "/api/v1/cash-shifts",
                headers={**headers, "Idempotency-Key": "cash-open-001"},
                json={"register_id": "front-desk", "opening_balance_cents": 1_000},
            )
            cash_movement_response = await client.post(
                f"/api/v1/cash-shifts/{cash_shift_response.json()['id']}/movements",
                headers={**headers, "Idempotency-Key": "cash-movement-001"},
                json={
                    "direction": "cash_in",
                    "amount_cents": 500,
                    "reason": "Cash deposit",
                },
            )
            cash_close_response = await client.post(
                f"/api/v1/cash-shifts/{cash_shift_response.json()['id']}/close",
                headers={**headers, "Idempotency-Key": "cash-close-001"},
                json={"actual_close_cents": 1_500},
            )
            operations_response = await client.get(
                f"/api/v1/clients/{client_id}/balance-operations?limit=10",
                headers=headers,
            )
            cancel_response = await client.post(
                f"/api/v1/reservations/{reservation_response.json()['id']}/cancel",
                headers=headers,
            )
            audit_response = await client.get(
                "/api/v1/audit/events?limit=5",
                headers=headers,
            )

    assert token_response.status_code == 200
    assert group_response.status_code == 200
    assert group_response.json()["theme"] == "vip"
    assert groups_response.status_code == 200
    assert groups_response.json()[0]["id"] == "vip"
    assert workstation_response.status_code == 201
    assert workstation_response.json()["theme"] == "vip"
    assert workstation_response.json()["capabilities"] == ["commands.v1", "theme.v1"]
    assert client_response.status_code == 201
    assert clients_response.status_code == 200
    assert clients_response.json()[0]["nickname"] == "NightFox"
    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["theme"] == "vip"
    assert command_response.status_code == 202
    assert repeated_command_response.status_code == 202
    assert repeated_command_response.json()["id"] == command_response.json()["id"]
    assert command_status_response.status_code == 200
    assert command_status_response.json()["status"] == "queued"
    assert command_status_response.json()["expires_at"]
    assert tariff_response.status_code == 201
    assert draft_tariff_response.status_code == 201
    assert draft_tariff_response.json()["lifecycle"] == "draft"
    assert publish_tariff_response.status_code == 200
    assert publish_tariff_response.json()["lifecycle"] == "published"
    assert archive_tariff_response.status_code == 200
    assert archive_tariff_response.json()["lifecycle"] == "archived"
    assert product_response.status_code == 201
    assert products_response.status_code == 200
    assert any(item["id"] == product_response.json()["id"] for item in products_response.json())
    assert tariffs_response.status_code == 200
    assert any(item["id"] == tariff_response.json()["id"] for item in tariffs_response.json())
    assert discount_response.status_code == 201
    assert discount_rules_response.status_code == 200
    assert discount_rules_response.json()[0]["id"] == discount_response.json()["id"]
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["tariffs"][0]["id"] == tariff_response.json()["id"]
    assert snapshot_response.json()["discount_rules"][0]["id"] == discount_response.json()["id"]
    assert quote_response.status_code == 200
    assert quote_response.json()["price_before_discount_cents"] == 500
    assert quote_response.json()["discount_amount_cents"] == 50
    assert quote_response.json()["price_cents"] == 450
    assert reservation_response.status_code == 201
    assert availability_response.status_code == 200
    assert availability_response.json()["available"] is False
    assert availability_response.json()["reason"] == "workstation_reserved"
    assert availability_response.json()["conflicting_reservation_ids"] == [
        reservation_response.json()["id"]
    ]
    assert get_reservation_response.status_code == 200
    assert get_reservation_response.json()["id"] == reservation_response.json()["id"]
    assert top_up_response.status_code == 200
    assert top_up_response.json()["client"]["balance_cents"] == 1_000
    assert cash_shift_response.status_code == 201
    assert cash_movement_response.status_code == 201
    assert cash_movement_response.json()["direction"] == "cash_in"
    assert cash_close_response.status_code == 200
    assert cash_close_response.json()["status"] == "closed"
    assert cash_close_response.json()["expected_close_cents"] == 1_500
    assert operations_response.status_code == 200
    assert operations_response.json()[0]["operation_type"] == "top_up"
    assert operations_response.json()[0]["reason"] == "Deposit"
    assert operations_response.json()[0]["actor_id"] == "dev-operator"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert audit_response.status_code == 200
    assert len(audit_response.json()) <= 5
    assert any(event["resource_path"].endswith("/top-up") for event in audit_response.json())
    audit_events = application.state.audit_repository.events
    assert any(
        event.actor_id == "dev-operator"
        and event.resource_path.endswith("/top-up")
        and event.outcome == "success"
        for event in audit_events
    )
    assert any(
        event.resource_path.endswith("/commands") and event.status_code == 202
        for event in audit_events
    )
