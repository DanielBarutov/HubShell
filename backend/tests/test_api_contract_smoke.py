from typing import Any

import pytest

pytestmark = pytest.mark.api


async def test_http_reservation_dto_round_trips_through_public_api(
    api_context: Any,
    workstation_payload,
    reservation_payload,
) -> None:
    """
    Проверяет, что минимальные HTTP DTO игрового места и гостевой брони проходят публичный API
    и возвращают обязательные поля транспортного контракта.
    """
    workstation_response = await api_context.client.post(
        "/api/v1/workstations",
        headers=api_context.headers,
        json=workstation_payload(),
    )
    assert workstation_response.status_code == 201
    workstation = workstation_response.json()

    reservation_response = await api_context.client.post(
        "/api/v1/reservations",
        headers={**api_context.headers, "Idempotency-Key": "contract-reservation-001"},
        json=reservation_payload(workstation["id"]),
    )

    assert reservation_response.status_code == 201
    body = reservation_response.json()
    assert {
        "id",
        "workstation_ids",
        "guest_name",
        "start_at",
        "end_at",
        "status",
        "idempotency_key",
    } <= body.keys()
    assert body["workstation_ids"] == [workstation["id"]]
    assert body["guest_name"] == "Contract Guest"
    assert body["status"] == "confirmed"
    assert body["idempotency_key"] == "contract-reservation-001"
