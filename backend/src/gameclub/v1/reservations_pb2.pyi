import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ReservationStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RESERVATION_STATUS_UNSPECIFIED: _ClassVar[ReservationStatus]
    RESERVATION_STATUS_CONFIRMED: _ClassVar[ReservationStatus]
    RESERVATION_STATUS_ACTIVE: _ClassVar[ReservationStatus]
    RESERVATION_STATUS_COMPLETED: _ClassVar[ReservationStatus]
    RESERVATION_STATUS_CANCELLED: _ClassVar[ReservationStatus]
    RESERVATION_STATUS_NO_SHOW: _ClassVar[ReservationStatus]
RESERVATION_STATUS_UNSPECIFIED: ReservationStatus
RESERVATION_STATUS_CONFIRMED: ReservationStatus
RESERVATION_STATUS_ACTIVE: ReservationStatus
RESERVATION_STATUS_COMPLETED: ReservationStatus
RESERVATION_STATUS_CANCELLED: ReservationStatus
RESERVATION_STATUS_NO_SHOW: ReservationStatus

class Reservation(_message.Message):
    __slots__ = ("id", "workstation_ids", "client_id", "guest_name", "start_at", "end_at", "status", "notes", "tariff_id", "created_by", "created_at", "cancelled_at", "guest_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_IDS_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    GUEST_NAME_FIELD_NUMBER: _ClassVar[int]
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_BY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    CANCELLED_AT_FIELD_NUMBER: _ClassVar[int]
    GUEST_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    workstation_ids: _containers.RepeatedScalarFieldContainer[str]
    client_id: str
    guest_name: str
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    status: ReservationStatus
    notes: str
    tariff_id: str
    created_by: str
    created_at: _timestamp_pb2.Timestamp
    cancelled_at: _timestamp_pb2.Timestamp
    guest_id: str
    def __init__(self, id: _Optional[str] = ..., workstation_ids: _Optional[_Iterable[str]] = ..., client_id: _Optional[str] = ..., guest_name: _Optional[str] = ..., start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., status: _Optional[_Union[ReservationStatus, str]] = ..., notes: _Optional[str] = ..., tariff_id: _Optional[str] = ..., created_by: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., cancelled_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., guest_id: _Optional[str] = ...) -> None: ...

class CheckAvailabilityRequest(_message.Message):
    __slots__ = ("workstation_ids", "start_at", "end_at")
    WORKSTATION_IDS_FIELD_NUMBER: _ClassVar[int]
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    workstation_ids: _containers.RepeatedScalarFieldContainer[str]
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    def __init__(self, workstation_ids: _Optional[_Iterable[str]] = ..., start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CheckAvailabilityResponse(_message.Message):
    __slots__ = ("available", "conflicting_reservation_ids", "reason")
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    CONFLICTING_RESERVATION_IDS_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    available: bool
    conflicting_reservation_ids: _containers.RepeatedScalarFieldContainer[str]
    reason: str
    def __init__(self, available: _Optional[bool] = ..., conflicting_reservation_ids: _Optional[_Iterable[str]] = ..., reason: _Optional[str] = ...) -> None: ...

class CreateReservationRequest(_message.Message):
    __slots__ = ("workstation_ids", "client_id", "guest_name", "start_at", "end_at", "notes", "tariff_id", "idempotency_key", "guest_id")
    WORKSTATION_IDS_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    GUEST_NAME_FIELD_NUMBER: _ClassVar[int]
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    GUEST_ID_FIELD_NUMBER: _ClassVar[int]
    workstation_ids: _containers.RepeatedScalarFieldContainer[str]
    client_id: str
    guest_name: str
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    notes: str
    tariff_id: str
    idempotency_key: str
    guest_id: str
    def __init__(self, workstation_ids: _Optional[_Iterable[str]] = ..., client_id: _Optional[str] = ..., guest_name: _Optional[str] = ..., start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., notes: _Optional[str] = ..., tariff_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., guest_id: _Optional[str] = ...) -> None: ...

class ListReservationsRequest(_message.Message):
    __slots__ = ("start_at", "end_at")
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    def __init__(self, start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ListReservationsResponse(_message.Message):
    __slots__ = ("reservations",)
    RESERVATIONS_FIELD_NUMBER: _ClassVar[int]
    reservations: _containers.RepeatedCompositeFieldContainer[Reservation]
    def __init__(self, reservations: _Optional[_Iterable[_Union[Reservation, _Mapping]]] = ...) -> None: ...

class GetReservationRequest(_message.Message):
    __slots__ = ("reservation_id",)
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    def __init__(self, reservation_id: _Optional[str] = ...) -> None: ...

class UpdateReservationRequest(_message.Message):
    __slots__ = ("reservation_id", "workstation_ids", "client_id", "guest_name", "start_at", "end_at", "notes", "tariff_id", "guest_id")
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_IDS_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    GUEST_NAME_FIELD_NUMBER: _ClassVar[int]
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    NOTES_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    GUEST_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    workstation_ids: _containers.RepeatedScalarFieldContainer[str]
    client_id: str
    guest_name: str
    start_at: _timestamp_pb2.Timestamp
    end_at: _timestamp_pb2.Timestamp
    notes: str
    tariff_id: str
    guest_id: str
    def __init__(self, reservation_id: _Optional[str] = ..., workstation_ids: _Optional[_Iterable[str]] = ..., client_id: _Optional[str] = ..., guest_name: _Optional[str] = ..., start_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., notes: _Optional[str] = ..., tariff_id: _Optional[str] = ..., guest_id: _Optional[str] = ...) -> None: ...

class CancelReservationRequest(_message.Message):
    __slots__ = ("reservation_id",)
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    def __init__(self, reservation_id: _Optional[str] = ...) -> None: ...

class ActivateReservationRequest(_message.Message):
    __slots__ = ("reservation_id",)
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    def __init__(self, reservation_id: _Optional[str] = ...) -> None: ...

class CompleteReservationRequest(_message.Message):
    __slots__ = ("reservation_id",)
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    def __init__(self, reservation_id: _Optional[str] = ...) -> None: ...

class MarkNoShowReservationRequest(_message.Message):
    __slots__ = ("reservation_id",)
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    def __init__(self, reservation_id: _Optional[str] = ...) -> None: ...
