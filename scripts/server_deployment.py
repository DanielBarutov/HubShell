"""Controlled application-only Compose deployment with verified database backups."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

from client_release import digest, validate_images
from client_update_cd import write_json


class MaintenanceBlocked(ValueError):
    """An actionable refusal with a fixed, safe-to-log message."""


class ComposeServer:
    def __init__(self, repository: Path, env_file: Path, job: Path, images: dict[str, str]):
        validate_images(images)
        self.repository = repository.resolve()
        self.job = job
        self.environment = dict(os.environ, **images)
        self.command = [
            "docker",
            "compose",
            "--project-name",
            "hubshell",
            "--env-file",
            str(env_file.resolve()),
            "-f",
            str(self.repository / "compose.deploy.yml"),
        ]
        self.images = images

    def run(self, *args: str, stdin=None, stdout=subprocess.PIPE, timeout=900):
        return subprocess.run(
            [*self.command, *args],
            cwd=self.repository,
            env=self.environment,
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=True,
        )

    def backup(self, service: str, user: str, database: str) -> None:
        backups = self.job / "backups"
        backups.mkdir(exist_ok=True, mode=0o700)
        dump = backups / f"{database}.dump"
        marker = backups / f"{database}.json"
        if dump.is_symlink() or marker.is_symlink():
            raise ValueError("Database backup cannot be a symlink")
        if marker.exists():
            saved = json.loads(marker.read_bytes())
            if not saved.get("restore_verified") or digest(dump) != saved["sha256"]:
                raise ValueError("Previously verified backup has changed")
            return
        if not dump.exists():
            temporary = dump.with_suffix(".dump.new")
            if temporary.is_symlink():
                raise ValueError("Backup temporary file cannot be a symlink")
            try:
                with temporary.open("wb") as output:
                    self.run(
                        "exec",
                        "-T",
                        service,
                        "pg_dump",
                        "-U",
                        user,
                        "-d",
                        database,
                        "-Fc",
                        stdout=output,
                    )
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(dump)
            finally:
                temporary.unlink(missing_ok=True)
        restore = "hubshell_restore_" + uuid.uuid4().hex
        self.run("exec", "-T", service, "createdb", "-U", user, restore)
        try:
            with dump.open("rb") as source:
                self.run(
                    "exec",
                    "-T",
                    service,
                    "pg_restore",
                    "-U",
                    user,
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "-d",
                    restore,
                    stdin=source,
                )
        finally:
            self.run("exec", "-T", service, "dropdb", "-U", user, restore)
        write_json(
            marker,
            {
                "database": database,
                "sha256": digest(dump),
                "bytes": dump.stat().st_size,
                "restore_verified": True,
            },
        )

    def update(self, deployment: dict, smoke) -> None:
        if deployment["phase"] != "preparing":
            raise ValueError("Server update requires the durable fleet barrier")
        self._update(smoke, {"deployment_id": deployment["id"], "round_id": deployment["round_id"]})

    def update_idle(self, smoke) -> None:
        self._update(smoke, {}, require_idle=True)

    def _require_idle(self) -> None:
        result = self.run(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "gameclub",
            "-d",
            "gameclub",
            "-Atc",
            "SELECT count(*) FROM gaming_sessions WHERE status = 'active'",
        )
        if result.stdout.strip() != b"0":
            raise MaintenanceBlocked("В клубе есть активные сессии. Деплой не запущен.")

    def _update(self, smoke, report: dict, *, require_idle: bool = False) -> None:
        config = json.loads(self.run("config", "--format", "json").stdout)
        if config["name"] != "hubshell" or any(
            "build" in item for item in config["services"].values()
        ):
            raise ValueError("CD only supports the isolated image-based TrueNAS stack")
        services = sorted(
            name
            for name, item in config["services"].items()
            if item.get("image") in self.images.values() and name != "backend-migrate"
        )
        expected = {
            "backend-http": "HUBSHELL_BACKEND_IMAGE",
            "backend-grpc": "HUBSHELL_BACKEND_IMAGE",
            "backend-migrate": "HUBSHELL_BACKEND_IMAGE",
            "frontend": "HUBSHELL_FRONTEND_IMAGE",
            "steam-guest-server": "HUBSHELL_STEAM_GUEST_IMAGE",
        }
        if any(
            config["services"][name]["image"] != self.images[key] for name, key in expected.items()
        ):
            raise ValueError("Resolved Compose images differ from the signed release")
        self.run("pull", *services, "backend-migrate")
        if require_idle:
            self._require_idle()
            running = set(
                self.run("ps", "--status", "running", "--services").stdout.decode().split()
            )
            if running - config["services"].keys():
                raise MaintenanceBlocked("У рабочего стека есть сервисы вне выбранного Compose.")
            if not {"backend-http", "backend-grpc"}.issubset(running):
                raise MaintenanceBlocked("Исходный backend должен работать перед обновлением.")
        migration_started = self.job / "migration-started.json"
        if require_idle and migration_started.exists():
            raise MaintenanceBlocked("Предыдущая миграция требует ручной проверки перед повтором.")
        try:
            self.run("stop", "--timeout", "30", *services)
            if require_idle:
                self._require_idle()
            self.backup("postgres", "gameclub", "gameclub")
            self.backup("steam-guest-postgres", "steam_guest", "steam_guest")
            if require_idle:
                write_json(migration_started, {"images": self.images})
        except Exception:
            if require_idle:
                self.run("start", *(name for name in services if name in running))
            raise
        self.run("run", "--rm", "--no-deps", "backend-migrate")
        self.run(
            "up", "-d", "--no-deps", "--pull", "never", "--wait", "--wait-timeout", "180", *services
        )
        self.run(
            "exec",
            "-T",
            "backend-grpc",
            "python",
            "-c",
            "import grpc; from gameclub.v1 import system_pb2, system_pb2_grpc; "
            "channel=grpc.insecure_channel('127.0.0.1:51051'); "
            "result=system_pb2_grpc.SystemServiceStub(channel).GetHealth("
            "system_pb2.HealthRequest(),timeout=10); "
            "assert result.status == 'ok' and result.service == 'gameclub-backend'",
        )
        self.run("exec", "-T", "frontend", "wget", "--quiet", "--spider", "http://127.0.0.1/")
        smoke()
        write_json(
            self.job / "server-stage.json",
            {
                **report,
                "images": self.images,
                "backup_restore_verified": True,
                "ready": True,
            },
        )
