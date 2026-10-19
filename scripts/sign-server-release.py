"""Bind immutable server images to the signed client release in CI."""

import argparse
import json
import subprocess
from pathlib import Path

from client_release import digest, parse_images, verify_signature


def sign_server_release(directory: Path, signing_key: Path) -> None:
    client = json.loads((directory / "release.json").read_bytes())
    value = {
        "schemaVersion": 1,
        "releaseId": client["releaseId"],
        "commit": client["commit"],
        "images": parse_images((directory / "images.env").read_text()),
    }
    path = directory / "server-release.json"
    with path.open("xb") as output:
        output.write(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
    signature = directory / "server-release.json.sig"
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(signing_key),
            "-out",
            str(signature),
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    verify_signature(path, signature, directory / "release-public-key.pem")
    with (directory / "SHA256SUMS").open("a") as checksums:
        for artifact in (directory / "images.env", path, signature):
            checksums.write(f"{digest(artifact)}  {artifact.name}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path, required=True)
    args = parser.parse_args()
    sign_server_release(args.directory, args.signing_key)
