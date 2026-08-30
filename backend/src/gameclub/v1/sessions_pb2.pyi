import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SessionStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SESSION_STATUS_UNSPECIFIED: _ClassVar[SessionStatus]
    SESSION_STATUS_ACTIVE: _ClassVar[SessionStatus]
    SESSION_STATUS_COMPLETED: _ClassVar[SessionStatus]
SESSION_STATUS_UNSPECIFIED: SessionStatus
SESSION_STATUS_ACTIVE: SessionStatus
SESSION_STATUS_COMPLETED: SessionStatus

class Session(_message.Message):
    __slots__ = ("id", "workstation_id", "client_id", "guest_name", "status", "started_at", "ended_at", "source", "created_by", "reservation_id", "idempotency_key", "guest_id", "tariff_id", "tariff_quantity")
    ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    GUEST_NAME_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    ENDED_AT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    CREATED_BY_FIELD_NUMBER: _ClassVar[int]
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    GUEST_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    id: str
    workstation_id: str
    client_id: str
    guest_name: str
    status: SessionStatus
    started_at: _timestamp_pb2.Timestamp
    ended_at: _timestamp_pb2.Timestamp
    source: str
    created_by: str
    reservation_id: str
    idempotency_key: str
    guest_id: str
    tariff_id: str
    tariff_quantity: int
    def __init__(self, id: _Optional[str] = ..., workstation_id: _Optional[str] = ..., client_id: _Optional[str] = ..., guest_name: _Optional[str] = ..., status: _Optional[_Union[SessionStatus, str]] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., ended_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., source: _Optional[str] = ..., created_by: _Optional[str] = ..., reservation_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., guest_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., tariff_quantity: _Optional[int] = ...) -> None: ...

class StartSessionRequest(_message.Message):
    __slots__ = ("workstation_id", "client_id", "guest_name", "source", "reservation_id", "idempotency_key", "device_id", "guest_id", "tariff_id", "tariff_quantity")
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    GUEST_NAME_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    GUEST_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    workstation_id: str
    client_id: str
    guest_name: str
    source: str
    reservation_id: str
    idempotency_key: str
    device_id: str
    guest_id: str
    tariff_id: str
    tariff_quantity: int
    def __init__(self, workstation_id: _Optional[str] = ..., client_id: _Optional[str] = ..., guest_name: _Optional[str] = ..., source: _Optional[str] = ..., reservation_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., device_id: _Optional[str] = ..., guest_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., tariff_quantity: _Optional[int] = ...) -> None: ...

class GetSessionRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class ListSessionsRequest(_message.Message):
    __slots__ = ("workstation_id", "active_only")
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_ONLY_FIELD_NUMBER: _ClassVar[int]
    workstation_id: str
    active_only: bool
    def __init__(self, workstation_id: _Optional[str] = ..., active_only: _Optional[bool] = ...) -> None: ...

class ListSessionsResponse(_message.Message):
    __slots__ = ("sessions",)
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    sessions: _containers.RepeatedCompositeFieldContainer[Session]
    def __init__(self, sessions: _Optional[_Iterable[_Union[Session, _Mapping]]] = ...) -> None: ...

class StopSessionRequest(_message.Message):
    __slots__ = ("session_id", "device_id")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    device_id: str
    def __init__(self, session_id: _Optional[str] = ..., device_id: _Optional[str] = ...) -> None: ...
