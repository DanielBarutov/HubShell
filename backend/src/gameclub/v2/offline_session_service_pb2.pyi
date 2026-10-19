import datetime

from gameclub.v2 import offline_session_snapshot_pb2 as _offline_session_snapshot_pb2
from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ResumeOfflinePortalRequest(_message.Message):
    __slots__ = ("device_id", "session_id", "client_id")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    session_id: str
    client_id: str
    def __init__(self, device_id: _Optional[str] = ..., session_id: _Optional[str] = ..., client_id: _Optional[str] = ...) -> None: ...

class ResumeOfflinePortalResponse(_message.Message):
    __slots__ = ("client_id", "portal_access_token", "portal_access_expires_in")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    PORTAL_ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    PORTAL_ACCESS_EXPIRES_IN_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    portal_access_token: str
    portal_access_expires_in: int
    def __init__(self, client_id: _Optional[str] = ..., portal_access_token: _Optional[str] = ..., portal_access_expires_in: _Optional[int] = ...) -> None: ...

class StopOfflineSessionRequest(_message.Message):
    __slots__ = ("device_id", "session_id", "client_id")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    session_id: str
    client_id: str
    def __init__(self, device_id: _Optional[str] = ..., session_id: _Optional[str] = ..., client_id: _Optional[str] = ...) -> None: ...

class RedeemGuestAccessRequest(_message.Message):
    __slots__ = ("device_id", "session_id", "applied_grant_ids")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    APPLIED_GRANT_IDS_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    session_id: str
    applied_grant_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, device_id: _Optional[str] = ..., session_id: _Optional[str] = ..., applied_grant_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class StopGuestAccessRequest(_message.Message):
    __slots__ = ("device_id", "session_id", "payment_id")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_ID_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    session_id: str
    payment_id: str
    def __init__(self, device_id: _Optional[str] = ..., session_id: _Optional[str] = ..., payment_id: _Optional[str] = ...) -> None: ...

class LoginOfflineSessionRequest(_message.Message):
    __slots__ = ("device_id", "identifier", "password", "idempotency_key")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    IDENTIFIER_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    identifier: str
    password: str
    idempotency_key: str
    def __init__(self, device_id: _Optional[str] = ..., identifier: _Optional[str] = ..., password: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class RegisterOfflineSessionRequest(_message.Message):
    __slots__ = ("device_id", "nickname", "phone", "password", "idempotency_key")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    nickname: str
    phone: str
    password: str
    idempotency_key: str
    def __init__(self, device_id: _Optional[str] = ..., nickname: _Optional[str] = ..., phone: _Optional[str] = ..., password: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class ChangeOfflinePasswordRequest(_message.Message):
    __slots__ = ("device_id", "new_password")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    NEW_PASSWORD_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    new_password: str
    def __init__(self, device_id: _Optional[str] = ..., new_password: _Optional[str] = ...) -> None: ...

class GetOfflinePortalSnapshotRequest(_message.Message):
    __slots__ = ("device_id", "limit")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    limit: int
    def __init__(self, device_id: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class ActivateOfflineEntitlementRequest(_message.Message):
    __slots__ = ("device_id", "entitlement_id")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    ENTITLEMENT_ID_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    entitlement_id: str
    def __init__(self, device_id: _Optional[str] = ..., entitlement_id: _Optional[str] = ...) -> None: ...

class PurchaseOfflineEntitlementRequest(_message.Message):
    __slots__ = ("device_id", "tariff_id", "idempotency_key", "bonus_confirmation")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    BONUS_CONFIRMATION_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    tariff_id: str
    idempotency_key: str
    bonus_confirmation: OfflineBonusPurchaseConfirmation
    def __init__(self, device_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., bonus_confirmation: _Optional[_Union[OfflineBonusPurchaseConfirmation, _Mapping]] = ...) -> None: ...

class QuoteOfflineEntitlementRequest(_message.Message):
    __slots__ = ("device_id", "tariff_id", "use_bonus")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    USE_BONUS_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    tariff_id: str
    use_bonus: bool
    def __init__(self, device_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., use_bonus: _Optional[bool] = ...) -> None: ...

class OfflineBonusPurchaseConfirmation(_message.Message):
    __slots__ = ("price_cents", "bonus_cents", "money_cents", "earned_bonus_cents")
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_CENTS_FIELD_NUMBER: _ClassVar[int]
    MONEY_CENTS_FIELD_NUMBER: _ClassVar[int]
    EARNED_BONUS_CENTS_FIELD_NUMBER: _ClassVar[int]
    price_cents: int
    bonus_cents: int
    money_cents: int
    earned_bonus_cents: int
    def __init__(self, price_cents: _Optional[int] = ..., bonus_cents: _Optional[int] = ..., money_cents: _Optional[int] = ..., earned_bonus_cents: _Optional[int] = ...) -> None: ...

class OfflineBonusGameQuote(_message.Message):
    __slots__ = ("price_cents", "bonus_cents", "money_cents", "earned_bonus_cents", "earning_rate_bps", "payment_limit_bps", "available_bonus_cents", "reserved_bonus_cents", "bonus_allowed", "can_pay")
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_CENTS_FIELD_NUMBER: _ClassVar[int]
    MONEY_CENTS_FIELD_NUMBER: _ClassVar[int]
    EARNED_BONUS_CENTS_FIELD_NUMBER: _ClassVar[int]
    EARNING_RATE_BPS_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_LIMIT_BPS_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_BONUS_CENTS_FIELD_NUMBER: _ClassVar[int]
    RESERVED_BONUS_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    CAN_PAY_FIELD_NUMBER: _ClassVar[int]
    price_cents: int
    bonus_cents: int
    money_cents: int
    earned_bonus_cents: int
    earning_rate_bps: int
    payment_limit_bps: int
    available_bonus_cents: int
    reserved_bonus_cents: int
    bonus_allowed: bool
    can_pay: bool
    def __init__(self, price_cents: _Optional[int] = ..., bonus_cents: _Optional[int] = ..., money_cents: _Optional[int] = ..., earned_bonus_cents: _Optional[int] = ..., earning_rate_bps: _Optional[int] = ..., payment_limit_bps: _Optional[int] = ..., available_bonus_cents: _Optional[int] = ..., reserved_bonus_cents: _Optional[int] = ..., bonus_allowed: _Optional[bool] = ..., can_pay: _Optional[bool] = ...) -> None: ...

class EnableMinuteBonusRequest(_message.Message):
    __slots__ = ("device_id", "session_id", "snapshot_id", "snapshot_version", "last_sequence", "last_payload_hash", "idempotency_key")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_ID_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_VERSION_FIELD_NUMBER: _ClassVar[int]
    LAST_SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    LAST_PAYLOAD_HASH_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    session_id: str
    snapshot_id: str
    snapshot_version: int
    last_sequence: int
    last_payload_hash: str
    idempotency_key: str
    def __init__(self, device_id: _Optional[str] = ..., session_id: _Optional[str] = ..., snapshot_id: _Optional[str] = ..., snapshot_version: _Optional[int] = ..., last_sequence: _Optional[int] = ..., last_payload_hash: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class MinuteBonusBudgetPayload(_message.Message):
    __slots__ = ("grant_id", "schema_version", "grant_version", "client_id", "session_id", "device_id", "snapshot_id", "snapshot_version", "checkpoint_sequence", "checkpoint_hash", "budget_cents", "payment_limit_bps", "issued_at", "idempotency_key")
    GRANT_ID_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    GRANT_VERSION_FIELD_NUMBER: _ClassVar[int]
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_ID_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_VERSION_FIELD_NUMBER: _ClassVar[int]
    CHECKPOINT_SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    CHECKPOINT_HASH_FIELD_NUMBER: _ClassVar[int]
    BUDGET_CENTS_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_LIMIT_BPS_FIELD_NUMBER: _ClassVar[int]
    ISSUED_AT_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    grant_id: str
    schema_version: int
    grant_version: int
    client_id: str
    session_id: str
    device_id: str
    snapshot_id: str
    snapshot_version: int
    checkpoint_sequence: int
    checkpoint_hash: str
    budget_cents: int
    payment_limit_bps: int
    issued_at: _timestamp_pb2.Timestamp
    idempotency_key: str
    def __init__(self, grant_id: _Optional[str] = ..., schema_version: _Optional[int] = ..., grant_version: _Optional[int] = ..., client_id: _Optional[str] = ..., session_id: _Optional[str] = ..., device_id: _Optional[str] = ..., snapshot_id: _Optional[str] = ..., snapshot_version: _Optional[int] = ..., checkpoint_sequence: _Optional[int] = ..., checkpoint_hash: _Optional[str] = ..., budget_cents: _Optional[int] = ..., payment_limit_bps: _Optional[int] = ..., issued_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class SignedMinuteBonusBudget(_message.Message):
    __slots__ = ("payload", "signing_key_id", "signature")
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    SIGNING_KEY_ID_FIELD_NUMBER: _ClassVar[int]
    SIGNATURE_FIELD_NUMBER: _ClassVar[int]
    payload: MinuteBonusBudgetPayload
    signing_key_id: str
    signature: bytes
    def __init__(self, payload: _Optional[_Union[MinuteBonusBudgetPayload, _Mapping]] = ..., signing_key_id: _Optional[str] = ..., signature: _Optional[bytes] = ...) -> None: ...

class OfflinePortalSnapshot(_message.Message):
    __slots__ = ("client_id", "nickname", "phone", "balance_cents", "balance_bonus", "available_time_minutes", "balance_operations", "sessions", "charges", "purchases", "entitlements", "tariffs", "reservations", "payment_methods", "purchased_package", "bonus_wallet", "active_package")
    CLIENT_ID_FIELD_NUMBER: _ClassVar[int]
    NICKNAME_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    BALANCE_CENTS_FIELD_NUMBER: _ClassVar[int]
    BALANCE_BONUS_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_TIME_MINUTES_FIELD_NUMBER: _ClassVar[int]
    BALANCE_OPERATIONS_FIELD_NUMBER: _ClassVar[int]
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    CHARGES_FIELD_NUMBER: _ClassVar[int]
    PURCHASES_FIELD_NUMBER: _ClassVar[int]
    ENTITLEMENTS_FIELD_NUMBER: _ClassVar[int]
    TARIFFS_FIELD_NUMBER: _ClassVar[int]
    RESERVATIONS_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_METHODS_FIELD_NUMBER: _ClassVar[int]
    PURCHASED_PACKAGE_FIELD_NUMBER: _ClassVar[int]
    BONUS_WALLET_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_PACKAGE_FIELD_NUMBER: _ClassVar[int]
    client_id: str
    nickname: str
    phone: str
    balance_cents: int
    balance_bonus: int
    available_time_minutes: int
    balance_operations: _containers.RepeatedCompositeFieldContainer[OfflineBalanceOperation]
    sessions: _containers.RepeatedCompositeFieldContainer[OfflinePortalSession]
    charges: _containers.RepeatedCompositeFieldContainer[OfflinePortalCharge]
    purchases: _containers.RepeatedCompositeFieldContainer[OfflinePortalPurchase]
    entitlements: _containers.RepeatedCompositeFieldContainer[OfflinePortalEntitlement]
    tariffs: _containers.RepeatedCompositeFieldContainer[OfflinePortalTariff]
    reservations: _containers.RepeatedCompositeFieldContainer[OfflinePortalReservation]
    payment_methods: _containers.RepeatedCompositeFieldContainer[OfflinePaymentMethod]
    purchased_package: _offline_session_snapshot_pb2.SignedOfflineSessionSnapshot
    bonus_wallet: OfflineBonusWallet
    active_package: _offline_session_snapshot_pb2.SignedOfflineSessionSnapshot
    def __init__(self, client_id: _Optional[str] = ..., nickname: _Optional[str] = ..., phone: _Optional[str] = ..., balance_cents: _Optional[int] = ..., balance_bonus: _Optional[int] = ..., available_time_minutes: _Optional[int] = ..., balance_operations: _Optional[_Iterable[_Union[OfflineBalanceOperation, _Mapping]]] = ..., sessions: _Optional[_Iterable[_Union[OfflinePortalSession, _Mapping]]] = ..., charges: _Optional[_Iterable[_Union[OfflinePortalCharge, _Mapping]]] = ..., purchases: _Optional[_Iterable[_Union[OfflinePortalPurchase, _Mapping]]] = ..., entitlements: _Optional[_Iterable[_Union[OfflinePortalEntitlement, _Mapping]]] = ..., tariffs: _Optional[_Iterable[_Union[OfflinePortalTariff, _Mapping]]] = ..., reservations: _Optional[_Iterable[_Union[OfflinePortalReservation, _Mapping]]] = ..., payment_methods: _Optional[_Iterable[_Union[OfflinePaymentMethod, _Mapping]]] = ..., purchased_package: _Optional[_Union[_offline_session_snapshot_pb2.SignedOfflineSessionSnapshot, _Mapping]] = ..., bonus_wallet: _Optional[_Union[OfflineBonusWallet, _Mapping]] = ..., active_package: _Optional[_Union[_offline_session_snapshot_pb2.SignedOfflineSessionSnapshot, _Mapping]] = ...) -> None: ...

class OfflineBonusWallet(_message.Message):
    __slots__ = ("total_cents", "available_cents", "reserved_cents", "pending_cents")
    TOTAL_CENTS_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_CENTS_FIELD_NUMBER: _ClassVar[int]
    RESERVED_CENTS_FIELD_NUMBER: _ClassVar[int]
    PENDING_CENTS_FIELD_NUMBER: _ClassVar[int]
    total_cents: int
    available_cents: int
    reserved_cents: int
    pending_cents: int
    def __init__(self, total_cents: _Optional[int] = ..., available_cents: _Optional[int] = ..., reserved_cents: _Optional[int] = ..., pending_cents: _Optional[int] = ...) -> None: ...

class OfflinePaymentPart(_message.Message):
    __slots__ = ("method", "amount_cents", "reference")
    METHOD_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    REFERENCE_FIELD_NUMBER: _ClassVar[int]
    method: str
    amount_cents: int
    reference: str
    def __init__(self, method: _Optional[str] = ..., amount_cents: _Optional[int] = ..., reference: _Optional[str] = ...) -> None: ...

class OfflineBalanceOperation(_message.Message):
    __slots__ = ("id", "operation_type", "amount_cents", "bonus_amount", "reason", "created_at", "payment_parts")
    ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_TYPE_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    BONUS_AMOUNT_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_PARTS_FIELD_NUMBER: _ClassVar[int]
    id: str
    operation_type: str
    amount_cents: int
    bonus_amount: int
    reason: str
    created_at: str
    payment_parts: _containers.RepeatedCompositeFieldContainer[OfflinePaymentPart]
    def __init__(self, id: _Optional[str] = ..., operation_type: _Optional[str] = ..., amount_cents: _Optional[int] = ..., bonus_amount: _Optional[int] = ..., reason: _Optional[str] = ..., created_at: _Optional[str] = ..., payment_parts: _Optional[_Iterable[_Union[OfflinePaymentPart, _Mapping]]] = ...) -> None: ...

class OfflinePortalSession(_message.Message):
    __slots__ = ("id", "workstation_id", "status", "started_at", "ended_at", "tariff_id", "tariff_name", "tariff_quantity", "workstation_name", "duration_minutes")
    ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    ENDED_AT_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_NAME_FIELD_NUMBER: _ClassVar[int]
    TARIFF_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_NAME_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    id: str
    workstation_id: str
    status: str
    started_at: str
    ended_at: str
    tariff_id: str
    tariff_name: str
    tariff_quantity: int
    workstation_name: str
    duration_minutes: int
    def __init__(self, id: _Optional[str] = ..., workstation_id: _Optional[str] = ..., status: _Optional[str] = ..., started_at: _Optional[str] = ..., ended_at: _Optional[str] = ..., tariff_id: _Optional[str] = ..., tariff_name: _Optional[str] = ..., tariff_quantity: _Optional[int] = ..., workstation_name: _Optional[str] = ..., duration_minutes: _Optional[int] = ...) -> None: ...

class OfflinePortalCharge(_message.Message):
    __slots__ = ("id", "session_id", "tariff_id", "duration_minutes", "amount_cents", "tariff_name", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    TARIFF_NAME_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    session_id: str
    tariff_id: str
    duration_minutes: int
    amount_cents: int
    tariff_name: str
    created_at: str
    def __init__(self, id: _Optional[str] = ..., session_id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., amount_cents: _Optional[int] = ..., tariff_name: _Optional[str] = ..., created_at: _Optional[str] = ...) -> None: ...

class OfflinePortalPurchase(_message.Message):
    __slots__ = ("id", "product_name", "quantity", "total_price_cents", "payment_method", "created_at", "payment_parts")
    ID_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_NAME_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_METHOD_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    PAYMENT_PARTS_FIELD_NUMBER: _ClassVar[int]
    id: str
    product_name: str
    quantity: int
    total_price_cents: int
    payment_method: str
    created_at: str
    payment_parts: _containers.RepeatedCompositeFieldContainer[OfflinePaymentPart]
    def __init__(self, id: _Optional[str] = ..., product_name: _Optional[str] = ..., quantity: _Optional[int] = ..., total_price_cents: _Optional[int] = ..., payment_method: _Optional[str] = ..., created_at: _Optional[str] = ..., payment_parts: _Optional[_Iterable[_Union[OfflinePaymentPart, _Mapping]]] = ...) -> None: ...

class OfflinePortalEntitlement(_message.Message):
    __slots__ = ("id", "tariff_id", "zone_id", "status", "duration_minutes", "remaining_minutes", "price_cents", "queue_position", "tariff_name", "purchased_at", "activated_at", "time_restricted", "sale_window_start_minute", "sale_window_end_minute", "usage_window_start_minute", "usage_window_end_minute", "window_timezone", "audience")
    ID_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    REMAINING_MINUTES_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    QUEUE_POSITION_FIELD_NUMBER: _ClassVar[int]
    TARIFF_NAME_FIELD_NUMBER: _ClassVar[int]
    PURCHASED_AT_FIELD_NUMBER: _ClassVar[int]
    ACTIVATED_AT_FIELD_NUMBER: _ClassVar[int]
    TIME_RESTRICTED_FIELD_NUMBER: _ClassVar[int]
    SALE_WINDOW_START_MINUTE_FIELD_NUMBER: _ClassVar[int]
    SALE_WINDOW_END_MINUTE_FIELD_NUMBER: _ClassVar[int]
    USAGE_WINDOW_START_MINUTE_FIELD_NUMBER: _ClassVar[int]
    USAGE_WINDOW_END_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    AUDIENCE_FIELD_NUMBER: _ClassVar[int]
    id: str
    tariff_id: str
    zone_id: str
    status: str
    duration_minutes: int
    remaining_minutes: int
    price_cents: int
    queue_position: int
    tariff_name: str
    purchased_at: str
    activated_at: str
    time_restricted: bool
    sale_window_start_minute: int
    sale_window_end_minute: int
    usage_window_start_minute: int
    usage_window_end_minute: int
    window_timezone: str
    audience: str
    def __init__(self, id: _Optional[str] = ..., tariff_id: _Optional[str] = ..., zone_id: _Optional[str] = ..., status: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., remaining_minutes: _Optional[int] = ..., price_cents: _Optional[int] = ..., queue_position: _Optional[int] = ..., tariff_name: _Optional[str] = ..., purchased_at: _Optional[str] = ..., activated_at: _Optional[str] = ..., time_restricted: _Optional[bool] = ..., sale_window_start_minute: _Optional[int] = ..., sale_window_end_minute: _Optional[int] = ..., usage_window_start_minute: _Optional[int] = ..., usage_window_end_minute: _Optional[int] = ..., window_timezone: _Optional[str] = ..., audience: _Optional[str] = ...) -> None: ...

class OfflinePortalTariff(_message.Message):
    __slots__ = ("id", "name", "zone_id", "duration_minutes", "price_cents", "time_restricted", "sale_window_start_minute", "sale_window_end_minute", "usage_window_start_minute", "usage_window_end_minute", "window_timezone", "audience")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    TIME_RESTRICTED_FIELD_NUMBER: _ClassVar[int]
    SALE_WINDOW_START_MINUTE_FIELD_NUMBER: _ClassVar[int]
    SALE_WINDOW_END_MINUTE_FIELD_NUMBER: _ClassVar[int]
    USAGE_WINDOW_START_MINUTE_FIELD_NUMBER: _ClassVar[int]
    USAGE_WINDOW_END_MINUTE_FIELD_NUMBER: _ClassVar[int]
    WINDOW_TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    AUDIENCE_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    zone_id: str
    duration_minutes: int
    price_cents: int
    time_restricted: bool
    sale_window_start_minute: int
    sale_window_end_minute: int
    usage_window_start_minute: int
    usage_window_end_minute: int
    window_timezone: str
    audience: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., zone_id: _Optional[str] = ..., duration_minutes: _Optional[int] = ..., price_cents: _Optional[int] = ..., time_restricted: _Optional[bool] = ..., sale_window_start_minute: _Optional[int] = ..., sale_window_end_minute: _Optional[int] = ..., usage_window_start_minute: _Optional[int] = ..., usage_window_end_minute: _Optional[int] = ..., window_timezone: _Optional[str] = ..., audience: _Optional[str] = ...) -> None: ...

class OfflinePortalReservation(_message.Message):
    __slots__ = ("id", "workstation_ids", "start_at", "end_at", "status", "tariff_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_IDS_FIELD_NUMBER: _ClassVar[int]
    START_AT_FIELD_NUMBER: _ClassVar[int]
    END_AT_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TARIFF_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    workstation_ids: _containers.RepeatedScalarFieldContainer[str]
    start_at: str
    end_at: str
    status: str
    tariff_id: str
    def __init__(self, id: _Optional[str] = ..., workstation_ids: _Optional[_Iterable[str]] = ..., start_at: _Optional[str] = ..., end_at: _Optional[str] = ..., status: _Optional[str] = ..., tariff_id: _Optional[str] = ...) -> None: ...

class OfflinePaymentMethod(_message.Message):
    __slots__ = ("key", "name")
    KEY_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    key: str
    name: str
    def __init__(self, key: _Optional[str] = ..., name: _Optional[str] = ...) -> None: ...
