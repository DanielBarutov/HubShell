"""Separate machine credentials issue short-lived, updater-only JWT identities."""

from __future__ import annotations

import dataclasses
import hashlib
import secrets
import typing
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.domain.equipment import EquipmentType
from gameclub_backend.modules.auth.application.ports import TokenService
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.application.service import ClientUpdateService
from gameclub_backend.modules.workstations.application.ports import WorkstationRepository
from gameclub_backend.modules.workstations.domain import WorkstationStatus


@dataclasses.dataclass(frozen=True)
class UpdaterCredential:
    id: uuid.UUID
    device_id: str
    workstation_id: uuid.UUID
    installation_id: str
    secret_hash: str


class UpdaterCredentialRepository(typing.Protocol):
    async def get(self, device_id: str) -> UpdaterCredential | None:
        """Read the current hashed machine credential."""

    async def save(self, credential: UpdaterCredential) -> None:
        """Rotate a machine credential, invalidating previous updater JWTs."""

    async def revoke(self, device_id: str) -> None:
        """Revoke the credential and its outstanding updater JWTs."""


class UpdaterIdentityService:
    def __init__(
        self,
        credentials: UpdaterCredentialRepository,
        workstations: WorkstationRepository,
        tokens: TokenService,
    ) -> None:
        self._credentials = credentials
        self._workstations = workstations
        self._tokens = tokens

    async def provision(
        self, principal: Principal, device_id: str
    ) -> tuple[UpdaterCredential, str]:
        ClientUpdateService.require_operator(principal)
        workstation = await self._workstations.get_by_device_id(device_id)
        if (
            workstation is None
            or workstation.archived_at is not None
            or workstation.status is WorkstationStatus.DISABLED
            or workstation.equipment_type is not EquipmentType.PC
            or not workstation.installation_id
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "An enrolled PC installation is required")
        secret = secrets.token_urlsafe(32)
        credential = UpdaterCredential(
            uuid.uuid4(),
            device_id,
            workstation.id,
            workstation.installation_id,
            hashlib.sha256(secret.encode()).hexdigest(),
        )
        await self._credentials.save(credential)
        return credential, secret

    async def revoke(self, principal: Principal, device_id: str) -> None:
        ClientUpdateService.require_operator(principal)
        await self._credentials.revoke(device_id)

    async def _require_enrollment(self, credential: UpdaterCredential) -> None:
        workstation = await self._workstations.get_by_device_id(credential.device_id)
        if (
            workstation is None
            or workstation.id != credential.workstation_id
            or workstation.installation_id != credential.installation_id
            or workstation.archived_at is not None
            or workstation.status is WorkstationStatus.DISABLED
        ):
            raise ApplicationError(
                ErrorCode.UNAUTHENTICATED, "Updater enrollment is no longer active"
            )

    async def token(self, device_id: str, secret: str) -> tuple[str, int]:
        credential = await self._credentials.get(device_id)
        digest = hashlib.sha256(secret.encode()).hexdigest()
        if credential is None or not secrets.compare_digest(credential.secret_hash, digest):
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, "Invalid updater credentials")
        await self._require_enrollment(credential)
        return self._tokens.issue_access_token(
            Principal(
                device_id,
                SubjectType.UPDATER,
                frozenset({f"updater-credential:{credential.id}"}),
                frozenset({"client_updates.report", "client_updates.poll"}),
            )
        )

    async def authorize(self, principal: Principal) -> Principal:
        if principal.subject_type is not SubjectType.UPDATER:
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Updater identity required")
        credential = await self._credentials.get(principal.subject_id)
        if credential is None or f"updater-credential:{credential.id}" not in principal.roles:
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, "Updater credential was revoked")
        await self._require_enrollment(credential)
        return principal
