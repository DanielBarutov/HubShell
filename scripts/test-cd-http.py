"""Real loopback HTTP checks for credential rotation, redirect refusal and Dockhand merging."""

import json
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cd_http import JsonApi, persist_images, trusted_endpoint
from client_release import COMPONENTS, IMAGE_ROOT


class CdHttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.file = Path(self.temporary.name) / "token.json"
        self.file.write_text(
            json.dumps({"access_token": "expired", "refresh_token": "refresh-old"})
        )
        self.file.chmod(0o600)
        self.variables = [
            {"key": "DB_PASSWORD", "value": "***", "isSecret": True},
            {"key": "UNCHANGED", "value": "value", "isSecret": False},
        ]
        self.requests = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length)) if length else None
                fixture.requests.append((self.command, self.path, body))
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/target")
                    self.end_headers()
                    return
                code, result = 200, {}
                if self.path == "/api/v1/auth/refresh":
                    if body != {"refresh_token": "refresh-old"}:
                        code = 400
                    result = {
                        "access_token": "fresh",
                        "refresh_token": "refresh-new",
                        "expires_in": 900,
                    }
                elif self.path == "/api/stacks/hubshell/env?env=1":
                    if self.command == "PUT":
                        fixture.variables = body["variables"]
                    result = {"variables": fixture.variables}
                elif self.headers.get("Authorization") != "Bearer fresh":
                    code = 401
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())

            do_GET = handle_request
            do_POST = handle_request
            do_PUT = handle_request

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def test_backend_refresh_token_is_rotated_and_saved_privately(self):
        api = JsonApi(self.origin, self.file, refresh=True)
        self.assertEqual(api.request("GET", "/protected"), {})
        self.assertEqual(json.loads(self.file.read_bytes())["refresh_token"], "refresh-new")
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            [item[1] for item in self.requests],
            ["/protected", "/api/v1/auth/refresh", "/protected"],
        )

    def test_dockhand_images_are_merged_without_dropping_masked_secrets(self):
        images = {
            f"HUBSHELL_{component}_IMAGE": f"{IMAGE_ROOT}/{name}@sha256:{'a' * 64}"
            for component, name in COMPONENTS.items()
        }
        persist_images(JsonApi(self.origin, self.file), images)
        saved = {item["key"]: item for item in self.variables}
        self.assertEqual(
            saved["DB_PASSWORD"], {"key": "DB_PASSWORD", "value": "***", "isSecret": True}
        )
        self.assertEqual(saved["UNCHANGED"]["value"], "value")
        self.assertEqual(len(saved), 5)

    def test_redirect_does_not_forward_bearer_token(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            JsonApi(self.origin, self.file).request("GET", "/redirect")
        self.assertEqual(error.exception.code, 302)
        self.assertEqual([item[1] for item in self.requests], ["/redirect"])

    def test_public_http_credential_in_url_and_public_token_file_are_rejected(self):
        for value in (
            "http://8.8.8.8",
            "http://192.0.2.1",
            "https://user:secret@example.com",
            "https://example.com?secret=value",
            "http://backend.example.com",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                trusted_endpoint(value)
        self.file.chmod(0o644)
        with self.assertRaises(ValueError):
            JsonApi(self.origin, self.file).request("GET", "/protected")
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
