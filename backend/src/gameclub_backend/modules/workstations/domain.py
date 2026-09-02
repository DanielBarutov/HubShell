import dataclasses
import datetime
import enum
import re
import typing
import uuid


def normalize_mac_address(value: str) -> str:
    """Return a canonical colon-separated MAC address."""
    compact = re.sub(r"[.:-]", "", value.strip())
    if not re.fullmatch(r"[0-9a-fA-F]{12}", compact):
        raise ValueError("MAC address must contain 12 hexadecimal characters")
    hexadecimal = compact
    normalized = hexadecimal.upper()
    return ":".join(normalized[index : index + 2] for index in range(0, 12, 2))


class WorkstationStatus(enum.StrEnum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    STALE = "stale"
    OFFLINE = "offline"
    DISABLED = "disabled"


class LockdownDeploymentMode(enum.StrEnum):
    APP_GATE = "app_gate"
    ASSIGNED_ACCESS = "assigned_access"
    SHELL_LAUNCHER = "shell_launcher"


@dataclasses.dataclass(frozen=True)
class LockdownPolicy:
    deployment_mode: LockdownDeploymentMode = LockdownDeploymentMode.APP_GATE
    shell_enabled: bool = True
    user_self_login_enabled: bool = True
    lock_after_session: bool = True
    restart_after_session: bool = True
    hidden_drives: tuple[str, ...] = ()
    block_external_storage: bool = False
    disable_start_menu: bool = False
    disable_desktop_switching: bool = False
    blocked_window_rules: tuple[str, ...] = ()
    allowed_application_ids: tuple[str, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        if self.version < 1 or self.version > 1_000_000:
            raise ValueError("Lockdown policy version is invalid")
        if len(self.hidden_drives) > 26:
            raise ValueError("Lockdown policy cannot contain more than 26 drives")
        if any(
            len(drive) != 2
            or drive[0].upper() not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            or drive[1] != ":"
            for drive in self.hidden_drives
        ):
            raise ValueError("Hidden drives must use the A: format")
        for rules, message in (
            (self.blocked_window_rules, "Blocked window rules"),
            (self.allowed_application_ids, "Allowed application ids"),
        ):
            if len(rules) > 128:
                raise ValueError(f"{message} cannot contain more than 128 values")
            if any(not value.strip() or len(value) > 256 or "\x00" in value for value in rules):
                raise ValueError(f"{message} contain an invalid value")


@dataclasses.dataclass(frozen=True)
class WorkstationGroup:
    id: str
    name: str
    theme: str = "standard"
    updated_at: datetime.datetime | None = None
    manager_password_verifier: str | None = None
    lockdown_policy: LockdownPolicy = dataclasses.field(default_factory=LockdownPolicy)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("Workstation group id and name cannot be empty")
        if self.theme not in {"standard", "vip", "neon", "minimal"}:
            raise ValueError("Unsupported workstation group theme")


@dataclasses.dataclass(frozen=True)
class Workstation:
    id: uuid.UUID
    device_id: str
    name: str
    group_id: str | None = None
    position: int | None = None
    status: WorkstationStatus = WorkstationStatus.UNKNOWN
    last_seen_at: datetime.datetime | None = None
    client_version: str | None = None
    disabled_reason: str | None = None
    capabilities: tuple[str, ...] = ()
    theme: str = "standard"
    archived_at: datetime.datetime | None = None
    manager_password_verifier: str | None = None
    lockdown_policy: LockdownPolicy = dataclasses.field(default_factory=LockdownPolicy)
    mac_address: str | None = None
    installation_id: str | None = None

    def __post_init__(self) -> None:
        if not self.device_id.strip():
            raise ValueError("Device identity cannot be empty")
        if not self.name.strip():
            raise ValueError("Workstation name cannot be empty")
        if self.mac_address:
            object.__setattr__(self, "mac_address", normalize_mac_address(self.mac_address))
        if self.installation_id is not None:
            installation_id = self.installation_id.strip()
            if not installation_id or len(installation_id) > 128 or "\x00" in installation_id:
                raise ValueError("Installation identity is invalid")
            object.__setattr__(self, "installation_id", installation_id)

    def heartbeat(
        self,
        now: datetime.datetime,
        client_version: str | None = None,
        capabilities: typing.Sequence[str] | None = None,
    ) -> "Workstation":
        if self.status is WorkstationStatus.DISABLED:
            return self
        return dataclasses.replace(
            self,
            status=WorkstationStatus.ONLINE,
            last_seen_at=now,
            client_version=client_version or self.client_version,
            disabled_reason=None,
            capabilities=tuple(capabilities) if capabilities is not None else self.capabilities,
        )

    def disable(self, reason: str) -> "Workstation":
        if not reason.strip():
            raise ValueError("Disable reason cannot be empty")
        return dataclasses.replace(
            self,
            status=WorkstationStatus.DISABLED,
            disabled_reason=reason.strip(),
        )

    def enable(self) -> "Workstation":
        return dataclasses.replace(self, status=WorkstationStatus.UNKNOWN, disabled_reason=None)

    def archive(self, now: datetime.datetime) -> "Workstation":
        return dataclasses.replace(
            self,
            status=WorkstationStatus.DISABLED,
            disabled_reason="Архивировано оператором",
            archived_at=now,
        )

    def status_at(
        self,
        now: datetime.datetime,
        stale_after: datetime.timedelta,
        offline_after: datetime.timedelta,
    ) -> "Workstation":
        if self.status is WorkstationStatus.DISABLED or self.last_seen_at is None:
            return self
        age = now - self.last_seen_at
        if age >= offline_after:
            status = WorkstationStatus.OFFLINE
        elif age >= stale_after:
            status = WorkstationStatus.STALE
        else:
            status = WorkstationStatus.ONLINE
        return dataclasses.replace(self, status=status)
