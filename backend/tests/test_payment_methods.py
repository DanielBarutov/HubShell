import httpx
import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.config import Settings
from gameclub_backend.modules.payment_methods.application.service import PaymentMethodService
from gameclub_backend.modules.payment_methods.infrastructure.memory import (
    InMemoryPaymentMethodRepository,
)
from gameclub_backend.presentation.http.app import create_app


async def test_payment_method_service_supports_create_update_and_delete() -> None:
    service = PaymentMethodService(InMemoryPaymentMethodRepository())

    method = await service.create(" Terminal ", " Терминал ", sort_order=3)
    assert method.key == "terminal"
    assert method.name == "Терминал"

    updated = await service.update(method.id, "terminal", "Кассовый терминал", active=False)
    assert updated.name == "Кассовый терминал"
    assert updated.active is False
    assert (await service.list()) == [updated]

    await service.delete(method.id)
    assert await service.list() == []


async def test_payment_method_service_rejects_duplicate_key() -> None:
    service = PaymentMethodService(InMemoryPaymentMethodRepository())
    await service.create("cash", "Наличные")

    with pytest.raises(ApplicationError) as error:
        await service.create(" CASH ", "Другие наличные")

    assert error.value.code is ErrorCode.CONFLICT


async def test_payment_method_http_crud_uses_settings_permission() -> None:
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
            created_response = await client.post(
                "/api/v1/payment-methods",
                headers=headers,
                json={"key": "terminal", "name": "Терминал", "active": True, "sort_order": 5},
            )
            method_id = created_response.json()["id"]
            updated_response = await client.put(
                f"/api/v1/payment-methods/{method_id}",
                headers=headers,
                json={
                    "key": "terminal",
                    "name": "Кассовый терминал",
                    "active": False,
                    "sort_order": 1,
                },
            )
            deleted_response = await client.delete(
                f"/api/v1/payment-methods/{method_id}",
                headers=headers,
            )

    assert token_response.status_code == 200
    assert created_response.status_code == 201
    assert updated_response.status_code == 200
    assert updated_response.json()["active"] is False
    assert deleted_response.status_code == 204
