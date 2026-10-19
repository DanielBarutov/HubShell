"""CD phase advancement and human/machine reports; the backend owns admission."""

from __future__ import annotations

import datetime
import json
import os
import urllib.error
from collections.abc import Callable
from pathlib import Path


def ready(value: dict, now: datetime.datetime) -> bool:
    targets = value["targets"]
    if not targets:
        return False
    for device in targets:
        report = value["reports"].get(device)
        if report is None or report["round_id"] != value["round_id"]:
            return False
        age = (
            now - datetime.datetime.fromisoformat(report["received_at"].replace("Z", "+00:00"))
        ).total_seconds()
        if (
            not 0 <= age <= 30
            or report["stage"] != "ready"
            or not report["ready"]
            or report["active_session"]
            or report["pending_facts"] != 0
        ):
            return False
    return True


def succeeded(value: dict, device: str) -> bool:
    report = value["reports"].get(device)
    return bool(
        report
        and report["round_id"] == value["round_id"]
        and report["stage"] == "installed"
        and report["installed_sha256"] == value["executable_sha256"]
        and value["gui_confirmations"].get(device) == value["release_id"]
    )


def advance(
    value: dict,
    post: Callable[[str], dict],
    update_server: Callable[[dict], None],
    now: datetime.datetime,
) -> dict:
    """One resumable step. A 409 means wait; failures never clear the admission barrier."""
    phase = value["phase"]
    if phase in {"failed", "completed"}:
        return value
    try:
        if phase == "polling" and ready(value, now):
            return post("prepare")
        if phase == "preparing" and ready(value, now):
            if not value["server_ready"]:
                update_server(value)
                # Backend persists this only after backup/migration/readiness all succeeded.
                return post("server-ready")
            return post("authorize")
        if (
            phase == "authorized"
            and value["targets"]
            and all(succeeded(value, device) for device in value["targets"])
        ):
            return post("finish")
    except urllib.error.HTTPError as error:
        if error.code != 409:
            raise
    return value


def report(value: dict, now: datetime.datetime, error: str | None = None) -> dict:
    devices = []
    for device, workstation in sorted(value["targets"].items()):
        current = value["reports"].get(device)
        if succeeded(value, device):
            status = "confirmed"
        elif current is None or current["round_id"] != value["round_id"]:
            status = "unreachable"
        elif current["stage"] in {"failed", "rolled_back"}:
            status = current["stage"]
        else:
            received = datetime.datetime.fromisoformat(
                current["received_at"].replace("Z", "+00:00")
            )
            age = (now - received).total_seconds()
            if not 0 <= age <= 30:
                status = "unreachable"
            elif current["active_session"]:
                status = "active_session"
            elif current["pending_facts"]:
                status = "pending_facts"
            elif not current["ready"]:
                status = "not_ready"
            else:
                status = "waiting_gui" if current["stage"] == "installed" else current["stage"]
        devices.append(
            {
                "device_id": device,
                "workstation_id": workstation,
                "status": status,
                "old_release_id": value.get("old_releases", {}).get(device),
                "target_release_id": value["release_id"],
                "running_release_id": current.get("running_release_id") if current else None,
                "received_at": current["received_at"] if current else None,
                "error_code": current.get("error_code") if current else None,
                "rollback": current is not None and current["stage"] == "rolled_back",
            }
        )
    confirmed = sum(item["status"] == "confirmed" for item in devices)
    success = bool(devices) and confirmed == len(devices) and value["phase"] == "completed"
    return {
        "deployment_id": value["id"],
        "operation_id": value["operation_id"],
        "release_id": value["release_id"],
        "round_id": value["round_id"],
        "phase": value["phase"],
        "reported_at": now.isoformat(),
        "confirmed": confirmed,
        "total": len(devices),
        "success": success,
        "error": error,
        "devices": devices,
    }


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".new")
    if temporary.is_symlink() or path.is_symlink():
        raise ValueError("CD state/report cannot be a symlink")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, sort_keys=True, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def save_report(
    directory: Path, value: dict, now: datetime.datetime, error: str | None = None
) -> dict:
    summary = report(value, now, error)
    write_json(directory / "deployment.json", value)
    write_json(directory / "report.json", summary)
    lines = [
        f"HubShell {summary['release_id']}: {summary['phase']}",
        f"Confirmed PCs: {summary['confirmed']}/{summary['total']}",
        f"Success: {str(summary['success']).lower()}",
    ]
    if error:
        lines.append(f"CD error: {error}")
    lines.extend(
        f"{device['device_id']}: {device['status']} ({device['error_code'] or '-'})"
        for device in summary["devices"]
    )
    path = directory / "report.txt"
    if path.is_symlink():
        raise ValueError("CD report cannot be a symlink")
    path.write_text("\n".join(lines) + "\n")
    return summary
