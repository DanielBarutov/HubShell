"""Аутентифицированный ingress V2 client facts перед Kafka."""

from __future__ import annotations

import asyncio
import typing

from fastapi import APIRouter, Depends, HTTPException, Request, status
from faststream.kafka import KafkaBroker
from google.protobuf.message import DecodeError
from pydantic import BaseModel

from gameclub.v2 import events_pb2
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.presentation.http.auth import get_current_principal

DevicePrincipal = typing.Annotated[Principal, Depends(get_current_principal)]


class ClientFactPublishResponse(BaseModel):
    event_id: str
    operation_id: str
    status: str = "accepted"


class V2ClientFactIngress:
    """Lazily starts one producer and publishes immutable protobuf bytes."""

    def __init__(self, broker: KafkaBroker) -> None:
        self._broker = broker
        self._start_lock = asyncio.Lock()
        self._started = False

    async def publish(self, envelope: events_pb2.EventEnvelope) -> None:
        async with self._start_lock:
            if not self._started:
                await self._broker.start()
                self._started = True
        await self._broker.publish(
            envelope.SerializeToString(),
            topic="v2.client-events",
            key=f"{envelope.client_id}:{envelope.session_id}".encode(),
            correlation_id=envelope.operation_id,
            headers={
                "event_id": envelope.event_id,
                "event_type": str(envelope.event_type),
                "schema_version": str(envelope.schema_version),
                "traceparent": envelope.traceparent,
            },
        )

    async def close(self) -> None:
        if self._started:
            await self._broker.stop()
            self._started = False


def create_v2_client_facts_router() -> APIRouter:
    router = APIRouter(prefix="/api/v2/events", tags=["v2-events"])

    @router.post(
        "/client-facts",
        response_model=ClientFactPublishResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def publish_client_fact(
        request: Request,
        principal: DevicePrincipal,
    ) -> ClientFactPublishResponse:
        if principal.subject_type is not SubjectType.DEVICE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device identity is required",
            )
        ingress: V2ClientFactIngress | None = getattr(
            request.app.state,
            "v2_client_fact_ingress",
            None,
        )
        if ingress is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="V2 event transport is not configured",
            )
        try:
            envelope = events_pb2.EventEnvelope.FromString(await request.body())
        except DecodeError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid V2 event envelope",
            ) from error
        if not envelope.event_id or not envelope.operation_id or not envelope.device_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="V2 event identity is incomplete",
            )
        if envelope.device_id != principal.subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="V2 event belongs to another device",
            )
        if envelope.producer_id != f"workstation:{principal.subject_id}":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="V2 event producer does not match the device",
            )
        await ingress.publish(envelope)
        return ClientFactPublishResponse(
            event_id=envelope.event_id,
            operation_id=envelope.operation_id,
        )

    return router
