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
