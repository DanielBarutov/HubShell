import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class WorkstationStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WORKSTATION_STATUS_UNSPECIFIED: _ClassVar[WorkstationStatus]
    WORKSTATION_STATUS_UNKNOWN: _ClassVar[WorkstationStatus]
    WORKSTATION_STATUS_ONLINE: _ClassVar[WorkstationStatus]
    WORKSTATION_STATUS_STALE: _ClassVar[WorkstationStatus]
    WORKSTATION_STATUS_OFFLINE: _ClassVar[WorkstationStatus]
    WORKSTATION_STATUS_DISABLED: _ClassVar[WorkstationStatus]

class WorkstationCommandStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WORKSTATION_COMMAND_STATUS_UNSPECIFIED: _ClassVar[WorkstationCommandStatus]
    WORKSTATION_COMMAND_STATUS_QUEUED: _ClassVar[WorkstationCommandStatus]
    WORKSTATION_COMMAND_STATUS_ACKNOWLEDGED: _ClassVar[WorkstationCommandStatus]
    WORKSTATION_COMMAND_STATUS_FAILED: _ClassVar[WorkstationCommandStatus]
    WORKSTATION_COMMAND_STATUS_EXPIRED: _ClassVar[WorkstationCommandStatus]
WORKSTATION_STATUS_UNSPECIFIED: WorkstationStatus
WORKSTATION_STATUS_UNKNOWN: WorkstationStatus
WORKSTATION_STATUS_ONLINE: WorkstationStatus
WORKSTATION_STATUS_STALE: WorkstationStatus
WORKSTATION_STATUS_OFFLINE: WorkstationStatus
WORKSTATION_STATUS_DISABLED: WorkstationStatus
WORKSTATION_COMMAND_STATUS_UNSPECIFIED: WorkstationCommandStatus
WORKSTATION_COMMAND_STATUS_QUEUED: WorkstationCommandStatus
WORKSTATION_COMMAND_STATUS_ACKNOWLEDGED: WorkstationCommandStatus
WORKSTATION_COMMAND_STATUS_FAILED: WorkstationCommandStatus
WORKSTATION_COMMAND_STATUS_EXPIRED: WorkstationCommandStatus

class Workstation(_message.Message):
    __slots__ = ("id", "device_id", "name", "group_id", "position", "status", "last_seen_at", "client_version", "disabled_reason", "capabilities", "theme", "manager_password_verifier", "lockdown_policy")
    ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_AT_FIELD_NUMBER: _ClassVar[int]
    CLIENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    DISABLED_REASON_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    THEME_FIELD_NUMBER: _ClassVar[int]
    MANAGER_PASSWORD_VERIFIER_FIELD_NUMBER: _ClassVar[int]
    LOCKDOWN_POLICY_FIELD_NUMBER: _ClassVar[int]
    id: str
    device_id: str
    name: str
    group_id: str
    position: int
    status: WorkstationStatus
    last_seen_at: _timestamp_pb2.Timestamp
    client_version: str
    disabled_reason: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    theme: str
    manager_password_verifier: str
    lockdown_policy: WorkstationLockdownPolicy
    def __init__(self, id: _Optional[str] = ..., device_id: _Optional[str] = ..., name: _Optional[str] = ..., group_id: _Optional[str] = ..., position: _Optional[int] = ..., status: _Optional[_Union[WorkstationStatus, str]] = ..., last_seen_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., client_version: _Optional[str] = ..., disabled_reason: _Optional[str] = ..., capabilities: _Optional[_Iterable[str]] = ..., theme: _Optional[str] = ..., manager_password_verifier: _Optional[str] = ..., lockdown_policy: _Optional[_Union[WorkstationLockdownPolicy, _Mapping]] = ...) -> None: ...

class WorkstationGroup(_message.Message):
    __slots__ = ("id", "name", "theme", "updated_at", "lockdown_policy")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    THEME_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    LOCKDOWN_POLICY_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    theme: str
    updated_at: _timestamp_pb2.Timestamp
    lockdown_policy: WorkstationLockdownPolicy
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., theme: _Optional[str] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., lockdown_policy: _Optional[_Union[WorkstationLockdownPolicy, _Mapping]] = ...) -> None: ...

class WorkstationLockdownPolicy(_message.Message):
    __slots__ = ("deployment_mode", "shell_enabled", "user_self_login_enabled", "lock_after_session", "restart_after_session", "hidden_drives", "block_external_storage", "disable_start_menu", "disable_desktop_switching", "blocked_window_rules", "allowed_application_ids", "version")
    DEPLOYMENT_MODE_FIELD_NUMBER: _ClassVar[int]
    SHELL_ENABLED_FIELD_NUMBER: _ClassVar[int]
    USER_SELF_LOGIN_ENABLED_FIELD_NUMBER: _ClassVar[int]
    LOCK_AFTER_SESSION_FIELD_NUMBER: _ClassVar[int]
    RESTART_AFTER_SESSION_FIELD_NUMBER: _ClassVar[int]
    HIDDEN_DRIVES_FIELD_NUMBER: _ClassVar[int]
    BLOCK_EXTERNAL_STORAGE_FIELD_NUMBER: _ClassVar[int]
    DISABLE_START_MENU_FIELD_NUMBER: _ClassVar[int]
    DISABLE_DESKTOP_SWITCHING_FIELD_NUMBER: _ClassVar[int]
    BLOCKED_WINDOW_RULES_FIELD_NUMBER: _ClassVar[int]
    ALLOWED_APPLICATION_IDS_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    deployment_mode: str
    shell_enabled: bool
    user_self_login_enabled: bool
    lock_after_session: bool
    restart_after_session: bool
    hidden_drives: _containers.RepeatedScalarFieldContainer[str]
    block_external_storage: bool
    disable_start_menu: bool
    disable_desktop_switching: bool
    blocked_window_rules: _containers.RepeatedScalarFieldContainer[str]
    allowed_application_ids: _containers.RepeatedScalarFieldContainer[str]
    version: int
    def __init__(self, deployment_mode: _Optional[str] = ..., shell_enabled: _Optional[bool] = ..., user_self_login_enabled: _Optional[bool] = ..., lock_after_session: _Optional[bool] = ..., restart_after_session: _Optional[bool] = ..., hidden_drives: _Optional[_Iterable[str]] = ..., block_external_storage: _Optional[bool] = ..., disable_start_menu: _Optional[bool] = ..., disable_desktop_switching: _Optional[bool] = ..., blocked_window_rules: _Optional[_Iterable[str]] = ..., allowed_application_ids: _Optional[_Iterable[str]] = ..., version: _Optional[int] = ...) -> None: ...

class ListWorkstationGroupsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListWorkstationGroupsResponse(_message.Message):
    __slots__ = ("groups",)
    GROUPS_FIELD_NUMBER: _ClassVar[int]
    groups: _containers.RepeatedCompositeFieldContainer[WorkstationGroup]
    def __init__(self, groups: _Optional[_Iterable[_Union[WorkstationGroup, _Mapping]]] = ...) -> None: ...

class UpsertWorkstationGroupRequest(_message.Message):
    __slots__ = ("id", "name", "theme", "lockdown_policy")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    THEME_FIELD_NUMBER: _ClassVar[int]
    LOCKDOWN_POLICY_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    theme: str
    lockdown_policy: WorkstationLockdownPolicy
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., theme: _Optional[str] = ..., lockdown_policy: _Optional[_Union[WorkstationLockdownPolicy, _Mapping]] = ...) -> None: ...

class RegisterWorkstationRequest(_message.Message):
    __slots__ = ("device_id", "name", "group_id", "position", "client_version", "capabilities")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    CLIENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    name: str
    group_id: str
    position: int
    client_version: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, device_id: _Optional[str] = ..., name: _Optional[str] = ..., group_id: _Optional[str] = ..., position: _Optional[int] = ..., client_version: _Optional[str] = ..., capabilities: _Optional[_Iterable[str]] = ...) -> None: ...

class HeartbeatRequest(_message.Message):
    __slots__ = ("device_id", "client_version", "capabilities")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    client_version: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, device_id: _Optional[str] = ..., client_version: _Optional[str] = ..., capabilities: _Optional[_Iterable[str]] = ...) -> None: ...

class ListWorkstationsRequest(_message.Message):
    __slots__ = ("group_id",)
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    group_id: str
    def __init__(self, group_id: _Optional[str] = ...) -> None: ...

class ListWorkstationsResponse(_message.Message):
    __slots__ = ("workstations",)
    WORKSTATIONS_FIELD_NUMBER: _ClassVar[int]
    workstations: _containers.RepeatedCompositeFieldContainer[Workstation]
    def __init__(self, workstations: _Optional[_Iterable[_Union[Workstation, _Mapping]]] = ...) -> None: ...

class DisableWorkstationRequest(_message.Message):
    __slots__ = ("workstation_id", "reason")
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    workstation_id: str
    reason: str
    def __init__(self, workstation_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class WorkstationCommand(_message.Message):
    __slots__ = ("id", "workstation_id", "command_type", "payload_json", "idempotency_key", "status", "created_at", "acknowledged_at", "acknowledgement_message", "expires_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    ACKNOWLEDGED_AT_FIELD_NUMBER: _ClassVar[int]
    ACKNOWLEDGEMENT_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    workstation_id: str
    command_type: str
    payload_json: str
    idempotency_key: str
    status: WorkstationCommandStatus
    created_at: _timestamp_pb2.Timestamp
    acknowledged_at: _timestamp_pb2.Timestamp
    acknowledgement_message: str
    expires_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., workstation_id: _Optional[str] = ..., command_type: _Optional[str] = ..., payload_json: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., status: _Optional[_Union[WorkstationCommandStatus, str]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., acknowledged_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., acknowledgement_message: _Optional[str] = ..., expires_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class DispatchCommandRequest(_message.Message):
    __slots__ = ("workstation_id", "command_type", "payload_json", "idempotency_key")
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    workstation_id: str
    command_type: str
    payload_json: str
    idempotency_key: str
    def __init__(self, workstation_id: _Optional[str] = ..., command_type: _Optional[str] = ..., payload_json: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class WatchCommandsRequest(_message.Message):
    __slots__ = ("device_id",)
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    def __init__(self, device_id: _Optional[str] = ...) -> None: ...

class AcknowledgeCommandRequest(_message.Message):
    __slots__ = ("command_id", "device_id", "success", "message")
    COMMAND_ID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    command_id: str
    device_id: str
    success: bool
    message: str
    def __init__(self, command_id: _Optional[str] = ..., device_id: _Optional[str] = ..., success: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...
