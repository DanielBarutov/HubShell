import datetime

import httpx
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.presentation.http.app import create_app

pytestmark = pytest.mark.api

async def test_catalog_tariff_listing_filters_by_workstation_group() -> None:
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
            moment = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)
            for name, group_id in (("Global", None), ("VIP", "vip"), ("Main", "main")):
                response = await client.post(
                    "/api/v1/catalog/tariffs",
                    headers=headers,
                    json={
                        "name": name,
                        "group_id": group_id,
                        "duration_minutes": 60,
                        "price_cents": 100,
                        "valid_from": moment.isoformat(),
                    },
                )
                assert response.status_code == 201

            response = await client.get(
                "/api/v1/catalog/tariffs?group_id=VIP",
                headers=headers,
            )

    assert response.status_code == 200
    assert {item["name"] for item in response.json()} == {"Global", "VIP"}


async def test_available_tariffs_filter_audience_and_quote_for_buyer() -> None:
    """
    Проверяет HTTP-контракт server-backed каталога для гостя и зарегистрированного клиента.
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
            moment = datetime.datetime.now(datetime.UTC).replace(second=0, microsecond=0)
            payloads = (
                ("All package", 700, "all"),
                ("Guest package", 500, "guest"),
                ("Registered package", 600, "registered"),
            )
            created: dict[str, str] = {}
            for name, price_cents, audience in payloads:
                response = await client.post(
                    "/api/v1/catalog/tariffs",
                    headers=headers,
                    json={
                        "name": name,
                        "group_id": "vip",
                        "duration_minutes": 60,
                        "price_cents": price_cents,
                        "valid_from": (moment - datetime.timedelta(minutes=1)).isoformat(),
                        "audience": audience,
                    },
                )
                assert response.status_code == 201
                created[name] = response.json()["id"]

            guest_catalog = await client.get(
                "/api/v1/catalog/available-tariffs",
                params={"group_id": "vip", "audience": "guest"},
                headers=headers,
            )
            registered_catalog = await client.get(
                "/api/v1/catalog/available-tariffs",
                params={"group_id": "vip", "audience": "registered"},
                headers=headers,
            )
            guest_quote = await client.post(
                "/api/v1/catalog/quote",
                headers=headers,
                json={
                    "duration_minutes": 60,
                    "group_id": "vip",
                    "moment": moment.isoformat(),
                    "audience": "guest",
                },
            )
            registered_quote = await client.post(
                "/api/v1/catalog/quote",
                headers=headers,
                json={
                    "duration_minutes": 60,
                    "group_id": "vip",
                    "moment": moment.isoformat(),
                    "audience": "registered",
                },
            )

    assert {item["name"] for item in guest_catalog.json()} == {
        "All package",
        "Guest package",
    }
    assert {item["name"] for item in registered_catalog.json()} == {
        "All package",
        "Registered package",
    }
    assert guest_quote.json()["tariff_id"] == created["Guest package"]
    assert guest_quote.json()["price_cents"] == 500
    assert registered_quote.json()["tariff_id"] == created["Registered package"]
    assert registered_quote.json()["price_cents"] == 600
