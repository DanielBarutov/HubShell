"""Packaging contract tests using real ZIP files and OpenSSL, no extra dependencies."""

import hashlib
import json
import runpy
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

build_release = runpy.run_path(str(Path(__file__).with_name("build-client-release.py")))[
    "build_release"
]


class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="hubshell-release-test-")
        self.root = Path(self.directory.name)
        self.client = self.root / "HubShell.exe"
        self.watchdog = self.root / "HubShell.Watchdog.exe"
        executable = bytearray(4096)
        executable[:2] = b"MZ"
        executable[0x3C:0x40] = struct.pack("<I", 128)
        executable[128:134] = b"PE\0\0\x64\x86"
        self.client.write_bytes(executable)
        self.watchdog.write_bytes(executable)
        self.key = self.root / "private.pem"
        subprocess.run(
            [
                "openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
                "-out",
                str(self.key),
            ],
            check=True,
            capture_output=True,
        )
        self.key.chmod(0o600)
        self.output = self.root / "release"

    def tearDown(self):
        self.directory.cleanup()

    def build(self, release_id="v2.4.0"):
        build_release(self.client, self.watchdog, self.output, release_id, "a" * 40, self.key)

    def test_signed_archive_contains_only_executable_and_manifest_matches_bytes(self):
        self.build()
        with zipfile.ZipFile(self.output / "HubShell.zip") as archive:
            self.assertEqual(archive.namelist(), ["HubShell.exe"])
            self.assertEqual(archive.read("HubShell.exe"), self.client.read_bytes())
        manifest = json.loads((self.output / "release.json").read_bytes())
        self.assertEqual(
            manifest["executableSha256"], hashlib.sha256(self.client.read_bytes()).hexdigest()
        )
        self.assertEqual(
            manifest["archiveSha256"],
            hashlib.sha256((self.output / "HubShell.zip").read_bytes()).hexdigest(),
        )
        self.assertEqual(manifest["executableBytes"], self.client.stat().st_size)
        self.assertEqual(manifest["archiveBytes"], (self.output / "HubShell.zip").stat().st_size)
        self.assertFalse((self.output / "private.pem").exists())
        subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-verify",
                str(self.output / "release-public-key.pem"),
                "-signature",
                str(self.output / "release.json.sig"),
                str(self.output / "release.json"),
            ],
            check=True,
            capture_output=True,
        )

    def test_existing_release_and_non_x64_executable_are_rejected(self):
        self.build()
        before = (self.output / "HubShell.zip").read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(before, (self.output / "HubShell.zip").read_bytes())
        self.output = self.root / "bad-architecture"
        self.client.write_bytes(b"invalid executable")
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_setup_bundle_contains_both_executables_and_only_distribution_configuration(self):
        self.build()
        with zipfile.ZipFile(self.output / "HubShell.Setup.zip") as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    "HubShell.exe",
                    "HubShell.Watchdog.exe",
                    "install-windows.ps1",
                    "start-service.ps1",
                    "start-service.cmd",
                    "uninstall-windows.ps1",
                    "server.ini.example",
                },
            )
            self.assertEqual(archive.read("HubShell.Watchdog.exe"), self.watchdog.read_bytes())
            self.assertEqual(archive.read("HubShell.exe"), self.client.read_bytes())
            self.assertIsNone(archive.testzip())

    def test_rebuilding_the_same_inputs_produces_identical_archives_and_signatures(self):
        self.build()
        first = {
            name: (self.output / name).read_bytes()
            for name in (
                "HubShell.zip",
                "HubShell.Watchdog.zip",
                "HubShell.Setup.zip",
                "release.json",
                "release.json.sig",
            )
        }
        self.output = self.root / "repeat"
        self.build()
        for name, contents in first.items():
            self.assertEqual(contents, (self.output / name).read_bytes())

    def test_release_path_cannot_escape_output_directory(self):
        with self.assertRaises(ValueError):
            self.build("../escape")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
