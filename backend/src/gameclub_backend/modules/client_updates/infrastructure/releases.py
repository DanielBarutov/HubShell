"""Validate immutable LAN artifacts without blocking the HTTP event loop."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from gameclub_backend.application.errors import ApplicationError, ErrorCode


class LocalClientReleaseStore:
    def __init__(
        self, root: str | None, public_key: str | None, server_release_id: str | None = None
    ) -> None:
        self._root = root
        self._public_key = public_key
        self._server_release_id = server_release_id or None

    async def executable_hash(self, release_id: str) -> str:
        return await asyncio.to_thread(self._verify, release_id)

    def _verify(self, release_id: str) -> str:
        if self._root is None or self._public_key is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "Trusted release mirror is not configured"
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release_id):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid release id")
        if self._server_release_id is not None and release_id != self._server_release_id:
            raise ApplicationError(
                ErrorCode.CONFLICT, "Client release differs from the running server"
            )
        try:
            root = Path(self._root)
            directory = root / release_id
            if root.is_symlink() or directory.is_symlink():
                raise ValueError("Linked release directory")
            paths = {
                name: directory / name
                for name in ("release.json", "release.json.sig", "HubShell.zip")
            }
            for name, limit in (
                ("release.json", 16384),
                ("release.json.sig", 2048),
                ("HubShell.zip", 99_999_999),
            ):
                path = paths[name]
                if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
                    raise ValueError("Missing or invalid release file")
            key = serialization.load_pem_public_key(Path(self._public_key).read_bytes())
            if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
                raise ValueError("Invalid pinned RSA key")
            manifest = paths["release.json"].read_bytes()
            key.verify(
                paths["release.json.sig"].read_bytes(),
                manifest,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            value = json.loads(manifest)
            if (
                value.get("schemaVersion") != 1
                or value.get("releaseId") != release_id
                or value.get("runtime") != "win-x64"
                or value.get("executableName") != "HubShell.exe"
                or not re.fullmatch("[a-f0-9]{64}", value.get("executableSha256", ""))
                or not re.fullmatch("[a-f0-9]{64}", value.get("archiveSha256", ""))
                or type(value.get("archiveBytes")) is not int
                or value["archiveBytes"] != paths["HubShell.zip"].stat().st_size
                or type(value.get("executableBytes")) is not int
                or not 0 < value["executableBytes"] <= 536_870_912
            ):
                raise ValueError("Invalid signed client metadata")
            for component in ("Backend", "Updater"):
                lower, upper = (
                    value.get(f"min{component}Protocol"),
                    value.get(f"max{component}Protocol"),
                )
                if type(lower) is not int or type(upper) is not int or not 1 <= lower <= 1 <= upper:
                    raise ValueError("Incompatible release protocol")
            with paths["HubShell.zip"].open("rb") as contents:
                if hashlib.file_digest(contents, "sha256").hexdigest() != value["archiveSha256"]:
                    raise ValueError("Archive hash mismatch")
            with zipfile.ZipFile(paths["HubShell.zip"]) as archive:
                if archive.namelist() != ["HubShell.exe"]:
                    raise ValueError("Invalid archive entries")
                info = archive.infolist()[0]
                if (
                    info.file_size != value["executableBytes"]
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError("Invalid executable entry")
                with archive.open(info) as executable:
                    if (
                        hashlib.file_digest(executable, "sha256").hexdigest()
                        != value["executableSha256"]
                    ):
                        raise ValueError("Executable hash mismatch")
            return value["executableSha256"]
        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
            InvalidSignature,
            zipfile.BadZipFile,
            RuntimeError,
        ) as error:
            raise ApplicationError(
                ErrorCode.CONFLICT, "Client release verification failed"
            ) from error
