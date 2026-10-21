"""Bounded authenticated HTTP for the local CD executor; credentials never enter reports."""

from __future__ import annotations

import ipaddress
import json
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from client_update_cd import write_json


def trusted_endpoint(value: str) -> str:
    endpoint = urllib.parse.urlsplit(value)
    if (
        endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in {"", "/"}
        or not endpoint.hostname
    ):
        raise ValueError("CD endpoint must be a bare origin without credentials")
    if endpoint.scheme == "http":
        try:
            address = ipaddress.ip_address(endpoint.hostname)
        except ValueError:
            if endpoint.hostname != "localhost":
                raise ValueError("Plain HTTP requires a private IP or localhost") from None
        else:
            networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
            if not address.is_loopback and not any(
                address in ipaddress.ip_network(network) for network in networks
            ):
                raise ValueError("Plain HTTP requires a private IP or loopback")
    elif endpoint.scheme != "https":
        raise ValueError("CD endpoint must use HTTP in the LAN or HTTPS")
    return value.rstrip("/")


def private_json(path: Path) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384 or info.st_mode & 0o077:
            raise ValueError("CD credentials must be a private regular file (chmod 600)")
        if info.st_uid not in {0, os.geteuid()}:
            raise ValueError("CD credentials must belong to the executor user or root")
        contents = source.read(16385)
        if len(contents) > 16384:
            raise ValueError("CD credentials exceed the size limit")
        return json.loads(contents)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, newurl):
        raise urllib.error.HTTPError(
            request.full_url, code, "CD redirects are refused", headers, file
        )


class JsonApi:
    def __init__(self, origin: str, token_file: Path, *, refresh: bool = False):
        self.origin = trusted_endpoint(origin)
        self.token_file = token_file
        self.refresh = refresh
        self.opener = urllib.request.build_opener(NoRedirect())

    def _send(self, method: str, path: str, body: dict | None, token: str | None) -> dict:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Invalid CD API path")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = urllib.request.Request(
            self.origin + path, data=data, headers=headers, method=method
        )
        with self.opener.open(request, timeout=30) as response:
            contents = response.read(16_777_217)
            if len(contents) > 16_777_216:
                raise ValueError("CD API response is too large")
            return json.loads(contents)

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        credentials = private_json(self.token_file)
        token = credentials.get("access_token")
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise ValueError("Missing CD access_token")
        try:
            return self._send(method, path, body, token)
        except urllib.error.HTTPError as error:
            if error.code != 401 or not self.refresh or not credentials.get("refresh_token"):
                raise
        renewed = self._send(
            "POST", "/api/v1/auth/refresh", {"refresh_token": credentials["refresh_token"]}, None
        )
        if not renewed.get("access_token") or not renewed.get("refresh_token"):
            raise ValueError("Backend did not rotate the CD refresh token")
        write_json(self.token_file, renewed)
        return self._send(method, path, body, renewed["access_token"])


def persist_images(api: JsonApi, images: dict[str, str]) -> None:
    from client_release import validate_images

    validate_images(images)
    path = "/api/stacks/hubshell/env?env=1"
    current = api.request("GET", path)
    variables = {item["key"]: item for item in current["variables"]}
    for key, image in images.items():
        variables[key] = {"key": key, "value": image, "isSecret": False}
    # Dockhand v1.0.53 PUT replaces the list; retain all variables, including masked secrets.
    api.request("PUT", path, {"variables": list(variables.values())})
    saved = {item["key"]: item["value"] for item in api.request("GET", path)["variables"]}
    if any(saved.get(key) != image for key, image in images.items()):
        raise ValueError("Dockhand did not persist the signed image references")
