"""Coordinated deployment: all PCs ready, one pilot, then the remaining fleet."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import re
import uuid


class DeploymentPhase(enum.StrEnum):
    POLLING = "polling"
    PREPARING = "preparing"
    AUTHORIZED = "authorized"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclasses.dataclass(frozen=True)
class DeviceUpdateReport:
    device_id: str
    round_id: uuid.UUID
    sequence: int
    instance_id: uuid.UUID
    received_at: datetime.datetime
    active_session: bool
    pending_facts: int
    ready: bool
    stage: str = "ready"
    installed_sha256: str | None = None
    error_code: str | None = None
    session_id: uuid.UUID | None = None
    last_sequence: int = 0
    last_payload_hash: str | None = None
    running_release_id: str | None = None

    def __post_init__(self) -> None:
        if self.sequence < 1 or self.pending_facts < 0 or self.received_at.tzinfo is None:
            raise ValueError("Invalid update report sequence, pending facts or timestamp")
        if (
            self.last_sequence < 0
            or (
                self.session_id is None
                and (self.last_sequence != 0 or self.last_payload_hash is not None)
            )
            or (self.last_sequence == 0 and self.last_payload_hash is not None)
            or (
                self.last_sequence > 0
                and not re.fullmatch("[a-f0-9]{64}", self.last_payload_hash or "")
            )
        ):
            raise ValueError("Invalid local financial checkpoint")
        if self.stage not in {
            "ready",
            "installing",
            "verifying",
            "installed",
            "failed",
            "rolled_back",
        }:
            raise ValueError("Invalid update report stage")
        if self.installed_sha256 is not None and not re.fullmatch(
            "[a-f0-9]{64}", self.installed_sha256
        ):
            raise ValueError("Invalid installed executable hash")
        if self.error_code is not None and not re.fullmatch("[a-z0-9_.-]{1,64}", self.error_code):
            raise ValueError("Invalid updater error code")
        if self.running_release_id is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.running_release_id
        ):
            raise ValueError("Invalid running client release")


@dataclasses.dataclass
class Deployment:
    id: uuid.UUID
    operation_id: uuid.UUID
    release_id: str
    executable_sha256: str
    targets: dict[str, uuid.UUID]
    created_by: str
    created_at: datetime.datetime
    round_id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
    phase: DeploymentPhase = DeploymentPhase.POLLING
    reports: dict[str, DeviceUpdateReport] = dataclasses.field(default_factory=dict)
    gui_confirmations: dict[str, str] = dataclasses.field(default_factory=dict)
    server_ready: bool = False
    old_releases: dict[str, str] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", self.release_id):
            raise ValueError("Invalid release id")
        if not re.fullmatch("[a-f0-9]{64}", self.executable_sha256):
            raise ValueError("Invalid release executable hash")
        if not self.targets or len(set(self.targets.values())) != len(self.targets):
            raise ValueError("Deployment must target unique workstations")
        if any(not device_id or len(device_id) > 128 for device_id in self.targets):
            raise ValueError("Invalid target device identity")
        if not self.created_by or self.created_at.tzinfo is None:
            raise ValueError("Deployment author and timezone are required")

    def report(self, report: DeviceUpdateReport) -> None:
        if report.device_id not in self.targets:
            raise ValueError("Report belongs to another device")
        if report.round_id != self.round_id:
            raise ValueError("Report belongs to an obsolete preparation round")
        if self.phase is DeploymentPhase.COMPLETED:
            return
        previous = self.reports.get(report.device_id)
        if previous is not None:
            if report.sequence < previous.sequence:
                return
            if report.sequence == previous.sequence:
                # Receipt time is server-owned and may differ on a network retry.
                if dataclasses.replace(report, received_at=previous.received_at) != previous:
                    raise ValueError("Report sequence reused with different contents")
                return
        if (
            self.phase is DeploymentPhase.AUTHORIZED
            and report.stage not in {"failed", "rolled_back"}
            and (
                report.active_session
                or report.pending_facts > 0
                or not report.ready
                or previous is None
                or report.instance_id != previous.instance_id
            )
        ):
            self.reports[report.device_id] = dataclasses.replace(
                report, stage="failed", error_code="readiness_lost"
            )
            self.phase = DeploymentPhase.FAILED
            return
        if self.phase in {DeploymentPhase.POLLING, DeploymentPhase.PREPARING}:
            if report.stage != "ready":
                raise ValueError("Installation has not been authorized")
        elif report.stage == "ready" and previous is not None and previous.stage != "ready":
            raise ValueError("Installation report cannot move backwards")
        elif report.stage in {"installing", "verifying", "installed"}:
            if previous is None or previous.instance_id != report.instance_id:
                raise ValueError("Updater instance changed after authorization")
            order = {"ready": 0, "installing": 1, "verifying": 2, "installed": 3}
            if previous.stage in order and order[report.stage] < order[previous.stage]:
                raise ValueError("Installation report cannot move backwards")
            if report.device_id != self.pilot and not self.device_succeeded(self.pilot):
                raise ValueError("Pilot has not confirmed the new client")
        if report.stage == "installed" and report.installed_sha256 != self.executable_sha256:
            raise ValueError("Installed executable does not match release")
        self.reports[report.device_id] = report
        if report.running_release_id is not None and report.running_release_id != "unknown":
            self.old_releases.setdefault(report.device_id, report.running_release_id)
        if report.stage in {"failed", "rolled_back"}:
            self.phase = DeploymentPhase.FAILED

    @property
    def pilot(self) -> str:
        return sorted(self.targets)[0]

    def all_ready(self, now: datetime.datetime, max_age_seconds: int = 30) -> bool:
        return all(
            (report := self.reports.get(device_id)) is not None
            and report.stage == "ready"
            and report.ready
            and not report.active_session
            and report.pending_facts == 0
            and 0 <= (now - report.received_at).total_seconds() <= max_age_seconds
            for device_id in self.targets
        )

    def begin_preparation(self, now: datetime.datetime) -> None:
        if self.phase is not DeploymentPhase.POLLING or not self.all_ready(now):
            raise ValueError("Every PC must be online and idle before preparation")
        self.phase = DeploymentPhase.PREPARING
        self.round_id = uuid.uuid4()
        self.reports.clear()
        self.gui_confirmations.clear()

    def retry_preparation(self) -> None:
        if self.phase is not DeploymentPhase.FAILED:
            raise ValueError("Only a failed deployment can restart preparation")
        self.phase = DeploymentPhase.PREPARING
        self.round_id = uuid.uuid4()
        self.reports.clear()
        self.gui_confirmations.clear()
        self.server_ready = False

    def authorize(self, now: datetime.datetime) -> None:
        if (
            self.phase is not DeploymentPhase.PREPARING
            or not self.server_ready
            or not self.all_ready(now)
        ):
            raise ValueError("Server and every PC must be ready in the final round")
        self.phase = DeploymentPhase.AUTHORIZED

    def may_install(self, device_id: str) -> bool:
        return (
            self.phase is DeploymentPhase.AUTHORIZED
            and (device_id == self.pilot or self.device_succeeded(self.pilot))
            and device_id in self.targets
        )

    def confirm_gui(self, device_id: str, release_id: str) -> None:
        if device_id not in self.targets or release_id != self.release_id:
            raise ValueError("Client confirmation does not match deployment")
        if self.phase not in {DeploymentPhase.AUTHORIZED, DeploymentPhase.COMPLETED}:
            raise ValueError("Deployment is not authorized")
        self.gui_confirmations[device_id] = release_id

    def device_succeeded(self, device_id: str) -> bool:
        report = self.reports.get(device_id)
        return bool(
            report
            and report.round_id == self.round_id
            and report.stage == "installed"
            and report.installed_sha256 == self.executable_sha256
            and self.gui_confirmations.get(device_id) == self.release_id
        )

    def finish(self) -> None:
        if self.phase is not DeploymentPhase.AUTHORIZED or not all(
            self.device_succeeded(device_id) for device_id in self.targets
        ):
            raise ValueError("Every PC must confirm the release before reopening the fleet")
        self.phase = DeploymentPhase.COMPLETED

    def device_status(self, device_id: str, now: datetime.datetime) -> str:
        if self.device_succeeded(device_id):
            return "confirmed"
        report = self.reports.get(device_id)
        if report is None or report.round_id != self.round_id:
            return "unreachable"
        if report.stage in {"failed", "rolled_back"}:
            return report.stage
        if not 0 <= (now - report.received_at).total_seconds() <= 30:
            return "unreachable"
        if report.active_session:
            return "active_session"
        if report.pending_facts:
            return "pending_facts"
        if not report.ready:
            return "not_ready"
        if report.stage == "installed":
            return "waiting_gui"
        return report.stage
