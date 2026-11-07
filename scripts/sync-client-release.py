"""Publish client updates matching the running Dockhand server; safe for periodic NAS jobs."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import uuid
from pathlib import Path

from cd_http import JsonApi
from client_release import IMAGE_ROOT, download_release, publish_mirror_key, release_id
from client_update_cd import write_json

PREFIX = "/api/v1/client-updates"
RELEASE_LABEL = "io.hubshell.release-id"


def docker_json(*args: str):
    result = subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=30
    )
    return json.loads(result.stdout)


def running_server() -> tuple[str, Path, list[dict]]:
    containers = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            "label=com.docker.compose.project=hubshell",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.split()
    if not containers:
        raise ValueError("The hubshell Docker project is not running")
    values = docker_json("inspect", *containers)
    primary = [
        item
        for item in values
        if item["Config"].get("Labels", {}).get("com.docker.compose.service") == "backend-http"
    ]
    if len(primary) != 1:
        raise ValueError("Expected exactly one backend-http container")
    backend = primary[0]
    images = docker_json("image", "inspect", backend["Image"])
    version = release_id(images[0]["Config"].get("Labels", {}).get(RELEASE_LABEL, ""))
    mounts = [
        item
        for item in backend.get("Mounts", [])
        if item.get("Destination") == "/var/lib/hubshell/client-releases"
    ]
    if len(mounts) != 1:
        raise ValueError("Backend release mirror mount is missing")
    mirror = Path(mounts[0]["Source"])
    if not mirror.is_absolute() or mirror.is_symlink() or not mirror.is_dir():
        raise ValueError("Run the sync job on the Docker host with access to its mirror volume")
    return version, mirror, values


def require_running_bundle(containers: list[dict], bundle: dict) -> None:
    expected = bundle["server"]["images"]
    services = {"backend-http", "backend-grpc", "frontend", "steam-guest-server"}
    service_images = {
        "backend-http": "HUBSHELL_BACKEND_IMAGE",
        "backend-grpc": "HUBSHELL_BACKEND_IMAGE",
        "frontend": "HUBSHELL_FRONTEND_IMAGE",
        "steam-guest-server": "HUBSHELL_STEAM_GUEST_IMAGE",
    }
    seen = set()
    images = {}
    for container in containers:
        labels = container["Config"].get("Labels", {})
        service = labels.get("com.docker.compose.service")
        if (
            service == "backend-migrate"
            or labels.get("com.docker.compose.oneoff", "").lower() == "true"
        ):
            continue
        reference = container["Config"]["Image"]
        if not reference.startswith(IMAGE_ROOT + "/"):
            if service in services:
                raise ValueError("Application service uses an unapproved image")
            continue
        if service in service_images and reference != expected[service_images[service]]:
            raise ValueError("Application service differs from its signed component")
        if reference not in expected.values():
            raise ValueError("Running stack differs from the signed server release")
        state = container["State"]
        if (
            not state.get("Running")
            or state.get("Health", {}).get("Status", "healthy") != "healthy"
        ):
            raise ValueError("Application containers must be running and healthy")
        image_id = container["Image"]
        if image_id not in images:
            images[image_id] = docker_json("image", "inspect", image_id)[0]
        actual = images[image_id]
        if (
            reference not in actual.get("RepoDigests", [])
            or actual["Config"].get("Labels", {}).get(RELEASE_LABEL)
            != bundle["client"]["releaseId"]
        ):
            raise ValueError("Actual application image does not match the signed release")
        seen.add(service)
    if not services <= seen:
        raise ValueError("Required application services are missing")


def publish_assignment(api, bundle: dict, directory: Path, accepted: list[str]) -> dict:
    target = bundle["client"]
    desired = {
        "release_id": target["releaseId"],
        "executable_sha256": target["executableSha256"],
        "accepted_release_ids": sorted(set([target["releaseId"], *accepted])),
    }
    if len(desired["accepted_release_ids"]) > 32:
        raise ValueError("Too many compatible releases")
    for item in desired["accepted_release_ids"]:
        release_id(item)

    def matches(policy):
        return policy is not None and all(
            policy.get(key) == value for key, value in desired.items()
        )

    if api.request("GET", "/health/ready").get("status") != "ready":
        raise ValueError("Backend is not ready")
    current = api.request("GET", PREFIX + "/policy")["policy"]
    state_path = directory / "assignment.json"
    if state_path.is_symlink():
        raise ValueError("Assignment journal cannot be a symlink")
    if matches(current):
        write_json(
            state_path, {**desired, "operation_id": current["operation_id"], "published": True}
        )
        return current
    saved = json.loads(state_path.read_bytes()) if state_path.exists() else None
    if saved is not None and not saved.get("published"):
        if not matches(saved):
            raise ValueError("Resume the pending assignment before changing its compatibility list")
        operation = saved["operation_id"]
    else:
        operation = str(uuid.uuid4())
    write_json(state_path, {**desired, "operation_id": operation, "published": False})
    response = api.request(
        "POST",
        PREFIX + "/policy",
        {
            "operation_id": operation,
            "release_id": desired["release_id"],
            "accepted_release_ids": [
                item for item in desired["accepted_release_ids"] if item != desired["release_id"]
            ],
        },
    )
    confirmed = api.request("GET", PREFIX + "/policy")["policy"]
    if not matches(response) or not matches(confirmed) or confirmed["operation_id"] != operation:
        raise ValueError("Release assignment changed concurrently; inspect the backend policy")
    write_json(state_path, {**desired, "operation_id": operation, "published": True})
    return confirmed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--backend", default="http://127.0.0.1:8100")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--accepted-release-id", action="append", default=[])
    args = parser.parse_args()
    os.umask(0o077)
    if args.job_root.is_symlink():
        raise ValueError("Sync job-root cannot be a symlink")
    args.job_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.job_root.stat().st_mode & 0o077:
        raise ValueError("Sync job-root must be private (chmod 700)")
    descriptor = os.open(
        args.job_root / ".sync.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("HubShell client sync is already running")
            return 0
        version, mirror, containers = running_server()
        bundle = download_release(version, mirror, args.public_key)
        observed_version, observed_mirror, containers = running_server()
        if (observed_version, observed_mirror) != (version, mirror):
            raise ValueError("Server changed during download; retry after deployment finishes")
        require_running_bundle(containers, bundle)
        publish_mirror_key(mirror, args.public_key)
        directory = args.job_root / version
        if directory.is_symlink():
            raise ValueError("Sync release directory cannot be a symlink")
        directory.mkdir(exist_ok=True, mode=0o700)
        api = JsonApi(args.backend, args.token_file, refresh=True)
        policy = publish_assignment(api, bundle, directory, args.accepted_release_id)
        print(f"Published client {policy['release_id']}; PCs update independently")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print("Client sync failed: " + str(error))
        raise SystemExit(1) from None
    except Exception as error:
        print("Client sync failed: " + type(error).__name__)
        raise SystemExit(1) from None
