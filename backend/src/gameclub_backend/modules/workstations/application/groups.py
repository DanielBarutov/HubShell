import base64
import dataclasses
import datetime
import hashlib
import secrets

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.workstations.application.ports import WorkstationGroupRepository
from gameclub_backend.modules.workstations.domain import LockdownPolicy, WorkstationGroup


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class WorkstationGroupService:
    _allowed_themes = frozenset({"standard", "vip", "neon", "minimal"})
    _password_iterations = 210_000

    def __init__(
        self,
        repository: WorkstationGroupRepository,
        clock: UtcClock | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()

    async def list(self) -> list[WorkstationGroup]:
        return await self._repository.list()

    async def save(
        self,
        group_id: str,
        name: str,
        theme: str,
        lockdown_policy: LockdownPolicy | None = None,
    ) -> WorkstationGroup:
        normalized_id = group_id.strip().lower()
        normalized_name = name.strip()
        normalized_theme = theme.strip().lower()
        if not normalized_id or not normalized_name:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "group_id and name are required")
        if normalized_theme not in self._allowed_themes:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT, "Unsupported workstation group theme"
            )
        existing = await self._repository.get(normalized_id)
        group = WorkstationGroup(
            id=normalized_id,
            name=normalized_name,
            theme=normalized_theme,
            updated_at=self._clock.now(),
            manager_password_verifier=(existing.manager_password_verifier if existing else None),
            lockdown_policy=(
                lockdown_policy
                if lockdown_policy is not None
                else (existing.lockdown_policy if existing else LockdownPolicy())
            ),
        )
        return await self._repository.save(group)

    async def set_lockdown_policy(
        self, group_id: str, lockdown_policy: LockdownPolicy
    ) -> WorkstationGroup:
        normalized_id = group_id.strip().lower()
        group = await self._repository.get(normalized_id)
        if group is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation group not found")
        return await self._repository.save(
            dataclasses.replace(
                group,
                lockdown_policy=lockdown_policy,
                updated_at=self._clock.now(),
            )
        )

    async def set_manager_password(self, group_id: str, password: str) -> WorkstationGroup:
        normalized_id = group_id.strip().lower()
        if not password.strip() or len(password) < 8 or len(password) > 128:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Manager password must contain from 8 to 128 characters",
            )
        group = await self._repository.get(normalized_id)
        if group is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation group not found")
        salt = secrets.token_bytes(24)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self._password_iterations,
            dklen=32,
        )
        verifier = "$".join(
            (
                "pbkdf2-sha256",
                str(self._password_iterations),
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(derived).decode("ascii"),
            )
        )
        return await self._repository.save(
            dataclasses.replace(
                group,
                manager_password_verifier=verifier,
                updated_at=self._clock.now(),
            )
        )

    async def delete(self, group_id: str) -> None:
        normalized_id = group_id.strip().lower()
        if await self._repository.get(normalized_id) is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation group not found")
        await self._repository.delete(normalized_id)

    async def theme_for(self, group_id: str | None) -> str:
        if not group_id:
            return "standard"
        group = await self._repository.get(group_id)
        return group.theme if group is not None else "standard"
