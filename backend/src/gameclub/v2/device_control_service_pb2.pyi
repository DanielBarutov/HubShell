from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DeviceHealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class DeviceHealthResponse(_message.Message):
    __slots__ = ("service", "status", "version")
    SERVICE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    service: str
    status: str
    version: str
    def __init__(self, service: _Optional[str] = ..., status: _Optional[str] = ..., version: _Optional[str] = ...) -> None: ...

class DeviceEnrollmentRequest(_message.Message):
    __slots__ = ("mac_addresses", "installation_id")
    MAC_ADDRESSES_FIELD_NUMBER: _ClassVar[int]
    INSTALLATION_ID_FIELD_NUMBER: _ClassVar[int]
    mac_addresses: _containers.RepeatedScalarFieldContainer[str]
    installation_id: str
    def __init__(self, mac_addresses: _Optional[_Iterable[str]] = ..., installation_id: _Optional[str] = ...) -> None: ...

class DeviceEnrollmentResponse(_message.Message):
    __slots__ = ("state", "device_id", "workstation_id", "workstation_name", "access_token", "expires_in")
    STATE_FIELD_NUMBER: _ClassVar[int]
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_NAME_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_IN_FIELD_NUMBER: _ClassVar[int]
    state: str
    device_id: str
    workstation_id: str
    workstation_name: str
    access_token: str
    expires_in: int
    def __init__(self, state: _Optional[str] = ..., device_id: _Optional[str] = ..., workstation_id: _Optional[str] = ..., workstation_name: _Optional[str] = ..., access_token: _Optional[str] = ..., expires_in: _Optional[int] = ...) -> None: ...

class DeviceHeartbeatRequest(_message.Message):
    __slots__ = ("device_id", "client_version", "capabilities")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    CLIENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    CAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    client_version: str
    capabilities: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, device_id: _Optional[str] = ..., client_version: _Optional[str] = ..., capabilities: _Optional[_Iterable[str]] = ...) -> None: ...

class DeviceHeartbeatResponse(_message.Message):
    __slots__ = ("device_id", "workstation_id", "workstation_name", "group_id", "theme", "manager_password_verifier", "lockdown_policy")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_ID_FIELD_NUMBER: _ClassVar[int]
    WORKSTATION_NAME_FIELD_NUMBER: _ClassVar[int]
    GROUP_ID_FIELD_NUMBER: _ClassVar[int]
    THEME_FIELD_NUMBER: _ClassVar[int]
    MANAGER_PASSWORD_VERIFIER_FIELD_NUMBER: _ClassVar[int]
    LOCKDOWN_POLICY_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    workstation_id: str
    workstation_name: str
    group_id: str
    theme: str
    manager_password_verifier: str
    lockdown_policy: WorkstationLockdownPolicy
    def __init__(self, device_id: _Optional[str] = ..., workstation_id: _Optional[str] = ..., workstation_name: _Optional[str] = ..., group_id: _Optional[str] = ..., theme: _Optional[str] = ..., manager_password_verifier: _Optional[str] = ..., lockdown_policy: _Optional[_Union[WorkstationLockdownPolicy, _Mapping]] = ...) -> None: ...

class DeviceCommandWatchRequest(_message.Message):
    __slots__ = ("device_id",)
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    def __init__(self, device_id: _Optional[str] = ...) -> None: ...

class DeviceCommandAcknowledgementRequest(_message.Message):
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

class DeviceCommand(_message.Message):
    __slots__ = ("id", "command_type", "payload_json", "idempotency_key", "status", "acknowledgement_message", "expires_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    COMMAND_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ACKNOWLEDGEMENT_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    command_type: str
    payload_json: str
    idempotency_key: str
    status: str
    acknowledgement_message: str
    expires_at: str
    def __init__(self, id: _Optional[str] = ..., command_type: _Optional[str] = ..., payload_json: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., status: _Optional[str] = ..., acknowledgement_message: _Optional[str] = ..., expires_at: _Optional[str] = ...) -> None: ...

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
