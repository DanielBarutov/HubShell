import uuid

import pytest


@pytest.mark.api
async def test_operator_can_top_up_client_in_negative_balance_group_over_http(api_context) -> None:
    """Проверяет, что HTTP-пополнение клиента-должника возвращает успех, а не ошибку 400."""
    group_response = await api_context.client.post(
        "/api/v1/client-groups",
        headers=api_context.headers,
        json={
            "id": "debtors",
            "name": "Должники",
            "allow_negative_balance": True,
            "negative_balance_limit_cents": 60_000,
        },
    )
    assert group_response.status_code == 201
    client_response = await api_context.client.post(
        "/api/v1/clients",
        headers=api_context.headers,
        json={"nickname": "DebtHttpFox", "client_group_id": "debtors"},
    )
    assert client_response.status_code == 201
    client_id = uuid.UUID(client_response.json()["id"])
    debtor, _ = await api_context.application.state.clients.debit(
        client_id,
        60_000,
        "meter",
        "system",
        "debt-http-meter",
        allow_negative_balance=True,
    )
    assert debtor.balance_cents == -60_000

    response = await api_context.client.post(
        f"/api/v1/clients/{client_id}/top-up",
        headers={**api_context.headers, "Idempotency-Key": "debt-http-top-up"},
        json={
            "amount_cents": 10_000,
            "bonus_amount": 0,
            "reason": "Пополнение через оператора",
            "payment_parts": [{"method": "cash", "amount_cents": 10_000}],
        },
    )

    assert response.status_code == 200
    assert response.json()["client"]["balance_cents"] == -50_000
