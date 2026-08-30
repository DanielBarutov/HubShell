import datetime

import httpx

from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.presentation.http.app import create_app


async def test_operator_can_complete_core_api_flow() -> None:
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


async def test_operator_can_move_reservation_through_lifecycle_over_http() -> None:
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


async def test_cash_correction_requires_separate_permission() -> None:
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
    assert len(reset_response.json()["temporary_password"]) >= 8
    assert delete_response.status_code == 204
    assert product_response.status_code == 201
    assert product_response.json()["stock_quantity"] == 12
    assert product_response.json()["cost_price_cents"] == 120
    assert product_update_response.status_code == 200
    assert product_update_response.json()["name"] == "Energy drink XL"
    assert product_delete_response.status_code == 204
