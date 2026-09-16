import datetime
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from gameclub_backend.config import Settings
from gameclub_backend.presentation.http.app import create_app


@dataclass
class ApiTestContext:
    """Контекст публичного HTTP API с реальным ASGI transport и операторским токеном."""

    application: FastAPI
    client: httpx.AsyncClient
    headers: dict[str, str]


@pytest.fixture
async def api_context() -> AsyncIterator[ApiTestContext]:
    """Предоставляет изолированный HTTP API контекст с авторизованным оператором."""
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
            token_response.raise_for_status()
            yield ApiTestContext(
                application=application,
                client=client,
                headers={"Authorization": f"Bearer {token_response.json()['access_token']}"},
            )


@pytest.fixture
def workstation_payload() -> Callable[[str], dict[str, Any]]:
    """Формирует стабильный HTTP DTO регистрации игрового места."""
    def factory(device_id: str = "contract-device-01") -> dict[str, Any]:
        return {
            "device_id": device_id,
            "name": "Contract PC",
            "group_id": None,
            "capabilities": ["sessions.v1", "commands.v1"],
        }

    return factory


@pytest.fixture
def reservation_payload() -> Callable[[str], dict[str, Any]]:
    """Формирует стабильный HTTP DTO гостевой брони для контрактного smoke-теста."""
    def factory(workstation_id: str) -> dict[str, Any]:
        start_at = datetime.datetime(2026, 12, 1, 12, tzinfo=datetime.UTC)
        return {
            "workstation_ids": [workstation_id],
            "client_id": None,
            "guest_id": None,
            "guest_name": "Contract Guest",
            "start_at": start_at.isoformat(),
            "end_at": (start_at + datetime.timedelta(hours=1)).isoformat(),
            "notes": "contract smoke",
            "tariff_id": None,
        }

    return factory


@pytest.fixture
def snapshot_contract() -> dict[str, Any]:
    """Описывает общие обязательные поля HTTP и gRPC snapshot DTO."""
    return {
        "schema_version": 1,
        "allowed_actions": ["stop"],
        "login_grant_remaining_minutes": 0,
    }
