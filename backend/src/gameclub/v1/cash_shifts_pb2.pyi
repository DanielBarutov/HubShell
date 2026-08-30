import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CashShiftStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CASH_SHIFT_STATUS_UNSPECIFIED: _ClassVar[CashShiftStatus]
    CASH_SHIFT_STATUS_OPEN: _ClassVar[CashShiftStatus]
    CASH_SHIFT_STATUS_CLOSED: _ClassVar[CashShiftStatus]

class CashMovementDirection(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CASH_MOVEMENT_DIRECTION_UNSPECIFIED: _ClassVar[CashMovementDirection]
    CASH_MOVEMENT_DIRECTION_CASH_IN: _ClassVar[CashMovementDirection]
    CASH_MOVEMENT_DIRECTION_CASH_OUT: _ClassVar[CashMovementDirection]
    CASH_MOVEMENT_DIRECTION_CORRECTION: _ClassVar[CashMovementDirection]
CASH_SHIFT_STATUS_UNSPECIFIED: CashShiftStatus
CASH_SHIFT_STATUS_OPEN: CashShiftStatus
CASH_SHIFT_STATUS_CLOSED: CashShiftStatus
CASH_MOVEMENT_DIRECTION_UNSPECIFIED: CashMovementDirection
CASH_MOVEMENT_DIRECTION_CASH_IN: CashMovementDirection
CASH_MOVEMENT_DIRECTION_CASH_OUT: CashMovementDirection
CASH_MOVEMENT_DIRECTION_CORRECTION: CashMovementDirection

class CashShift(_message.Message):
    __slots__ = ("id", "register_id", "opened_by", "opened_at", "opening_balance_cents", "expected_close_cents", "status", "closed_by", "closed_at", "actual_close_cents", "difference_cents")
    ID_FIELD_NUMBER: _ClassVar[int]
    REGISTER_ID_FIELD_NUMBER: _ClassVar[int]
    OPENED_BY_FIELD_NUMBER: _ClassVar[int]
    OPENED_AT_FIELD_NUMBER: _ClassVar[int]
    OPENING_BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_CLOSE_CENTS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CLOSED_BY_FIELD_NUMBER: _ClassVar[int]
    CLOSED_AT_FIELD_NUMBER: _ClassVar[int]
    ACTUAL_CLOSE_CENTS_FIELD_NUMBER: _ClassVar[int]
    DIFFERENCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    id: str
    register_id: str
    opened_by: str
    opened_at: _timestamp_pb2.Timestamp
    opening_balance_cents: int
    expected_close_cents: int
    status: CashShiftStatus
    closed_by: str
    closed_at: _timestamp_pb2.Timestamp
    actual_close_cents: int
    difference_cents: int
    def __init__(self, id: _Optional[str] = ..., register_id: _Optional[str] = ..., opened_by: _Optional[str] = ..., opened_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., opening_balance_cents: _Optional[int] = ..., expected_close_cents: _Optional[int] = ..., status: _Optional[_Union[CashShiftStatus, str]] = ..., closed_by: _Optional[str] = ..., closed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., actual_close_cents: _Optional[int] = ..., difference_cents: _Optional[int] = ...) -> None: ...

class CashMovement(_message.Message):
    __slots__ = ("id", "shift_id", "direction", "amount_cents", "reason", "actor_id", "idempotency_key", "created_at", "reference_type", "reference_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    SHIFT_ID_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    ACTOR_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    REFERENCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    REFERENCE_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    shift_id: str
    direction: CashMovementDirection
    amount_cents: int
    reason: str
    actor_id: str
    idempotency_key: str
    created_at: _timestamp_pb2.Timestamp
    reference_type: str
    reference_id: str
    def __init__(self, id: _Optional[str] = ..., shift_id: _Optional[str] = ..., direction: _Optional[_Union[CashMovementDirection, str]] = ..., amount_cents: _Optional[int] = ..., reason: _Optional[str] = ..., actor_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., reference_type: _Optional[str] = ..., reference_id: _Optional[str] = ...) -> None: ...

class CashApproval(_message.Message):
    __slots__ = ("id", "shift_id", "kind", "target_key", "approved_by", "reason", "idempotency_key", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    SHIFT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    TARGET_KEY_FIELD_NUMBER: _ClassVar[int]
    APPROVED_BY_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    shift_id: str
    kind: str
    target_key: str
    approved_by: str
    reason: str
    idempotency_key: str
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., shift_id: _Optional[str] = ..., kind: _Optional[str] = ..., target_key: _Optional[str] = ..., approved_by: _Optional[str] = ..., reason: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class OpenCashShiftRequest(_message.Message):
    __slots__ = ("register_id", "opening_balance_cents", "idempotency_key")
    REGISTER_ID_FIELD_NUMBER: _ClassVar[int]
    OPENING_BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    register_id: str
    opening_balance_cents: int
    idempotency_key: str
    def __init__(self, register_id: _Optional[str] = ..., opening_balance_cents: _Optional[int] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class GetCashShiftRequest(_message.Message):
    __slots__ = ("shift_id",)
    SHIFT_ID_FIELD_NUMBER: _ClassVar[int]
    shift_id: str
    def __init__(self, shift_id: _Optional[str] = ...) -> None: ...

class ListCashShiftsRequest(_message.Message):
    __slots__ = ("limit",)
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    limit: int
    def __init__(self, limit: _Optional[int] = ...) -> None: ...

class ListCashShiftsResponse(_message.Message):
    __slots__ = ("shifts",)
    SHIFTS_FIELD_NUMBER: _ClassVar[int]
    shifts: _containers.RepeatedCompositeFieldContainer[CashShift]
    def __init__(self, shifts: _Optional[_Iterable[_Union[CashShift, _Mapping]]] = ...) -> None: ...

class ListCashMovementsRequest(_message.Message):
    __slots__ = ("shift_id", "limit")
    SHIFT_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    shift_id: str
    limit: int
    def __init__(self, shift_id: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class ListCashMovementsResponse(_message.Message):
    __slots__ = ("movements",)
    MOVEMENTS_FIELD_NUMBER: _ClassVar[int]
    movements: _containers.RepeatedCompositeFieldContainer[CashMovement]
    def __init__(self, movements: _Optional[_Iterable[_Union[CashMovement, _Mapping]]] = ...) -> None: ...

class RecordCashMovementRequest(_message.Message):
    __slots__ = ("shift_id", "direction", "amount_cents", "reason", "reference_type", "reference_id", "idempotency_key", "approval_id")
    SHIFT_ID_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    REFERENCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    REFERENCE_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    APPROVAL_ID_FIELD_NUMBER: _ClassVar[int]
    shift_id: str
    direction: CashMovementDirection
    amount_cents: int
    reason: str
    reference_type: str
    reference_id: str
    idempotency_key: str
    approval_id: str
    def __init__(self, shift_id: _Optional[str] = ..., direction: _Optional[_Union[CashMovementDirection, str]] = ..., amount_cents: _Optional[int] = ..., reason: _Optional[str] = ..., reference_type: _Optional[str] = ..., reference_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., approval_id: _Optional[str] = ...) -> None: ...

class CloseCashShiftRequest(_message.Message):
    __slots__ = ("shift_id", "actual_close_cents", "idempotency_key", "approval_id")
    SHIFT_ID_FIELD_NUMBER: _ClassVar[int]
    ACTUAL_CLOSE_CENTS_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    APPROVAL_ID_FIELD_NUMBER: _ClassVar[int]
    shift_id: str
    actual_close_cents: int
    idempotency_key: str
    approval_id: str
    def __init__(self, shift_id: _Optional[str] = ..., actual_close_cents: _Optional[int] = ..., idempotency_key: _Optional[str] = ..., approval_id: _Optional[str] = ...) -> None: ...

class CreateCashApprovalRequest(_message.Message):
    __slots__ = ("shift_id", "kind", "target_key", "reason", "idempotency_key")
    SHIFT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    TARGET_KEY_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    shift_id: str
    kind: str
    target_key: str
    reason: str
    idempotency_key: str
    def __init__(self, shift_id: _Optional[str] = ..., kind: _Optional[str] = ..., target_key: _Optional[str] = ..., reason: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...
