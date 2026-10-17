from __future__ import annotations

import dataclasses
import datetime
import json
import uuid

from google.protobuf.message import DecodeError

from gameclub.v2 import events_pb2
from gameclub_backend.modules.eventing_v2.domain import V2Event, V2EventType

_PROTO_EVENT_TYPES = {
    V2EventType.LOGIN_REQUESTED: events_pb2.V2_EVENT_TYPE_LOGIN_REQUESTED,
    V2EventType.LOGIN_SNAPSHOT_ISSUED: events_pb2.V2_EVENT_TYPE_LOGIN_SNAPSHOT_ISSUED,
    V2EventType.LOGIN_GRANT_CONSUMED: events_pb2.V2_EVENT_TYPE_LOGIN_GRANT_CONSUMED,
    V2EventType.LOGIN_GRANT_BURNED: events_pb2.V2_EVENT_TYPE_LOGIN_GRANT_BURNED,
    V2EventType.PACKAGE_PURCHASED: events_pb2.V2_EVENT_TYPE_PACKAGE_PURCHASED,
    V2EventType.PACKAGE_CONSUMED: events_pb2.V2_EVENT_TYPE_PACKAGE_CONSUMED,
    V2EventType.PER_MINUTE_DEBIT: events_pb2.V2_EVENT_TYPE_PER_MINUTE_DEBIT,
    V2EventType.BONUS_PAYMENT_DISABLED: events_pb2.V2_EVENT_TYPE_BONUS_PAYMENT_DISABLED,
    V2EventType.PACKAGE_BURNED: events_pb2.V2_EVENT_TYPE_PACKAGE_BURNED,
    V2EventType.SESSION_STOPPED: events_pb2.V2_EVENT_TYPE_SESSION_STOPPED,
    V2EventType.BALANCE_CREDIT_APPLIED: events_pb2.V2_EVENT_TYPE_BALANCE_CREDIT_APPLIED,
    V2EventType.RECONCILIATION_COMPLETED: events_pb2.V2_EVENT_TYPE_RECONCILIATION_COMPLETED,
}
_DOMAIN_EVENT_TYPES = {value: key for key, value in _PROTO_EVENT_TYPES.items()}


def event_to_protobuf(event: V2Event) -> events_pb2.EventEnvelope:
    """Перевести доменный факт в неизменяемый Protobuf-конверт Kafka."""
    message = events_pb2.EventEnvelope(
        event_id=str(event.event_id),
        operation_id=str(event.operation_id),
        event_type=_PROTO_EVENT_TYPES[event.event_type],
        schema_version=event.schema_version,
        producer_id=event.producer_id,
        client_id=str(event.client_id),
        session_id=str(event.session_id),
        device_id=event.device_id,
        sequence=event.sequence,
        correlation_id=str(event.correlation_id),
        traceparent=event.traceparent,
        payload_hash=event.payload_hash,
        payload_json=event.payload_json,
    )
    message.occurred_at.FromDatetime(event.occurred_at)
    if event.causation_id is not None:
        message.causation_id = str(event.causation_id)
    if event.previous_hash is not None:
        message.previous_hash = event.previous_hash
    return message


def event_from_protobuf(message: events_pb2.EventEnvelope) -> V2Event:
    """Проверить Protobuf-конверт и восстановить доменный факт."""
    event_type = _DOMAIN_EVENT_TYPES.get(message.event_type)
    if event_type is None:
        raise ValueError("V2 protobuf event type is unsupported")
    if not message.HasField("occurred_at"):
        raise ValueError("V2 protobuf occurred at is required")
    try:
        payload = json.loads(message.payload_json)
    except json.JSONDecodeError as error:
        raise ValueError("V2 protobuf payload must contain JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("V2 protobuf payload must be a JSON object")
    event = V2Event.create(
        event_id=_parse_uuid(message.event_id, "event id"),
        operation_id=_parse_uuid(message.operation_id, "operation id"),
        event_type=event_type,
        producer_id=message.producer_id,
        client_id=_parse_uuid(message.client_id, "client id"),
        session_id=_parse_uuid(message.session_id, "session id"),
        device_id=message.device_id,
        sequence=message.sequence,
        occurred_at=message.occurred_at.ToDatetime(tzinfo=datetime.UTC),
        payload=payload,
        previous_hash=message.previous_hash if message.HasField("previous_hash") else None,
        causation_id=(
            _parse_uuid(message.causation_id, "causation id")
            if message.HasField("causation_id")
            else None
        ),
        correlation_id=_parse_uuid(message.correlation_id, "correlation id"),
        traceparent=message.traceparent,
    )
    return dataclasses.replace(event, payload_hash=message.payload_hash)


def event_from_protobuf_bytes(payload: bytes) -> V2Event:
    """Разобрать bytes Kafka, не позволяя ошибке декодирования пройти дальше."""
    message = events_pb2.EventEnvelope()
    try:
        message.ParseFromString(payload)
    except DecodeError as error:
        raise ValueError("V2 Kafka message is not a valid protobuf envelope") from error
    return event_from_protobuf(message)


def _parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise ValueError(f"V2 protobuf {field_name} is invalid") from error
