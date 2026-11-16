"""Poll GitHub for the latest manually requested HubShell deployment."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from cd_http import NoRedirect, private_json
from server_deployment import MaintenanceBlocked

DEPLOYMENTS = "https://api.github.com/repos/DanielBarutov/HubShell/deployments"


def github_request(token: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        DEPLOYMENTS + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "HubShell-CD",
        },
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        return json.load(response)


def run_latest(request, deploy) -> bool:
    deployments = request("?environment=production&task=hubshell%3Adeploy&per_page=1")
    if not deployments:
        return True
    deployment = deployments[0]
    sha = deployment["sha"]
    identifier = deployment["id"]
    if type(identifier) is not int or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Unexpected GitHub deployment")
    statuses = f"/{identifier}/statuses"
    current = request(statuses + "?per_page=1")
    if not current or current[0]["state"] != "queued":
        return True
    request(statuses, {"state": "in_progress", "description": "TrueNAS deployment running"})
    try:
        deploy(f"commit-{sha}")
    except MaintenanceBlocked as error:
        request(statuses, {"state": "failure", "description": str(error)})
        return False
    except Exception:
        request(statuses, {"state": "failure", "description": "See the TrueNAS deployment log"})
        raise
    request(statuses, {"state": "success", "description": "Server ready; client release assigned"})
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--dockhand", required=True)
    args = parser.parse_args()
    config = args.config_dir.resolve()
    token = private_json(config / "github-token.json")["access_token"]
    os.umask(0o077)
    lock = os.open(config / ".github-deploy.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock, "w") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0

        def deploy(version: str) -> None:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("deploy-release.py")),
                    "--independent",
                    "--release-id",
                    version,
                    "--public-key",
                    str(config / "release-public-key.pem"),
                    "--env-file",
                    str(config / "stack.env"),
                    "--job-root",
                    str(config / "jobs"),
                    "--backend",
                    args.backend,
                    "--token-file",
                    str(config / "backend-token.json"),
                    "--dockhand",
                    args.dockhand,
                    "--dockhand-token-file",
                    str(config / "dockhand-token.json"),
                ],
                check=False,
            )
            if result.returncode == 3:
                raise MaintenanceBlocked("Maintenance check blocked deployment; see TrueNAS log")
            result.check_returncode()

        return (
            0
            if run_latest(lambda path, body=None: github_request(token, path, body), deploy)
            else 1
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"GitHub deployment polling failed: {type(error).__name__}")
        raise SystemExit(1) from None
