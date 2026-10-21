"""Create signed win-x64 update artifacts; the private key stays outside the release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def require_windows_x64(path: Path) -> None:
    with path.open("rb") as source:
        if source.read(2) != b"MZ":
            raise ValueError(f"Not a Windows executable: {path.name}")
        source.seek(0x3C)
        offset = source.read(4)
        if len(offset) != 4:
            raise ValueError("Truncated executable header")
        source.seek(struct.unpack("<I", offset)[0])
        if source.read(6) != b"PE\0\0\x64\x86":
            raise ValueError(f"Not a Windows x64 executable: {path.name}")


def build_release(
    client: Path, watchdog: Path, output: Path, release_id: str, commit: str, signing_key: Path
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release_id):
        raise ValueError("Invalid release id")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Commit must be a complete lowercase SHA-1")
    if not signing_key.is_file():
        raise ValueError("Release signing key is required")
    for executable in (client, watchdog):
        require_windows_x64(executable)
        if not 0 < executable.stat().st_size <= 536_870_912:
            raise ValueError("Executable exceeds updater size limit")
    # Refuse to republish a different artifact into an existing release directory.
    output.mkdir(parents=True, exist_ok=False)
    archives = []
    scripts = Path(__file__).resolve().parents[1] / "win-client"
    setup_files = [(client, "HubShell.exe"), (watchdog, "HubShell.Watchdog.exe")]
    setup_files.extend(
        (scripts / "scripts" / name, name)
        for name in (
            "install-windows.ps1",
            "start-service.ps1",
            "start-service.cmd",
            "uninstall-windows.ps1",
        )
    )
    setup_files.append((scripts / "server.ini.example", "server.ini.example"))
    setup_files.append((scripts / "INSTALL.txt", "README.txt"))
    packages = [
        ("HubShell.zip", [(client, "HubShell.exe")]),
        ("HubShell.Watchdog.zip", [(watchdog, "HubShell.Watchdog.exe")]),
        ("HubShell.Setup.zip", setup_files),
    ]
    for archive_name, contents in packages:
        archive_path = output / archive_name
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for source_path, name in contents:
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                with source_path.open("rb") as source, archive.open(entry, "w") as destination:
                    shutil.copyfileobj(source, destination)
        with zipfile.ZipFile(archive_path) as archive:
            if (
                archive.namelist() != [name for _, name in contents]
                or archive.testzip() is not None
            ):
                raise ValueError("Release ZIP verification failed")
            for source_path, name in contents:
                with archive.open(name) as embedded:
                    if hashlib.file_digest(embedded, "sha256").hexdigest() != sha256(source_path):
                        raise ValueError("Embedded file differs from published file")
        if archive_path.stat().st_size >= 100_000_000:
            raise ValueError(f"Archive exceeds 100 MB: {archive_path.name}")
        archives.append(archive_path)
    manifest = {
        "schemaVersion": 1,
        "releaseId": release_id,
        "commit": commit,
        "runtime": "win-x64",
        "executableName": "HubShell.exe",
        "executableSha256": sha256(client),
        "executableBytes": client.stat().st_size,
        "archiveSha256": sha256(archives[0]),
        "archiveBytes": archives[0].stat().st_size,
        "minUpdaterProtocol": 1,
        "maxUpdaterProtocol": 1,
        "minBackendProtocol": 1,
        "maxBackendProtocol": 1,
    }
    manifest_path = output / "release.json"
    manifest_path.write_bytes(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    signature = output / "release.json.sig"
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(signing_key),
            "-out",
            str(signature),
            str(manifest_path),
        ],
        check=True,
        capture_output=True,
    )
    # A successful OpenSSL command alone does not prove the key is RSA or the
    # signature matches the client's RSA/SHA-256 contract.
    public = subprocess.run(
        ["openssl", "rsa", "-in", str(signing_key), "-pubout"], check=True, capture_output=True
    ).stdout
    public_path = output / "release-public-key.pem"
    public_path.write_bytes(public)
    key_info = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", str(public_path), "-text", "-noout"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    key_bits = re.search(r"\((\d+) bit\)", key_info)
    if key_bits is None or int(key_bits.group(1)) < 2048:
        raise ValueError("Release signing key must be RSA with at least 2048 bits")

    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(public_path),
            "-signature",
            str(signature),
            str(manifest_path),
        ],
        check=True,
        capture_output=True,
    )
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in [*archives, manifest_path, signature])
    )
    (output / "commit.txt").write_text(commit + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--watchdog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    args = parser.parse_args()
    build_release(
        args.client, args.watchdog, args.output, args.release_id, args.commit, args.signing_key
    )


if __name__ == "__main__":
    main()
