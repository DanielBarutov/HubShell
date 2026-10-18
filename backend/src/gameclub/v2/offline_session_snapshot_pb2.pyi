import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class OfflinePackageStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    OFFLINE_PACKAGE_STATUS_UNSPECIFIED: _ClassVar[OfflinePackageStatus]
    OFFLINE_PACKAGE_STATUS_ACTIVE: _ClassVar[OfflinePackageStatus]
    OFFLINE_PACKAGE_STATUS_QUEUED: _ClassVar[OfflinePackageStatus]
    OFFLINE_PACKAGE_STATUS_EXHAUSTED: _ClassVar[OfflinePackageStatus]
    OFFLINE_PACKAGE_STATUS_BURNED: _ClassVar[OfflinePackageStatus]
OFFLINE_PACKAGE_STATUS_UNSPECIFIED: OfflinePackageStatus
OFFLINE_PACKAGE_STATUS_ACTIVE: OfflinePackageStatus
OFFLINE_PACKAGE_STATUS_QUEUED: OfflinePackageStatus
OFFLINE_PACKAGE_STATUS_EXHAUSTED: OfflinePackageStatus
OFFLINE_PACKAGE_STATUS_BURNED: OfflinePackageStatus

class OfflinePackageSnapshot(_message.Message):
    __slots__ = ("package_id", "tariff_id", "zone_id", "remaining_minutes", "status")
    PACKAGE_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    REMAINING_MINUTES_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    package_id: str
    tariff_id: str
    zone_id: str
    remaining_minutes: int
    status: OfflinePackageStatus
    def __init__(self, package_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., zone_id: _Optional[str] = ..., remaining_minutes: _Optional[int] = ..., status: _Optional[_Union[OfflinePackageStatus, str]] = ...) -> None: ...

class OfflineTariffSnapshot(_message.Message):
    __slots__ = ("tariff_id", "name", "zone_id", "package_minutes", "package_price_cents", "per_minute_price_cents", "is_purchasable", "usage_window_start_minute", "usage_window_end_minute", "window_timezone", "is_per_minute")
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    PACKAGE_MINUTES_FIELD_NUMBER: _ClassVar[int]
    PACKAGE_PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PER_MINUTE_PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    IS_PURCHASABLE_FIELD_NUMBER: _ClassVar[int]
    USAGE_WINDOW_START_MINUTE_FIELD_NUMBER: _ClassVar[int]
    USAGE_WINDOW_END_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    IS_PER_MINUTE_FIELD_NUMBER: _ClassVar[int]
    tariff_id: str
    name: str
    zone_id: str
    package_minutes: int
    package_price_cents: int
    per_minute_price_cents: int
    is_purchasable: bool
    usage_window_start_minute: int
    usage_window_end_minute: int
    window_timezone: str
    is_per_minute: bool
    def __init__(self, tariff_id: _Optional[str] = ..., name: _Optional[str] = ..., zone_id: _Optional[str] = ..., package_minutes: _Optional[int] = ..., package_price_cents: _Optional[int] = ..., per_minute_price_cents: _Optional[int] = ..., is_purchasable: _Optional[bool] = ..., usage_window_start_minute: _Optional[int] = ..., usage_window_end_minute: _Optional[int] = ..., window_timezone: _Optional[str] = ..., is_per_minute: _Optional[bool] = ...) -> None: ...

class OfflineSessionSnapshotPayload(_message.Message):
    __slots__ = ("snapshot_id", "schema_version", "snapshot_version", "issued_at", "client_id", "session_id", "device_id", "workstation_zone_id", "balance_cents", "debt_limit_cents", "login_grant_remaining_minutes", "packages", "tariffs", "policy_version", "purchase_idempotency_key", "purchase_money_cents", "purchase_bonus_cents")
    SNAPSHOT_ID_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_VERSION_FIELD_NUMBER: _ClassVar[int]
    ISSUED_AT_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    DEBT_LIMIT_CENTS_FIELD_NUMBER: _ClassVar[int]
    LOGIN_GRANT_REMAINING_MINUTES_FIELD_NUMBER: _ClassVar[int]
    PACKAGES_FIELD_NUMBER: _ClassVar[int]
    TARIFFS_FIELD_NUMBER: _ClassVar[int]
    POLICY_VERSION_FIELD_NUMBER: _ClassVar[int]
    PURCHASE_IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    PURCHASE_MONEY_CENTS_FIELD_NUMBER: _ClassVar[int]
    PURCHASE_BONUS_CENTS_FIELD_NUMBER: _ClassVar[int]
    snapshot_id: str
    schema_version: int
    snapshot_version: int
    issued_at: _timestamp_pb2.Timestamp
    client_id: str
    session_id: str
    device_id: str
    workstation_zone_id: str
    balance_cents: int
    debt_limit_cents: int
    login_grant_remaining_minutes: int
    packages: _containers.RepeatedCompositeFieldContainer[OfflinePackageSnapshot]
    tariffs: _containers.RepeatedCompositeFieldContainer[OfflineTariffSnapshot]
    policy_version: str
    purchase_idempotency_key: str
    purchase_money_cents: int
    purchase_bonus_cents: int
    def __init__(self, snapshot_id: _Optional[str] = ..., schema_version: _Optional[int] = ..., snapshot_version: _Optional[int] = ..., issued_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., client_id: _Optional[str] = ..., session_id: _Optional[str] = ..., device_id: _Optional[str] = ..., workstation_zone_id: _Optional[str] = ..., balance_cents: _Optional[int] = ..., debt_limit_cents: _Optional[int] = ..., login_grant_remaining_minutes: _Optional[int] = ..., packages: _Optional[_Iterable[_Union[OfflinePackageSnapshot, _Mapping]]] = ..., tariffs: _Optional[_Iterable[_Union[OfflineTariffSnapshot, _Mapping]]] = ..., policy_version: _Optional[str] = ..., purchase_idempotency_key: _Optional[str] = ..., purchase_money_cents: _Optional[int] = ..., purchase_bonus_cents: _Optional[int] = ...) -> None: ...

class SignedOfflineSessionSnapshot(_message.Message):
    __slots__ = ("payload", "signing_key_id", "signature", "password_reset_required", "password_reset_token", "portal_access_token", "portal_access_expires_in")
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    SIGNING_KEY_ID_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_RESET_REQUIRED_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_RESET_TOKEN_FIELD_NUMBER: _ClassVar[int]
    PORTAL_ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    PORTAL_ACCESS_EXPIRES_IN_FIELD_NUMBER: _ClassVar[int]
    payload: OfflineSessionSnapshotPayload
    signing_key_id: str
    signature: bytes
    password_reset_required: bool
    password_reset_token: str
    portal_access_token: str
    portal_access_expires_in: int
    def __init__(self, payload: _Optional[_Union[OfflineSessionSnapshotPayload, _Mapping]] = ..., signing_key_id: _Optional[str] = ..., signature: _Optional[bytes] = ..., password_reset_required: _Optional[bool] = ..., password_reset_token: _Optional[str] = ..., portal_access_token: _Optional[str] = ..., portal_access_expires_in: _Optional[int] = ...) -> None: ...

class GuestSessionAccessPayload(_message.Message):
    __slots__ = ("grant_id", "schema_version", "issued_at", "expires_at", "payment_id", "session_id", "device_id", "workstation_zone_id", "guest_name", "tariff_id", "tariff_name", "duration_minutes", "tariff_quantity")
    GRANT_ID_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    ISSUED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    GUEST_NAME_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_NAME_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    TARIFF_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    grant_id: str
    schema_version: int
    issued_at: _timestamp_pb2.Timestamp
    expires_at: _timestamp_pb2.Timestamp
    payment_id: str
    session_id: str
    device_id: str
    workstation_zone_id: str
    guest_name: str
    tariff_id: str
    tariff_name: str
    duration_minutes: int
    tariff_quantity: int
    def __init__(self, grant_id: _Optional[str] = ..., schema_version: _Optional[int] = ..., issued_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., expires_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., payment_id: _Optional[str] = ..., session_id: _Optional[str] = ..., device_id: _Optional[str] = ..., workstation_zone_id: _Optional[str] = ..., guest_name: _Optional[str] = ..., tariff_id: _Optional[str] = ..., tariff_name: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., tariff_quantity: _Optional[int] = ...) -> None: ...

class SignedGuestSessionAccess(_message.Message):
    __slots__ = ("payload", "signing_key_id", "signature")
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    SIGNING_KEY_ID_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    payload: GuestSessionAccessPayload
    signing_key_id: str
    signature: bytes
    def __init__(self, payload: _Optional[_Union[GuestSessionAccessPayload, _Mapping]] = ..., signing_key_id: _Optional[str] = ..., signature: _Optional[bytes] = ...) -> None: ...
