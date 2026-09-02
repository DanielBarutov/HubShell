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
    __slots__ = ("id", "workstation_id", "client_id", "guest_name", "status", "started_at", "ended_at", "source", "created_by", "reservation_id", "idempotency_key", "guest_id", "tariff_id", "tariff_quantity", "guest_payment_id", "login_grant_minutes", "entitlement_id")
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
    GUEST_PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    LOGIN_GRANT_MINUTES_FIELD_NUMBER: _ClassVar[int]
    ENTITLEMENT_ID_FIELD_NUMBER: _ClassVar[int]
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
    guest_payment_id: str
    login_grant_minutes: int
    entitlement_id: str
    def __init__(self, id: _Optional[str] = ..., workstation_id: _Optional[str] = ..., client_id: _Optional[str] = ..., guest_name: _Optional[str] = ..., status: _Optional[_Union[SessionStatus, str]] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., ended_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., source: _Optional[str] = ..., created_by: _Optional[str] = ..., reservation_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., guest_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., tariff_quantity: _Optional[int] = ..., guest_payment_id: _Optional[str] = ..., login_grant_minutes: _Optional[int] = ..., entitlement_id: _Optional[str] = ...) -> None: ...

class StartSessionRequest(_message.Message):
    __slots__ = ("workstation_id", "client_id", "guest_name", "source", "reservation_id", "idempotency_key", "device_id", "guest_id", "tariff_id", "tariff_quantity", "guest_payment_id", "entitlement_id")
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
    GUEST_PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    ENTITLEMENT_ID_FIELD_NUMBER: _ClassVar[int]
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
    guest_payment_id: str
    entitlement_id: str
    def __init__(self, workstation_id: _Optional[str] = ..., client_id: _Optional[str] = ..., guest_name: _Optional[str] = ..., source: _Optional[str] = ..., reservation_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., device_id: _Optional[str] = ..., guest_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., tariff_quantity: _Optional[int] = ..., guest_payment_id: _Optional[str] = ..., entitlement_id: _Optional[str] = ...) -> None: ...

class GetSessionRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class GetSessionSnapshotRequest(_message.Message):
    __slots__ = ("session_id", "device_id")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    device_id: str
    def __init__(self, session_id: _Optional[str] = ..., device_id: _Optional[str] = ...) -> None: ...

class PackageSnapshot(_message.Message):
    __slots__ = ("id", "tariff_id", "zone_id", "duration_minutes", "remaining_minutes", "queue_position", "status", "window_start_minute", "window_end_minute", "window_timezone")
    ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    REMAINING_MINUTES_FIELD_NUMBER: _ClassVar[int]
    QUEUE_POSITION_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    WINDOW_START_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_END_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    id: str
    tariff_id: str
    zone_id: str
    duration_minutes: int
    remaining_minutes: int
    queue_position: int
    status: str
    window_start_minute: int
    window_end_minute: int
    window_timezone: str
    def __init__(self, id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., zone_id: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., remaining_minutes: _Optional[int] = ..., queue_position: _Optional[int] = ..., status: _Optional[str] = ..., window_start_minute: _Optional[int] = ..., window_end_minute: _Optional[int] = ..., window_timezone: _Optional[str] = ...) -> None: ...

class SessionMeterSnapshot(_message.Message):
    __slots__ = ("session_id", "billed_minutes", "billed_cents", "package_minutes", "active_entitlement_id", "status", "updated_at")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    BILLED_MINUTES_FIELD_NUMBER: _ClassVar[int]
    BILLED_CENTS_FIELD_NUMBER: _ClassVar[int]
    PACKAGE_MINUTES_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_ENTITLEMENT_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    billed_minutes: int
    billed_cents: int
    package_minutes: int
    active_entitlement_id: str
    status: str
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, session_id: _Optional[str] = ..., billed_minutes: _Optional[int] = ..., billed_cents: _Optional[int] = ..., package_minutes: _Optional[int] = ..., active_entitlement_id: _Optional[str] = ..., status: _Optional[str] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SessionSnapshot(_message.Message):
    __slots__ = ("schema_version", "server_time", "session", "workstation_id", "zone_id", "client_id", "balance_cents", "balance_bonus", "active_package", "package_queue", "meter", "allowed_actions", "device_id")
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    SERVER_TIME_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    BALANCE_BONUS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_PACKAGE_FIELD_NUMBER: _ClassVar[int]
    PACKAGE_QUEUE_FIELD_NUMBER: _ClassVar[int]
    METER_FIELD_NUMBER: _ClassVar[int]
    ALLOWED_ACTIONS_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    schema_version: int
    server_time: _timestamp_pb2.Timestamp
    session: Session
    workstation_id: str
    zone_id: str
    client_id: str
    balance_cents: int
    balance_bonus: int
    active_package: PackageSnapshot
    package_queue: _containers.RepeatedCompositeFieldContainer[PackageSnapshot]
    meter: SessionMeterSnapshot
    allowed_actions: _containers.RepeatedScalarFieldContainer[str]
    device_id: str
    def __init__(self, schema_version: _Optional[int] = ..., server_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., session: _Optional[_Union[Session, _Mapping]] = ..., workstation_id: _Optional[str] = ..., zone_id: _Optional[str] = ..., client_id: _Optional[str] = ..., balance_cents: _Optional[int] = ..., balance_bonus: _Optional[int] = ..., active_package: _Optional[_Union[PackageSnapshot, _Mapping]] = ..., package_queue: _Optional[_Iterable[_Union[PackageSnapshot, _Mapping]]] = ..., meter: _Optional[_Union[SessionMeterSnapshot, _Mapping]] = ..., allowed_actions: _Optional[_Iterable[str]] = ..., device_id: _Optional[str] = ...) -> None: ...

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

class CreateTransferOfferRequest(_message.Message):
    __slots__ = ("session_id", "target_workstation_id", "device_id", "idempotency_key")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    target_workstation_id: str
    device_id: str
    idempotency_key: str
    def __init__(self, session_id: _Optional[str] = ..., target_workstation_id: _Optional[str] = ..., device_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class GetTransferOfferRequest(_message.Message):
    __slots__ = ("offer_id", "device_id", "token")
    OFFER_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    offer_id: str
    device_id: str
    token: str
    def __init__(self, offer_id: _Optional[str] = ..., device_id: _Optional[str] = ..., token: _Optional[str] = ...) -> None: ...

class ConfirmTransferRequest(_message.Message):
    __slots__ = ("offer_id", "device_id", "token", "idempotency_key")
    OFFER_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    offer_id: str
    device_id: str
    token: str
    idempotency_key: str
    def __init__(self, offer_id: _Optional[str] = ..., device_id: _Optional[str] = ..., token: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class TransferOffer(_message.Message):
    __slots__ = ("id", "session_id", "client_id", "source_workstation_id", "target_workstation_id", "token", "status", "requires_package_burn", "warning", "created_at", "expires_at", "confirmed_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    REQUIRES_PACKAGE_BURN_FIELD_NUMBER: _ClassVar[int]
    WARNING_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    CONFIRMED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    session_id: str
    client_id: str
    source_workstation_id: str
    target_workstation_id: str
    token: str
    status: str
    requires_package_burn: bool
    warning: str
    created_at: _timestamp_pb2.Timestamp
    expires_at: _timestamp_pb2.Timestamp
    confirmed_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., session_id: _Optional[str] = ..., client_id: _Optional[str] = ..., source_workstation_id: _Optional[str] = ..., target_workstation_id: _Optional[str] = ..., token: _Optional[str] = ..., status: _Optional[str] = ..., requires_package_burn: _Optional[bool] = ..., warning: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., expires_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., confirmed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class TransferResult(_message.Message):
    __slots__ = ("offer", "session")
    OFFER_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    offer: TransferOffer
    session: Session
    def __init__(self, offer: _Optional[_Union[TransferOffer, _Mapping]] = ..., session: _Optional[_Union[Session, _Mapping]] = ...) -> None: ...

class ReplayOfflineBatchRequest(_message.Message):
    __slots__ = ("protocol_version", "device_id", "session_id", "operations")
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATIONS_FIELD_NUMBER: _ClassVar[int]
    protocol_version: int
    device_id: str
    session_id: str
    operations: _containers.RepeatedCompositeFieldContainer[OfflineOperation]
    def __init__(self, protocol_version: _Optional[int] = ..., device_id: _Optional[str] = ..., session_id: _Optional[str] = ..., operations: _Optional[_Iterable[_Union[OfflineOperation, _Mapping]]] = ...) -> None: ...

class OfflineOperation(_message.Message):
    __slots__ = ("id", "sequence", "kind", "payload_json", "snapshot_version", "idempotency_key", "checksum", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_VERSION_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    CHECKSUM_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    sequence: int
    kind: str
    payload_json: str
    snapshot_version: int
    idempotency_key: str
    checksum: str
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., sequence: _Optional[int] = ..., kind: _Optional[str] = ..., payload_json: _Optional[str] = ..., snapshot_version: _Optional[int] = ..., idempotency_key: _Optional[str] = ..., checksum: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class OfflineOperationResult(_message.Message):
    __slots__ = ("operation_id", "sequence", "status", "message", "applied_at")
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    APPLIED_AT_FIELD_NUMBER: _ClassVar[int]
    operation_id: str
    sequence: int
    status: str
    message: str
    applied_at: _timestamp_pb2.Timestamp
    def __init__(self, operation_id: _Optional[str] = ..., sequence: _Optional[int] = ..., status: _Optional[str] = ..., message: _Optional[str] = ..., applied_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ReplayOfflineBatchResponse(_message.Message):
    __slots__ = ("protocol_version", "session_id", "results", "snapshot")
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    protocol_version: int
    session_id: str
    results: _containers.RepeatedCompositeFieldContainer[OfflineOperationResult]
    snapshot: SessionSnapshot
    def __init__(self, protocol_version: _Optional[int] = ..., session_id: _Optional[str] = ..., results: _Optional[_Iterable[_Union[OfflineOperationResult, _Mapping]]] = ..., snapshot: _Optional[_Union[SessionSnapshot, _Mapping]] = ...) -> None: ...
