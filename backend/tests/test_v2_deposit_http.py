import datetime
import uuid

import httpx
import pytest
from fastapi import FastAPI

from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.clients.presentation.http import create_router
from gameclub_backend.modules.eventing_v2.application.deposit import (
    V2DepositCreditResult,
)

pytestmark = pytest.mark.api


class DepositServiceStub:
    def __init__(self) -> None:
        self.command = None
        self.active_clients: set[uuid.UUID] = set()

    async def has_active_lease_for_client(self, client_id: uuid.UUID) -> bool:
        return client_id in self.active_clients

    async def apply(self, command):
        self.command = command
        return V2DepositCreditResult(
            payment_operation_id=command.payment_operation_id,
            balance_operation_id=uuid.uuid4(),
            client_delivery_event_id=uuid.uuid4(),
            confirmed_domain_event_id=uuid.uuid4(),
            amount_delta_cents=command.amount_delta_cents,
            currency=command.currency,
            accepted_at=datetime.datetime(2026, 9, 27, 23, tzinfo=datetime.UTC),
        )


async def test_operator_v2_deposit_uses_header_key_and_returns_pending_delivery() -> None:
    """Проверяет заявленное поведение backend."""
    clients = ClientService(InMemoryClientRepository())
    client = await clients.create("V2 Deposit Player", None)
    deposits = DepositServiceStub()
    settings = Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    jwt_service = JwtTokenService(settings)
    token, _ = jwt_service.issue_access_token(
        Principal(
            subject_id="operator-42",
            subject_type=SubjectType.OPERATOR,
            roles=frozenset({"operator"}),
            permissions=frozenset({"clients.manage"}),
        )
    )
    application = FastAPI()
    application.state.jwt_service = jwt_service
    application.include_router(create_router(clients, deposits))
    session_id = uuid.uuid4()

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(
            f"/api/v1/clients/{client.id}/v2-deposits",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "operator-v2-credit-001",
            },
            json={
                "session_id": str(session_id),
                "device_id": "v2-deposit-device",
                "amount_cents": 12_500,
                "currency": "rub",
                "reason": "Пополнение у оператора",
                "payment_parts": [{"method": "transfer", "amount_cents": 12_500}],
            },
        )

    assert response.status_code == 200
    assert response.json()["delivery_status"] == "pending_delivery"
    assert deposits.command is not None
    assert deposits.command.client_id == client.id
    assert deposits.command.session_id == session_id
    assert deposits.command.currency == "RUB"
    assert deposits.command.actor_id == "operator-42"
    assert deposits.command.payment_operation_id == uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"gameclub:v2-deposit:{client.id}:operator-v2-credit-001",
    )
