"""Validate isolated TrueNAS copy without starting containers or reading local .env."""

import json
import os
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GAMECLUB_", "STEAM_GUEST_", "HUBSHELL_"))
    }
    images = {
        f"HUBSHELL_{component}_IMAGE": (
            f"ghcr.io/danielbarutov/hubshell/{component.lower().replace('_', '-')}"
            f"@sha256:{digit * 64}"
        )
        for component, digit in [("BACKEND", "a"), ("FRONTEND", "b"), ("STEAM_GUEST", "c")]
    }
    environment.update(images)
    environment.update(
        {
            key: "validation-only"
            for key in (
                "STEAM_GUEST_MASTER_KEY",
                "STEAM_GUEST_ADMIN_KEY",
                "STEAM_GUEST_STATION_KEY_PEPPER",
            )
        }
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "/dev/null",
            "-f",
            "compose.truenas.yaml",
            "config",
            "--format",
            "json",
        ],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    config = json.loads(result.stdout)
    assert config["name"] == "hubshell-test"
    assert all("build" not in service for service in config["services"].values())
    assert all(volume["name"].startswith("hubshell-test_") for volume in config["volumes"].values())
    assert config["services"]["backend-http"]["image"] == images["HUBSHELL_BACKEND_IMAGE"]
    assert config["services"]["backend-http"]["environment"]["GAMECLUB_CLIENT_RELEASE_ROOT"] == (
        "/var/lib/hubshell/client-releases"
    )
    assert any(
        mount["source"] == "gameclub-client-releases" and mount.get("read_only") is True
        for mount in config["services"]["backend-http"]["volumes"]
    )
    assert config["services"]["frontend"]["image"] == images["HUBSHELL_FRONTEND_IMAGE"]
    assert config["services"]["steam-guest-server"]["image"] == images["HUBSHELL_STEAM_GUEST_IMAGE"]
    assert all(
        port["host_ip"] == "127.0.0.1"
        for service in config["services"].values()
        for port in service.get("ports", [])
    )
    assert not config["services"]["postgres"].get("ports")
    assert not config["services"]["redis"].get("ports")
    assert not config["services"]["kafka"].get("ports")
    print("TrueNAS Compose: isolated volumes, no builds, digest images, loopback ports verified.")


if __name__ == "__main__":
    main()
