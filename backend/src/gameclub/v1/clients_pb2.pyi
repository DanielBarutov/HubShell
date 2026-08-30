import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Client(_message.Message):
    __slots__ = ("id", "nickname", "phone", "discount_category", "balance_cents", "balance_bonus", "created_at", "updated_at", "blocked_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    BALANCE_BONUS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    BLOCKED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    nickname: str
    phone: str
    discount_category: str
    balance_cents: int
    balance_bonus: int
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    blocked_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., nickname: _Optional[str] = ..., phone: _Optional[str] = ..., discount_category: _Optional[str] = ..., balance_cents: _Optional[int] = ..., balance_bonus: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., blocked_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateClientRequest(_message.Message):
    __slots__ = ("nickname", "phone", "discount_category")
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    nickname: str
    phone: str
    discount_category: str
    def __init__(self, nickname: _Optional[str] = ..., phone: _Optional[str] = ..., discount_category: _Optional[str] = ...) -> None: ...

class SearchClientsRequest(_message.Message):
    __slots__ = ("query", "field")
    class Field(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        FIELD_UNSPECIFIED: _ClassVar[SearchClientsRequest.Field]
        FIELD_NICKNAME: _ClassVar[SearchClientsRequest.Field]
        FIELD_PHONE: _ClassVar[SearchClientsRequest.Field]
    FIELD_UNSPECIFIED: SearchClientsRequest.Field
    FIELD_NICKNAME: SearchClientsRequest.Field
    FIELD_PHONE: SearchClientsRequest.Field
    QUERY_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    query: str
    field: SearchClientsRequest.Field
    def __init__(self, query: _Optional[str] = ..., field: _Optional[_Union[SearchClientsRequest.Field, str]] = ...) -> None: ...

class SearchClientsResponse(_message.Message):
    __slots__ = ("clients",)
    CLIENTS_FIELD_NUMBER: _ClassVar[int]
    clients: _containers.RepeatedCompositeFieldContainer[Client]
    def __init__(self, clients: _Optional[_Iterable[_Union[Client, _Mapping]]] = ...) -> None: ...

class GetClientRequest(_message.Message):
    __slots__ = ("client_id",)
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    def __init__(self, client_id: _Optional[str] = ...) -> None: ...

class TopUpRequest(_message.Message):
    __slots__ = ("client_id", "amount_cents", "bonus_amount", "reason", "idempotency_key")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    amount_cents: int
    bonus_amount: int
    reason: str
    idempotency_key: str
    def __init__(self, client_id: _Optional[str] = ..., amount_cents: _Optional[int] = ..., bonus_amount: _Optional[int] = ..., reason: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class TopUpResponse(_message.Message):
    __slots__ = ("client", "operation_id", "idempotency_key")
    CLIENT_FIELD_NUMBER: _ClassVar[int]
    OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    client: Client
    operation_id: str
    idempotency_key: str
    def __init__(self, client: _Optional[_Union[Client, _Mapping]] = ..., operation_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class BalanceOperation(_message.Message):
    __slots__ = ("id", "client_id", "operation_type", "amount_cents", "bonus_amount", "reason", "actor_id", "idempotency_key", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    ACTOR_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    client_id: str
    operation_type: str
    amount_cents: int
    bonus_amount: int
    reason: str
    actor_id: str
    idempotency_key: str
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., client_id: _Optional[str] = ..., operation_type: _Optional[str] = ..., amount_cents: _Optional[int] = ..., bonus_amount: _Optional[int] = ..., reason: _Optional[str] = ..., actor_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ListBalanceOperationsRequest(_message.Message):
    __slots__ = ("client_id", "limit")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    limit: int
    def __init__(self, client_id: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class ListBalanceOperationsResponse(_message.Message):
    __slots__ = ("operations",)
    OPERATIONS_FIELD_NUMBER: _ClassVar[int]
    operations: _containers.RepeatedCompositeFieldContainer[BalanceOperation]
    def __init__(self, operations: _Optional[_Iterable[_Union[BalanceOperation, _Mapping]]] = ...) -> None: ...

class Guest(_message.Message):
    __slots__ = ("id", "nickname", "phone", "discount_category", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    nickname: str
    phone: str
    discount_category: str
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., nickname: _Optional[str] = ..., phone: _Optional[str] = ..., discount_category: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateGuestRequest(_message.Message):
    __slots__ = ("nickname", "phone", "discount_category")
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    DISCOUNT_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    nickname: str
    phone: str
    discount_category: str
    def __init__(self, nickname: _Optional[str] = ..., phone: _Optional[str] = ..., discount_category: _Optional[str] = ...) -> None: ...

class SearchGuestsRequest(_message.Message):
    __slots__ = ("query", "field")
    class Field(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        FIELD_UNSPECIFIED: _ClassVar[SearchGuestsRequest.Field]
        FIELD_NICKNAME: _ClassVar[SearchGuestsRequest.Field]
        FIELD_PHONE: _ClassVar[SearchGuestsRequest.Field]
    FIELD_UNSPECIFIED: SearchGuestsRequest.Field
    FIELD_NICKNAME: SearchGuestsRequest.Field
    FIELD_PHONE: SearchGuestsRequest.Field
    QUERY_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    query: str
    field: SearchGuestsRequest.Field
    def __init__(self, query: _Optional[str] = ..., field: _Optional[_Union[SearchGuestsRequest.Field, str]] = ...) -> None: ...

class SearchGuestsResponse(_message.Message):
    __slots__ = ("guests",)
    GUESTS_FIELD_NUMBER: _ClassVar[int]
    guests: _containers.RepeatedCompositeFieldContainer[Guest]
    def __init__(self, guests: _Optional[_Iterable[_Union[Guest, _Mapping]]] = ...) -> None: ...

class GetGuestRequest(_message.Message):
    __slots__ = ("guest_id",)
    GUEST_ID_FIELD_NUMBER: _ClassVar[int]
    guest_id: str
    def __init__(self, guest_id: _Optional[str] = ...) -> None: ...

class ListGuestsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListGuestsResponse(_message.Message):
    __slots__ = ("guests",)
    GUESTS_FIELD_NUMBER: _ClassVar[int]
    guests: _containers.RepeatedCompositeFieldContainer[Guest]
    def __init__(self, guests: _Optional[_Iterable[_Union[Guest, _Mapping]]] = ...) -> None: ...
