"""Versioned, identity-scoped protocol for coordinated client delivery."""

from __future__ import annotations

import datetime
import re
import typing
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, SecretStr, TypeAdapter

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.application.identity import UpdaterIdentityService
from gameclub_backend.modules.client_updates.application.service import ClientUpdateService
from gameclub_backend.modules.client_updates.domain import Deployment, DeviceUpdateReport
from gameclub_backend.presentation.http.auth import get_current_principal

Authenticated = typing.Annotated[Principal, Depends(get_current_principal)]
_codec = TypeAdapter(Deployment)


class CreateDeployment(BaseModel):
    operation_id: uuid.UUID
    release_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    executable_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgentTokenRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    credential_secret: SecretStr = Field(min_length=32, max_length=256)


class AgentReport(BaseModel):
    round_id: uuid.UUID
    sequence: int = Field(ge=1)
    instance_id: uuid.UUID
    active_session: bool
    pending_facts: int = Field(ge=0)
    ready: bool
    stage: typing.Literal["ready", "installing", "verifying", "installed", "failed", "rolled_back"]
    installed_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    error_code: str | None = Field(default=None, pattern=r"^[a-z0-9_.-]{1,64}$")

    session_id: uuid.UUID | None = None
    last_sequence: int = Field(default=0, ge=0)
    last_payload_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    running_release_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
    )


class BeginInstallation(AgentReport):
    stage: typing.Literal["installing"] = "installing"


class GuiConfirmation(BaseModel):
    release_id: str = Field(min_length=1, max_length=128)


async def _result(operation: typing.Awaitable[Deployment]) -> dict:
    try:
        return _codec.dump_python(await operation, mode="json")
    except ValueError as error:
        raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error


def create_router(
    service: ClientUpdateService | None,
    identity: UpdaterIdentityService | None,
    release_root: str | None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/client-updates", tags=["client-updates"])

    def updates() -> ClientUpdateService:
        if service is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "PostgreSQL updates are not configured"
            )
        return service

    def credentials() -> UpdaterIdentityService:
        if identity is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "Updater authentication is not configured"
            )
        return identity

    @router.post("/credentials/{device_id}")
    async def provision(device_id: str, principal: Authenticated, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        record, secret = await credentials().provision(principal, device_id)
        return {
            "device_id": record.device_id,
            "installation_id": record.installation_id,
            "credential_id": record.id,
            "credential_secret": secret,
        }

    @router.delete("/credentials/{device_id}")
    async def revoke(device_id: str, principal: Authenticated) -> dict:
        await credentials().revoke(principal, device_id)
        return {"revoked": True}

    @router.post("/agent-token")
    async def token(request: Request, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        try:
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw) + len(chunk) > 4096:
                    raise ValueError("Too large")
                raw.extend(chunk)
            body = AgentTokenRequest.model_validate_json(raw)
        except ValueError as error:
            # Do not echo machine secrets in request-validation errors.
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Invalid updater token request"
            ) from error
        access_token, expires_in = await credentials().token(
            body.device_id, body.credential_secret.get_secret_value()
        )
        return {"access_token": access_token, "expires_in": expires_in, "token_type": "Bearer"}

    @router.get("/agent/current")
    async def current_agent(
        instance_id: uuid.UUID, principal: Authenticated, response: Response
    ) -> dict:
        response.headers["Cache-Control"] = "no-store"
        await credentials().authorize(principal)
        return await updates().agent_command(principal, instance_id)

    @router.get("/gui/current")
    async def current_gui(principal: Authenticated, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        if principal.subject_type is not SubjectType.DEVICE:
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "GUI device identity required")
        value = await updates().current(principal)
        return {
            "deployment": None
            if value is None
            else {
                "id": value.id,
                "round_id": value.round_id,
                "release_id": value.release_id,
                "phase": value.phase.value,
                "block_gui": value.phase.value in {"preparing", "authorized", "failed"},
            }
        }

    @router.get("/releases/{release_id}/{filename}")
    def release_file(release_id: str, filename: str) -> FileResponse:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release_id) or filename not in {
            "release.json",
            "release.json.sig",
            "HubShell.zip",
        }:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Release file not found")
        if release_root is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "Release mirror is not configured"
            )
        root = Path(release_root).resolve()
        path = (root / release_id / filename).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ApplicationError(ErrorCode.NOT_FOUND, "Release file not found")
        return FileResponse(path, media_type="application/octet-stream", filename=filename)

    @router.post("")
    async def create(body: CreateDeployment, principal: Authenticated) -> dict:
        return await _result(
            updates().create(principal, body.operation_id, body.release_id, body.executable_sha256)
        )

    @router.get("/current")
    async def latest(principal: Authenticated, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        value = await updates().latest(principal)
        if value is None:
            return {"deployment": None}
        now = datetime.datetime.now(datetime.UTC)
        devices = []
        for device, workstation in sorted(value.targets.items()):
            report = value.reports.get(device)
            devices.append(
                {
                    "device_id": device,
                    "workstation_id": workstation,
                    "status": value.device_status(device, now),
                    "old_release_id": value.old_releases.get(device),
                    "running_release_id": report.running_release_id if report else None,
                    "received_at": report.received_at if report else None,
                    "error_code": report.error_code if report else None,
                }
            )
        return {
            "deployment": {
                "id": value.id,
                "release_id": value.release_id,
                "phase": value.phase.value,
                "created_at": value.created_at,
                "observed_at": now,
                "confirmed": sum(value.device_succeeded(device) for device in value.targets),
                "total": len(value.targets),
                "devices": devices,
            }
        }

    @router.get("/{deployment_id}")
    async def get(deployment_id: uuid.UUID, principal: Authenticated) -> dict:
        return await _result(updates().get(principal, deployment_id))

    @router.post("/{deployment_id}/refresh-targets")
    async def refresh_targets(deployment_id: uuid.UUID, principal: Authenticated) -> dict:
        return await _result(updates().refresh_targets(principal, deployment_id))

    @router.post("/{deployment_id}/prepare")
    async def prepare(deployment_id: uuid.UUID, principal: Authenticated) -> dict:
        return await _result(updates().prepare(principal, deployment_id))

    @router.post("/{deployment_id}/server-ready")
    async def server_ready(deployment_id: uuid.UUID, principal: Authenticated) -> dict:
        return await _result(updates().server_ready(principal, deployment_id))

    @router.post("/{deployment_id}/authorize")
    async def authorize(deployment_id: uuid.UUID, principal: Authenticated) -> dict:
        return await _result(updates().authorize(principal, deployment_id))

    @router.post("/{deployment_id}/retry")
    async def retry(deployment_id: uuid.UUID, principal: Authenticated) -> dict:
        return await _result(updates().retry(principal, deployment_id))

    @router.post("/{deployment_id}/finish")
    async def finish(deployment_id: uuid.UUID, principal: Authenticated) -> dict:
        return await _result(updates().finish(principal, deployment_id))

    @router.post("/{deployment_id}/begin-install")
    async def begin_install(
        deployment_id: uuid.UUID, body: BeginInstallation, principal: Authenticated
    ) -> dict:
        await credentials().authorize(principal)
        try:
            value = DeviceUpdateReport(
                device_id=principal.subject_id,
                received_at=datetime.datetime.now(datetime.UTC),
                **body.model_dump(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        await _result(updates().begin_install(principal, deployment_id, value))
        return {"authorized": True, "deployment_id": deployment_id, "round_id": body.round_id}

    @router.post("/{deployment_id}/reports")
    async def report(deployment_id: uuid.UUID, body: AgentReport, principal: Authenticated) -> dict:
        await credentials().authorize(principal)
        try:
            value = DeviceUpdateReport(
                device_id=principal.subject_id,
                received_at=datetime.datetime.now(datetime.UTC),
                **body.model_dump(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        await _result(updates().report(principal, deployment_id, value))
        return {"accepted": True}

    @router.post("/{deployment_id}/gui-confirm")
    async def gui_confirm(
        deployment_id: uuid.UUID, body: GuiConfirmation, principal: Authenticated
    ) -> dict:
        await _result(updates().confirm_gui(principal, deployment_id, body.release_id))
        return {"accepted": True}

    return router
