"""Real signature/archive checks and atomic mirror publication without GitHub access."""

import io
import json
import runpy
import subprocess
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from client_release import (
    COMPONENTS,
    IMAGE_ROOT,
    LIMITS,
    download_release,
    parse_images,
    verify_bundle,
)


class ClientReleaseTests(unittest.TestCase):
    def setUp(self):
        scripts = Path(__file__).resolve().parent
        packaging = runpy.run_path(str(scripts / "test-build-client-release.py"))
        self.fixture = packaging["ReleasePackagingTests"]()
        self.fixture.setUp()
        self.fixture.build()
        self.directory = self.fixture.output
        self.key = self.directory / "release-public-key.pem"
        self.mirror = self.fixture.root / "mirror"
        (self.directory / "images.env").write_text(
            "".join(
                f"HUBSHELL_{component}_IMAGE={IMAGE_ROOT}/{name}@sha256:{'a' * 64}\n"
                for component, name in COMPONENTS.items()
            )
        )
        runpy.run_path(str(scripts / "sign-server-release.py"))["sign_server_release"](
            self.directory, self.fixture.key
        )

    def tearDown(self):
        self.fixture.tearDown()

    def resign(self, name):
        subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(self.fixture.key),
                "-out",
                str(self.directory / (name + ".sig")),
                str(self.directory / name),
            ],
            capture_output=True,
            check=True,
        )

    def response(self, request, timeout):
        self.assertEqual(timeout, 30)
        self.assertTrue(
            request.full_url.startswith(
                "https://github.com/DanielBarutov/HubShell/releases/download/v2.4.0/"
            )
        )
        response = io.BytesIO((self.directory / request.full_url.rsplit("/", 1)[1]).read_bytes())
        response.url = request.full_url
        return response

    def test_verified_mirror_becomes_visible_only_after_all_files_are_downloaded(self):
        def download(request, timeout):
            self.assertFalse((self.mirror / "v2.4.0").exists())
            return self.response(request, timeout)

        with patch("urllib.request.urlopen", side_effect=download) as transport:
            result = download_release("v2.4.0", self.mirror, self.key)
        self.assertEqual(transport.call_count, len(LIMITS))
        final = self.mirror / "v2.4.0"
        self.assertEqual(set(path.name for path in final.iterdir()), set(LIMITS))
        self.assertEqual(verify_bundle(final, "v2.4.0", self.key), result)
        with patch("urllib.request.urlopen") as transport:
            self.assertEqual(download_release("v2.4.0", self.mirror, self.key), result)
            transport.assert_not_called()

    def test_incomplete_download_never_exposes_release_directory(self):
        def download(request, timeout):
            if request.full_url.endswith("HubShell.zip"):
                raise urllib.error.URLError("interrupted")
            return self.response(request, timeout)

        with patch("urllib.request.urlopen", side_effect=download):
            with self.assertRaises(urllib.error.URLError):
                download_release("v2.4.0", self.mirror, self.key)
        self.assertEqual(list(self.mirror.iterdir()), [])

    def test_corrupt_zip_and_untrusted_signature_are_rejected(self):
        archive = self.directory / "HubShell.zip"
        archive.write_bytes(archive.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            verify_bundle(self.directory, "v2.4.0", self.key)
        signature = self.directory / "server-release.json.sig"
        signature.write_bytes(b"wrong signature")
        with self.assertRaises(subprocess.CalledProcessError):
            verify_bundle(self.directory, "v2.4.0", self.key)

    def test_signed_server_manifest_cannot_mix_commit_or_mutable_foreign_images(self):
        path = self.directory / "server-release.json"
        original = json.loads(path.read_bytes())
        for change in (
            {"commit": "b" * 40},
            {"images": {**original["images"], "HUBSHELL_BACKEND_IMAGE": "ubuntu:latest"}},
            {"releaseId": "v-other"},
        ):
            with self.subTest(change=change):
                path.write_text(json.dumps({**original, **change}))
                self.resign(path.name)
                with self.assertRaises(ValueError):
                    verify_bundle(self.directory, "v2.4.0", self.key)

    def test_image_environment_is_parsed_without_shell_or_extra_keys(self):
        original = (self.directory / "images.env").read_text()
        self.assertEqual(len(parse_images(original)), 3)
        for suffix in ("X=$(touch unwanted)\n", original.splitlines()[0] + "\n"):
            with self.assertRaises(ValueError):
                parse_images(original + suffix)
        with self.assertRaises(ValueError):
            parse_images(original.replace("@sha256:" + "a" * 64, ":latest"))

    def test_unsafe_release_or_linked_mirror_is_rejected_without_network(self):
        with patch("urllib.request.urlopen") as transport:
            with self.assertRaises(ValueError):
                download_release("../escape", self.mirror, self.key)
            self.mirror.symlink_to(self.directory, target_is_directory=True)
            with self.assertRaises(ValueError):
                download_release("v2.4.0", self.mirror, self.key)
            transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
