"""Run/resume one coordinated HubShell delivery on the TrueNAS Docker host."""

from __future__ import annotations

import argparse
import datetime
import fcntl
import json
import math
import os
import re
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

from cd_http import JsonApi, persist_images
from client_release import download_release, release_id
from client_update_cd import advance, save_report, write_json
from server_deployment import ComposeServer

PREFIX = "/api/v1/client-updates"


def latest_release() -> str:
    request = urllib.request.Request(
        "https://api.github.com/repos/DanielBarutov/HubShell/releases/latest",
        headers={"User-Agent": "HubShell-CD/1", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(65537)
        if len(data) > 65536:
            raise ValueError("GitHub release metadata exceeds size limit")
        return release_id(json.loads(data)["tag_name"])


def select_release(root: Path, requested: str | None) -> str:
    cursor = root / "active-release.json"
    previous = None
    unfinished = False
    if cursor.exists():
        previous = release_id(json.loads(cursor.read_bytes())["release_id"])
        report_path = root / previous / "report.json"
        saved = json.loads(report_path.read_bytes()) if report_path.exists() else {}
        unfinished = not (saved.get("success") is True and saved.get("phase") == "completed")
    if unfinished:
        if requested is not None and release_id(requested) != previous:
            raise ValueError("Finish the active release before selecting another one")
        return previous
    chosen = release_id(requested) if requested is not None else latest_release()
    write_json(cursor, {"release_id": chosen})
    return chosen


def run_delivery(api, server, dockhand, bundle: dict, job: Path, timeout: float) -> dict:
    target = bundle["client"]
    state_path = job / "job.json"
    if state_path.exists():
        state = json.loads(state_path.read_bytes())
        if (state["release_id"], state["executable_sha256"]) != (
            target["releaseId"],
            target["executableSha256"],
        ):
            raise ValueError("Existing CD job belongs to different release content")
    else:
        state = {
            "operation_id": str(uuid.uuid4()),
            "release_id": target["releaseId"],
            "executable_sha256": target["executableSha256"],
            "deployment_id": None,
        }
        write_json(state_path, state)
    value = None
    deadline = time.monotonic() + timeout

    def require_match(current):
        if any(
            current[key] != state[key]
            for key in ("operation_id", "release_id", "executable_sha256")
        ):
            raise ValueError("Backend deployment does not match the saved CD job")
        if state["deployment_id"] and current["id"] != state["deployment_id"]:
            raise ValueError("Backend returned another deployment")

    def post(action):
        changed = api.request("POST", f"{PREFIX}/{state['deployment_id']}/{action}", {})
        require_match(changed)
        return changed

    def update_server(current):
        def smoke():
            health = api.request("GET", "/health/ready")
            if health.get("status") != "ready":
                raise ValueError("Backend is not ready after the server stage")
            restored = api.request("GET", f"{PREFIX}/{state['deployment_id']}")
            require_match(restored)
            if restored["phase"] != "preparing" or restored["round_id"] != current["round_id"]:
                raise ValueError("The durable preparation barrier did not survive server update")

        server.update(current, smoke)
        persist_images(dockhand, bundle["server"]["images"])

    try:
        if state["deployment_id"] is None:
            value = api.request(
                "POST",
                PREFIX,
                {key: state[key] for key in ("operation_id", "release_id", "executable_sha256")},
            )
            require_match(value)
            state["deployment_id"] = str(uuid.UUID(value["id"]))
            write_json(state_path, state)
        while True:
            value = api.request("GET", f"{PREFIX}/{state['deployment_id']}")
            require_match(value)
            now = datetime.datetime.now(datetime.UTC)
            summary = save_report(job, value, now)
            if value["phase"] in {"failed", "completed"}:
                return summary
            if time.monotonic() >= deadline:
                raise TimeoutError("CD timed out; the backend deployment remains active")
            changed = advance(value, post, update_server, now)
            if changed != value:
                value = changed
                save_report(job, value, datetime.datetime.now(datetime.UTC))
            else:
                time.sleep(min(5, max(0, deadline - time.monotonic())))
    except BaseException as error:
        if value is not None:
            save_report(job, value, datetime.datetime.now(datetime.UTC), type(error).__name__)
        write_json(job / "job-error.json", {"error": type(error).__name__, **state})
        raise


def mirror_directory() -> Path:
    result = subprocess.run(
        [
            "docker",
            "volume",
            "inspect",
            "hubshell-test_gameclub-client-releases",
            "--format",
            "{{.Mountpoint}}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    path = Path(result.stdout.strip())
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        raise ValueError("Run CD on the Docker host with access to the release volume mountpoint")
    return path


def checkout_release(repository: Path, commit: str) -> None:
    if not re.fullmatch("[a-f0-9]{40}", commit):
        raise ValueError("Invalid signed release commit")

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repository, check=True, capture_output=True, text=True, timeout=120
        ).stdout.strip()

    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("CD refuses to replace a dirty repository checkout")
    if git("rev-parse", "HEAD") == commit:
        return
    origin = git("remote", "get-url", "origin").removesuffix(".git").lower()
    if origin != "https://github.com/danielbarutov/hubshell":
        raise ValueError("CD checkout must use the approved GitHub origin")
    git("fetch", "--no-tags", "origin", commit)
    git("checkout", "--detach", commit)
    if git("rev-parse", "HEAD") != commit:
        raise ValueError("Checkout does not match the signed release commit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-id", help="Default: resume the active job, then GitHub latest release"
    )
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--backend", default="http://127.0.0.1:8100")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--dockhand", required=True)
    parser.add_argument("--dockhand-token-file", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=7200)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("CD timeout must be positive")
    os.umask(0o077)
    root = args.job_root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise ValueError("CD job-root must be private (chmod 700)")
    lock_path = root / ".delivery.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("HubShell CD is already running")
            return 0
        version = select_release(root, args.release_id)
        bundle = download_release(version, mirror_directory(), args.public_key)
        repository = Path(__file__).resolve().parents[1]
        checkout_release(repository, bundle["client"]["commit"])
        if args.env_file.is_symlink() or args.env_file.stat().st_mode & 0o077:
            raise ValueError("The stack env file must be private (chmod 600)")
        job = root / version
        if job.is_symlink():
            raise ValueError("CD job cannot be a symlink")
        job.mkdir(exist_ok=True, mode=0o700)
        api = JsonApi(args.backend, args.token_file, refresh=True)
        dockhand = JsonApi(args.dockhand, args.dockhand_token_file)
        server = ComposeServer(repository, args.env_file, job, bundle["server"]["images"])
        summary = run_delivery(api, server, dockhand, bundle, job, args.timeout)
        print(
            f"{summary['phase']}: {summary['confirmed']}/{summary['total']} PCs; "
            f"report {job / 'report.json'}"
        )
        return 0 if summary["success"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # No HTTP bodies, command stderr or credential values in cron/job logs.
        print(f"HubShell CD failed: {type(error).__name__}")
        raise SystemExit(1) from None
