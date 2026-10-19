"""Trusted release verification and immutable LAN mirror, using stdlib and OpenSSL."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

IMAGE_ROOT = "ghcr.io/danielbarutov/hubshell"
COMPONENTS = {"BACKEND": "backend", "FRONTEND": "frontend", "STEAM_GUEST": "steam-guest"}
RELEASE_ROOT = "https://github.com/DanielBarutov/HubShell/releases/download"
LIMITS = {
    "release.json": 16384,
    "release.json.sig": 2048,
    "server-release.json": 16384,
    "server-release.json.sig": 2048,
    "HubShell.zip": 99_999_999,
}


def release_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("Invalid release id")
    return value


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def parse_images(contents: str) -> dict[str, str]:
    images = {}
    for line in contents.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key in images:
            raise ValueError("Invalid or repeated image definition")
        images[key] = value
    validate_images(images)
    return images


def validate_images(images: dict[str, str]) -> None:
    if not isinstance(images, dict) or set(images) != {
        f"HUBSHELL_{name}_IMAGE" for name in COMPONENTS
    }:
        raise ValueError("Release must contain exactly the three HubShell images")
    for component, name in COMPONENTS.items():
        value = images[f"HUBSHELL_{component}_IMAGE"]
        if not isinstance(value, str) or not re.fullmatch(
            re.escape(f"{IMAGE_ROOT}/{name}@sha256:") + "[a-f0-9]{64}", value
        ):
            raise ValueError("Image must use the approved repository and immutable digest")


def verify_signature(manifest: Path, signature: Path, public_key: Path) -> None:
    key_info = subprocess.run(
        ["openssl", "rsa", "-pubin", "-in", str(public_key), "-text", "-noout"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    bits = re.search(r"\((\d+) bit\)", key_info)
    if bits is None or int(bits.group(1)) < 2048:
        raise ValueError("The pinned key must be RSA with at least 2048 bits")
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(public_key),
            "-signature",
            str(signature),
            str(manifest),
        ],
        capture_output=True,
        check=True,
    )


def verify_bundle(directory: Path, expected_release: str, public_key: Path) -> dict:
    release_id(expected_release)
    for name, limit in LIMITS.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise ValueError("Missing, linked or oversized release artifact")
    for name in ("release.json", "server-release.json"):
        verify_signature(directory / name, directory / (name + ".sig"), public_key)
    client = json.loads((directory / "release.json").read_bytes())
    server = json.loads((directory / "server-release.json").read_bytes())
    if (
        client.get("schemaVersion") != 1
        or client.get("releaseId") != expected_release
        or client.get("runtime") != "win-x64"
        or client.get("executableName") != "HubShell.exe"
        or not re.fullmatch("[a-f0-9]{40}", client.get("commit", ""))
        or not re.fullmatch("[a-f0-9]{64}", client.get("executableSha256", ""))
        or not re.fullmatch("[a-f0-9]{64}", client.get("archiveSha256", ""))
        or type(client.get("executableBytes")) is not int
        or not 0 < client["executableBytes"] <= 536_870_912
    ):
        raise ValueError("Invalid client release metadata")
    for name in ("Updater", "Backend"):
        lower, upper = client.get(f"min{name}Protocol"), client.get(f"max{name}Protocol")
        if type(lower) is not int or type(upper) is not int or not 1 <= lower <= 1 <= upper:
            raise ValueError("Incompatible release protocol")
    if (
        set(server) != {"schemaVersion", "releaseId", "commit", "images"}
        or server["schemaVersion"] != 1
        or server["releaseId"] != expected_release
        or server["commit"] != client["commit"]
    ):
        raise ValueError("Server and client must belong to the same signed release")
    validate_images(server["images"])
    archive_path = directory / "HubShell.zip"
    if (
        type(client.get("archiveBytes")) is not int
        or client["archiveBytes"] != archive_path.stat().st_size
        or digest(archive_path) != client["archiveSha256"]
    ):
        raise ValueError("Client archive differs from signed metadata")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.namelist() != ["HubShell.exe"]:
            raise ValueError("Client archive must contain only HubShell.exe")
        info = archive.infolist()[0]
        if (
            info.file_size != client["executableBytes"]
            or (info.external_attr >> 16) & 0o170000 == 0o120000
        ):
            raise ValueError("Invalid executable archive entry")
        with archive.open(info) as executable:
            if hashlib.file_digest(executable, "sha256").hexdigest() != client["executableSha256"]:
                raise ValueError("Client executable differs from signed metadata")
    return {"client": client, "server": server}


def download_release(version: str, mirror: Path, public_key: Path) -> dict:
    release_id(version)
    mirror.mkdir(parents=True, exist_ok=True)
    if mirror.is_symlink():
        raise ValueError("Release mirror cannot be a symlink")
    final = mirror / version
    if final.exists():
        if final.is_symlink():
            raise ValueError("Release directory cannot be a symlink")
        return verify_bundle(final, version, public_key)
    with tempfile.TemporaryDirectory(prefix=".incoming-", dir=mirror) as temporary:
        staging = Path(temporary) / version
        staging.mkdir()
        for name, limit in LIMITS.items():
            url = f"{RELEASE_ROOT}/{urllib.parse.quote(version, safe='')}/{name}"
            request = urllib.request.Request(url, headers={"User-Agent": "HubShell-CD/1"})
            with urllib.request.urlopen(request, timeout=30) as response:
                if urllib.parse.urlsplit(response.url).scheme != "https":
                    raise ValueError("Release download must remain HTTPS")
                with (staging / name).open("xb") as destination:
                    size = 0
                    while chunk := response.read(81920):
                        size += len(chunk)
                        if size > limit:
                            raise ValueError("Release download exceeds size limit")
                        destination.write(chunk)
        result = verify_bundle(staging, version, public_key)
        for path in staging.iterdir():
            path.chmod(0o644)
        staging.chmod(0o755)
        # Never replace a previously published release, including a concurrent download.
        try:
            staging.rename(final)
        except OSError:
            if not final.is_dir() or final.is_symlink():
                raise
            existing = verify_bundle(final, version, public_key)
            if existing != result:
                raise ValueError("Release id already contains different signed artifacts") from None
        return result
