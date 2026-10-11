import uuid

import httpx
import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.clients.presentation.http import create_router

pytestmark = pytest.mark.api


class ActiveV2LeaseStub:
    async def has_active_lease_for_client(self, client_id: uuid.UUID) -> bool:
        return True

    async def apply(self, command):
        raise AssertionError("Regular top-up must not apply a V2 deposit")


@pytest.mark.asyncio
async def test_regular_top_up_is_rejected_for_a_client_with_an_active_v2_lease() -> None:
    """Не даёт пополнить серверный кошелёк в обход активного V2 ledger."""
    clients = ClientService(InMemoryClientRepository())
    client = await clients.create("V2 Active Deposit")
    settings = Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    jwt_service = JwtTokenService(settings)
    token, _ = jwt_service.issue_access_token(
        Principal(
            subject_id="operator-43",
            subject_type=SubjectType.OPERATOR,
            roles=frozenset({"operator"}),
            permissions=frozenset({"clients.manage"}),
        )
    )
    application = FastAPI()
    application.state.jwt_service = jwt_service
    application.add_exception_handler(
        ApplicationError,
        lambda _request, error: JSONResponse(
            status_code=409,
            content={"message": error.message},
        ),
    )
    application.include_router(create_router(clients, ActiveV2LeaseStub()))

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(
            f"/api/v1/clients/{client.id}/top-up",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "active-v2-regular-top-up",
            },
            json={
                "amount_cents": 200,
                "bonus_amount": 0,
                "reason": "Пополнение через оператора",
                "payment_parts": [{"method": "transfer", "amount_cents": 200}],
            },
        )

    assert response.status_code == 409
    assert "V2-сессия" in response.json()["message"]
    assert (await clients.get(client.id)).balance_cents == 0
