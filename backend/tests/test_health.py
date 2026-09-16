import httpx
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.presentation.http.app import create_app

pytestmark = pytest.mark.api


async def request(application, method: str, path: str, **kwargs):
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)


async def test_live_endpoint() -> None:
    """
    Проверяет сценарий «test_live_endpoint» и подтверждает ожидаемый публичный результат
    согласно соответствующему бизнес-правилу.
    """
    application = create_app(Settings())
    response = await request(application, "GET", "/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_endpoint_without_configured_dependencies() -> None:
    """
    Проверяет сценарий «test_ready_endpoint_without_configured_dependencies» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    application = create_app(Settings())
    response = await request(application, "GET", "/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"configuration": "ok"},
    }
