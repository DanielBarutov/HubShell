import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class V2EventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    V2_EVENT_TYPE_UNSPECIFIED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_LOGIN_REQUESTED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_LOGIN_SNAPSHOT_ISSUED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_LOGIN_GRANT_CONSUMED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_PACKAGE_PURCHASED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_PACKAGE_CONSUMED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_PER_MINUTE_DEBIT: _ClassVar[V2EventType]
    V2_EVENT_TYPE_PACKAGE_BURNED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_SESSION_STOPPED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_BALANCE_CREDIT_APPLIED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_RECONCILIATION_COMPLETED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_LOGIN_GRANT_BURNED: _ClassVar[V2EventType]
    V2_EVENT_TYPE_BONUS_PAYMENT_DISABLED: _ClassVar[V2EventType]

class V2EventProcessingStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    V2_EVENT_PROCESSING_STATUS_UNSPECIFIED: _ClassVar[V2EventProcessingStatus]
    V2_EVENT_PROCESSING_STATUS_ACCEPTED: _ClassVar[V2EventProcessingStatus]
    V2_EVENT_PROCESSING_STATUS_DUPLICATE: _ClassVar[V2EventProcessingStatus]
    V2_EVENT_PROCESSING_STATUS_REJECTED: _ClassVar[V2EventProcessingStatus]
    V2_EVENT_PROCESSING_STATUS_NEEDS_REVIEW: _ClassVar[V2EventProcessingStatus]
V2_EVENT_TYPE_UNSPECIFIED: V2EventType
V2_EVENT_TYPE_LOGIN_REQUESTED: V2EventType
V2_EVENT_TYPE_LOGIN_SNAPSHOT_ISSUED: V2EventType
V2_EVENT_TYPE_LOGIN_GRANT_CONSUMED: V2EventType
V2_EVENT_TYPE_PACKAGE_PURCHASED: V2EventType
V2_EVENT_TYPE_PACKAGE_CONSUMED: V2EventType
V2_EVENT_TYPE_PER_MINUTE_DEBIT: V2EventType
V2_EVENT_TYPE_PACKAGE_BURNED: V2EventType
V2_EVENT_TYPE_SESSION_STOPPED: V2EventType
V2_EVENT_TYPE_BALANCE_CREDIT_APPLIED: V2EventType
V2_EVENT_TYPE_RECONCILIATION_COMPLETED: V2EventType
V2_EVENT_TYPE_LOGIN_GRANT_BURNED: V2EventType
V2_EVENT_TYPE_BONUS_PAYMENT_DISABLED: V2EventType
V2_EVENT_PROCESSING_STATUS_UNSPECIFIED: V2EventProcessingStatus
V2_EVENT_PROCESSING_STATUS_ACCEPTED: V2EventProcessingStatus
V2_EVENT_PROCESSING_STATUS_DUPLICATE: V2EventProcessingStatus
V2_EVENT_PROCESSING_STATUS_REJECTED: V2EventProcessingStatus
V2_EVENT_PROCESSING_STATUS_NEEDS_REVIEW: V2EventProcessingStatus

class EventEnvelope(_message.Message):
    __slots__ = ("event_id", "operation_id", "event_type", "schema_version", "producer_id", "client_id", "session_id", "device_id", "sequence", "occurred_at", "causation_id", "correlation_id", "traceparent", "payload_hash", "previous_hash", "payload_json")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    PRODUCER_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    CAUSATION_ID_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    TRACEPARENT_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_HASH_FIELD_NUMBER: _ClassVar[int]
    PREVIOUS_HASH_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    operation_id: str
    event_type: V2EventType
    schema_version: int
    producer_id: str
    client_id: str
    session_id: str
    device_id: str
    sequence: int
    occurred_at: _timestamp_pb2.Timestamp
    causation_id: str
    correlation_id: str
    traceparent: str
    payload_hash: str
    previous_hash: str
    payload_json: str
    def __init__(self, event_id: _Optional[str] = ..., operation_id: _Optional[str] = ..., event_type: _Optional[_Union[V2EventType, str]] = ..., schema_version: _Optional[int] = ..., producer_id: _Optional[str] = ..., client_id: _Optional[str] = ..., session_id: _Optional[str] = ..., device_id: _Optional[str] = ..., sequence: _Optional[int] = ..., occurred_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., causation_id: _Optional[str] = ..., correlation_id: _Optional[str] = ..., traceparent: _Optional[str] = ..., payload_hash: _Optional[str] = ..., previous_hash: _Optional[str] = ..., payload_json: _Optional[str] = ...) -> None: ...

class EventProcessingResult(_message.Message):
    __slots__ = ("event_id", "operation_id", "status", "reason_code", "message", "processed_at")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    REASON_CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    PROCESSED_AT_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    operation_id: str
    status: V2EventProcessingStatus
    reason_code: str
    message: str
    processed_at: _timestamp_pb2.Timestamp
    def __init__(self, event_id: _Optional[str] = ..., operation_id: _Optional[str] = ..., status: _Optional[_Union[V2EventProcessingStatus, str]] = ..., reason_code: _Optional[str] = ..., message: _Optional[str] = ..., processed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
