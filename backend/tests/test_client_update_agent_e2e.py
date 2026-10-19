"""Real .NET agent / TCP HTTP / PostgreSQL delivery; native GUI/processes are simulated."""

import asyncio
import datetime
import hashlib
import json
import os
import runpy
import socket
import struct
import sys
import uuid
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import delete, func, select

from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.infrastructure.credentials_postgres import (
    UpdaterCredentialModel,
)
from gameclub_backend.modules.sessions.infrastructure.postgres import SessionAdmissionBlockModel
from gameclub_backend.modules.workstations.domain import Workstation
from gameclub_backend.modules.workstations.infrastructure.postgres import WorkstationModel
from test_client_update_http_postgres import http_updates as http_updates

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.api]
ROOT = Path(__file__).resolve().parents[2]
PREFIX = "/api/v1/client-updates"


@pytest.fixture
async def second_update_pc(http_updates):
    """Второй тестовый PC очищается даже при ошибке запуска host/backend."""
    _, _, first, repository, app, _ = http_updates
    second = Workstation(
        uuid.uuid4(), first.device_id + "-2", "Second update PC", installation_id=uuid.uuid4().hex
    )
    await repository.save(second)
    try:
        yield second
    finally:
        async with app.state.resources.engine.begin() as transaction:
            await transaction.execute(
                delete(UpdaterCredentialModel).where(
                    UpdaterCredentialModel.device_id == second.device_id
                )
            )
            await transaction.execute(
                delete(SessionAdmissionBlockModel).where(
                    SessionAdmissionBlockModel.workstation_id == second.id
                )
            )
            await transaction.execute(
                delete(WorkstationModel).where(WorkstationModel.id == second.id)
            )


async def test_two_real_agents_wait_for_park_rollback_retry_and_confirm_every_pc(
    http_updates, second_update_pc
):
    """Два .NET агента проходят общий барьер, pilot, откат и retry через настоящий HTTP/БД."""
    _, operator, first, _, app, root = http_updates
    project = "win-client/tests/UpdateAgentHost/UpdateAgentHost.csproj"
    build = await asyncio.create_subprocess_exec(
        "dotnet",
        "build",
        project,
        "-p:Platform=x64",
        "--nologo",
        cwd=ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    build_output, _ = await build.communicate()
    assert build.returncode == 0, build_output.decode()[-4000:]
    host = ROOT / "win-client/tests/UpdateAgentHost/bin/x64/Debug/net8.0/UpdateAgentHost.dll"
    second = second_update_pc
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_file = root / "private.pem"
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_file.chmod(0o600)
    executable = bytearray(4096)
    executable[:2] = b"MZ"
    executable[0x3C:0x40] = struct.pack("<I", 128)
    executable[128:134] = b"PE\0\0\x64\x86"
    source = root / "new.exe"
    source.write_bytes(executable)
    version = "v-e2e-" + uuid.uuid4().hex
    package = root / version
    packager = runpy.run_path(str(ROOT / "scripts/build-client-release.py"))["build_release"]
    await asyncio.to_thread(packager, source, source, package, version, "a" * 40, key_file)
    target_hash = hashlib.sha256(executable).hexdigest()
    old_hash = hashlib.sha256(b"old executable").hexdigest()
    configuration = root / "backend-settings.json"
    configuration.write_text(
        json.dumps(
            {
                "postgres_dsn": app.state.settings.postgres_dsn,
                "redis_url": None,
                "jwt_secret": app.state.settings.jwt_secret,
                "dev_operator_username": "operator",
                "dev_operator_password": "test-password",
                "client_release_root": str(root),
            }
        )
    )
    configuration.chmod(0o600)
    entrypoint = (
        "import json,sys,uvicorn; from gameclub_backend.config import Settings; "
        "from gameclub_backend.presentation.http.app import create_app; "
        "settings=Settings(_env_file=None,**json.load(open(sys.argv[1]))); "
        "uvicorn.run(create_app(settings),fd=int(sys.argv[2]),log_level='info',access_log=False)"
    )

    async def start_backend(port=0):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        port = listener.getsockname()[1]
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            entrypoint,
            str(configuration),
            str(listener.fileno()),
            pass_fds=(listener.fileno(),),
            cwd=ROOT,
            env={
                key: value for key, value in os.environ.items() if not key.startswith("GAMECLUB_")
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        listener.close()
        try:
            async with asyncio.timeout(15):
                while True:
                    line = await process.stderr.readline()
                    assert line, "Backend exited before startup"
                    if b"Uvicorn running" in line:
                        return process, port
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise

    server, port = await start_backend()
    backend = f"http://127.0.0.1:{port}"
    processes = []
    installations = []

    async def command(index, value="tick", success=True):
        process = processes[index]
        process.stdin.write((value + "\n").encode())
        await process.stdin.drain()
        data = await asyncio.wait_for(process.stdout.readline(), 20)
        result = json.loads(data)
        assert result["ok"] is success, result
        return result

    try:
        async with httpx.AsyncClient(base_url=backend, timeout=20) as client:
            for index, workstation in enumerate((first, second)):
                credential = await client.post(
                    f"{PREFIX}/credentials/{workstation.device_id}", headers=operator
                )
                credential.raise_for_status()
                gui_token, _ = app.state.jwt_service.issue_access_token(
                    Principal(
                        workstation.device_id,
                        SubjectType.DEVICE,
                        frozenset({"device"}),
                        frozenset({"workstations.connect"}),
                    )
                )
                directory = root / f"pc-{index}"
                directory.mkdir()
                (directory / "HubShell.exe").write_bytes(b"old executable")
                (directory / "server.ini").write_text("preserved server config")
                (directory / "ledger.json").write_text("preserved financial facts")
                installations.append(directory)
                settings = root / f"host-{index}.json"
                settings.write_text(
                    json.dumps(
                        {
                            "backend": backend,
                            "deviceId": workstation.device_id,
                            "installationId": workstation.installation_id,
                            "credentialSecret": credential.json()["credential_secret"],
                            "guiToken": gui_token,
                            "publicKeyPath": str(package / "release-public-key.pem"),
                            "directory": str(directory),
                            "targetReleaseId": version,
                            "targetSha256": target_hash,
                        }
                    )
                )
                settings.chmod(0o600)
                processes.append(
                    await asyncio.create_subprocess_exec(
                        "dotnet",
                        str(host),
                        str(settings),
                        cwd=ROOT,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                )
            creation = await client.post(
                PREFIX,
                headers=operator,
                json={
                    "operation_id": str(uuid.uuid4()),
                    "release_id": version,
                    "executable_sha256": target_hash,
                },
            )
            creation.raise_for_status()
            identifier = creation.json()["id"]

            async def action(name, status=200):
                response = await client.post(f"{PREFIX}/{identifier}/{name}", headers=operator)
                assert response.status_code == status, response.text
                return response.json()

            assert (await command(0))["hash"] == old_hash
            await action("prepare", 409)  # No response from the second PC.
            await command(1, "active")
            assert (await command(1))["hash"] == old_hash
            await action("prepare", 409)
            assert (await command(0))["closes"] == 0
            assert (await command(1))["closes"] == 0
            await command(1, "idle")
            await command(1)
            await action("prepare")
            await action("server-ready")
            await action("authorize", 409)  # Final round has no reports yet.
            assert (await command(0))["blocked"]
            assert (await command(1))["blocked"]
            first_pid = server.pid
            server.terminate()
            await asyncio.wait_for(server.wait(), 10)
            assert not (await command(0, success=False))["ok"]
            assert json.loads((installations[0] / ".client-update.json").read_bytes())["blocked"]
            server, restarted_port = await start_backend(port)
            assert server.pid != first_pid and restarted_port == port
            restored = (await client.get(f"{PREFIX}/{identifier}", headers=operator)).json()
            assert restored["phase"] == "preparing" and restored["server_ready"]
            await action("authorize")
            assert (await command(1))["hash"] == old_hash  # Pilot is still unconfirmed.
            assert (await command(0))["hash"] == target_hash
            await action("finish", 409)
            await command(1, "unhealthy")
            rollback = await command(1)
            assert (rollback["hash"], rollback["stage"], rollback["blocked"]) == (
                old_hash,
                "rolled_back",
                True,
            )
            failed = (await client.get(f"{PREFIX}/{identifier}", headers=operator)).json()
            assert failed["phase"] == "failed"
            await command(0)
            await command(1)
            preserved = (await client.get(f"{PREFIX}/{identifier}", headers=operator)).json()
            assert preserved["reports"][first.device_id]["stage"] == "installed"
            assert preserved["reports"][second.device_id]["stage"] == "rolled_back"
            assert all(
                json.loads((directory / ".client-update.json").read_bytes())["blocked"]
                for directory in installations
            )
            await action("finish", 409)
            async with app.state.resources.engine.connect() as connection:
                assert await connection.scalar(
                    select(func.count())
                    .select_from(SessionAdmissionBlockModel)
                    .where(SessionAdmissionBlockModel.deployment_id == uuid.UUID(identifier))
                )
            await command(1, "healthy")
            await action("retry")
            await command(0)
            await command(1)
            await action("server-ready")
            await action("authorize")
            assert (await command(1))["hash"] == old_hash
            pilot = await command(0)
            assert pilot["hash"] == target_hash and pilot["closes"] == 1
            assert (await command(1))["hash"] == target_hash
            completed = await action("finish")
            assert completed["phase"] == "completed"
            for index, directory in enumerate(installations):
                assert not (await command(index))["blocked"]
                assert (directory / "server.ini").read_text() == "preserved server config"
                assert (directory / "ledger.json").read_text() == "preserved financial facts"
            current = (await client.get(f"{PREFIX}/current", headers=operator)).json()["deployment"]
            assert (current["confirmed"], current["total"]) == (2, 2)
            output = root / "evidence"
            output.mkdir()
            save = runpy.run_path(str(ROOT / "scripts/client_update_cd.py"))["save_report"]
            assert save(output, completed, datetime.datetime.now(datetime.UTC))["success"]
            assert "2/2" in (output / "report.txt").read_text()
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.wait()
        if server.returncode is None:
            server.terminate()
        await asyncio.wait_for(server.wait(), 10)
