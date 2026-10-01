"""HTTP polling boundary for V2 server events addressed to a device."""

from __future__ import annotations

import base64
import typing
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.eventing_v2.application.outbox import V2ServerOutboxService
from gameclub_backend.modules.eventing_v2.infrastructure.protobuf import event_to_protobuf
from gameclub_backend.presentation.http.auth import get_current_principal

DevicePrincipal = typing.Annotated[Principal, Depends(get_current_principal)]


class ServerEventResponse(BaseModel):
    """Opaque protobuf envelope returned to the authenticated workstation."""

    event_id: str
    operation_id: str
    topic: str
    payload_base64: str


class ServerEventPollResponse(BaseModel):
    events: list[ServerEventResponse] = Field(default_factory=list)


class ServerEventAcknowledgeResponse(BaseModel):
    event_id: str
    status: str = "acknowledged"


def _require_device(principal: Principal) -> None:
    if principal.subject_type is not SubjectType.DEVICE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device identity is required",
        )


def _service_from_request(request: Request) -> V2ServerOutboxService:
    service: V2ServerOutboxService | None = getattr(
        request.app.state,
        "v2_server_events",
        None,
    )
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="V2 server event transport is not configured",
        )
    return service


def create_v2_server_events_router() -> APIRouter:
    router = APIRouter(prefix="/api/v2/events", tags=["v2-events"])

    @router.get("/server", response_model=ServerEventPollResponse)
    async def poll_server_events(
        request: Request,
        principal: DevicePrincipal,
        limit: int = 100,
    ) -> ServerEventPollResponse:
        _require_device(principal)
        service = _service_from_request(request)
        try:
            events = await service.published_for_device(principal.subject_id, limit)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return ServerEventPollResponse(
            events=[
                ServerEventResponse(
                    event_id=str(outgoing.event.event_id),
                    operation_id=str(outgoing.event.operation_id),
                    topic=outgoing.topic,
                    payload_base64=base64.b64encode(
                        event_to_protobuf(outgoing.event).SerializeToString()
                    ).decode("ascii"),
                )
                for outgoing in events
            ]
        )

    @router.post(
        "/server/{event_id}/acknowledge",
        response_model=ServerEventAcknowledgeResponse,
    )
    async def acknowledge_server_event(
        event_id: str,
        request: Request,
        principal: DevicePrincipal,
    ) -> ServerEventAcknowledgeResponse:
        _require_device(principal)
        try:
            parsed_event_id = uuid.UUID(event_id)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="event_id must be a UUID",
            ) from error
        service = _service_from_request(request)
        outgoing = await service.acknowledge(parsed_event_id, principal.subject_id)
        if outgoing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="V2 server event was not found for this device",
            )
        if outgoing.status.value != "acknowledged":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="V2 server event is not published yet",
            )
        return ServerEventAcknowledgeResponse(event_id=event_id)

    return router
