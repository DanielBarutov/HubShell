import datetime
import uuid

import httpx
import pytest
from fastapi import FastAPI

from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.eventing_v2.application.outbox import V2ServerOutboxService
from gameclub_backend.modules.eventing_v2.domain import (
    V2Event,
    V2EventType,
    V2OutgoingServerEvent,
)
from gameclub_backend.modules.eventing_v2.infrastructure.memory import (
    InMemoryV2ServerOutboxRepository,
)
from gameclub_backend.modules.eventing_v2.presentation.server_events_http import (
    create_v2_server_events_router,
)
from gameclub_backend.presentation.http.auth import get_current_principal

pytestmark = pytest.mark.api


@pytest.mark.asyncio
async def test_device_polls_own_server_event_and_acknowledges_it() -> None:
    """Проверяет заявленное поведение backend."""
    service = V2ServerOutboxService(InMemoryV2ServerOutboxRepository())
    event = V2Event.create(
        operation_id=uuid.uuid4(),
        event_type=V2EventType.BALANCE_CREDIT_APPLIED,
        producer_id="server:deposit",
        client_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        device_id="device-01",
        sequence=1,
        occurred_at=datetime.datetime(2026, 9, 29, tzinfo=datetime.UTC),
        payload={
            "amount_delta_cents": 500,
            "currency": "RUB",
            "deposit_operation_id": "00000000-0000-0000-0000-000000000001",
        },
    )
    outgoing = await service.enqueue(
        V2OutgoingServerEvent(
            event=event,
            topic="v2.server-events",
            partition_key="client-session",
            created_at=event.occurred_at,
        )
    )
    await service.mark_published(
        outgoing,
        datetime.datetime(2026, 9, 29, 0, 1, tzinfo=datetime.UTC),
    )

    application = FastAPI()
    application.state.v2_server_events = service
    application.dependency_overrides[get_current_principal] = lambda: Principal(
        subject_id="device-01",
        subject_type=SubjectType.DEVICE,
        roles=frozenset({"device"}),
        permissions=frozenset(),
    )
    application.include_router(create_v2_server_events_router())

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/events/server")
        assert response.status_code == 200
        body = response.json()
        assert len(body["events"]) == 1
        event_id = body["events"][0]["event_id"]

        acknowledged = await client.post(f"/api/events/server/{event_id}/acknowledge")
        assert acknowledged.status_code == 200
        assert acknowledged.json()["status"] == "acknowledged"
        assert (await client.get("/api/events/server")).json()["events"] == []
