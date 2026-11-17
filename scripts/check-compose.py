"""Validate both Compose configurations without containers or local secrets."""

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
                "GAMECLUB_DB_PASSWORD",
                "GAMECLUB_JWT_SECRET",
                "GAMECLUB_DEV_OPERATOR_PASSWORD",
                "GAMECLUB_DEVICE_BOOTSTRAP_TOKEN",
                "GAMECLUB_GRAFANA_ADMIN_PASSWORD",
                "GAMECLUB_V2_SNAPSHOT_SIGNING_KEY_ID",
                "GAMECLUB_V2_SNAPSHOT_SIGNING_PRIVATE_KEY_B64",
                "STEAM_GUEST_DB_PASSWORD",
                "STEAM_GUEST_MASTER_KEY",
                "STEAM_GUEST_ADMIN_KEY",
                "STEAM_GUEST_STATION_KEY_PEPPER",
            )
        }
    )

    def config_for(filename: str, extra: dict[str, str] | None = None) -> dict:
        source = (root / filename).read_text()
        assert "!reset" not in source and "!override" not in source
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                "/dev/null",
                "-f",
                filename,
                "config",
                "--format",
                "json",
            ],
            cwd=root,
            env={**environment, **(extra or {})},
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    config = config_for("compose.deploy.yml")
    local = config_for("compose.local.yml")
    assert set(local["services"]) == set(config["services"])
    assert local["name"] == "gameshell"  # Preserve existing Linux developer volumes.
    assert "build" in local["services"]["frontend"]
    assert "build" in local["services"]["backend-http"]
    assert all("extends" not in service for service in config["services"].values())
    for name, service in local["services"].items():
        deployed = config["services"][name]
        for key in ("command", "depends_on", "healthcheck", "restart"):
            local_value = service.get(key)
            deploy_value = deployed.get(key)
            if (name, key) == ("backend-http", "command"):
                local_value, deploy_value = local_value.copy(), deploy_value.copy()
                for stack, command in ((local, local_value), (config, deploy_value)):
                    frontend = stack["services"]["frontend"]
                    proxy_ip = frontend["networks"]["operator-proxy"]["ipv4_address"]
                    option = command.index("--forwarded-allow-ips")
                    assert command[option + 1] == proxy_ip, (stack["name"], proxy_ip)
                    del command[option : option + 2]
            assert deploy_value == local_value, (name, key)
    lan = config_for(
        "compose.deploy.yml",
        {
            "HUBSHELL_BIND_HOST": "192.168.0.21",
        },
    )
    assert all(
        p["host_ip"] == "192.168.0.21"
        for service in lan["services"].values()
        for p in service.get("ports", [])
    )
    assert config["name"] == "hubshell"
    for deployment, host in ((config, "127.0.0.1"), (lan, "192.168.0.21")):
        (port,) = deployment["services"]["grafana"]["ports"]
        assert (port["host_ip"], port["published"], port["target"]) == (host, "3300", 3000)
    assert all("build" not in service for service in config["services"].values())
    assert all(volume["name"].startswith("hubshell_") for volume in config["volumes"].values())
    assert config["services"]["backend-http"]["image"] == images["HUBSHELL_BACKEND_IMAGE"]
    assert config["services"]["backend-http"]["environment"]["GAMECLUB_CLIENT_RELEASE_ROOT"] == (
        "/var/lib/hubshell/client-releases"
    )
    assert config["services"]["backend-http"]["environment"][
        "GAMECLUB_CLIENT_RELEASE_PUBLIC_KEY"
    ] == ("/var/lib/hubshell/client-releases/trusted-public-key.pem")
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
    print(
        "Local/deploy Compose: services, dependencies, digest images, "
        "ports and named volumes verified."
    )


if __name__ == "__main__":
    main()
