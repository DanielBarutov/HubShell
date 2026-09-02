import asyncio
import datetime
import json
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.workstations.application.ports import (
    Clock,
    CommandNotifier,
    WorkstationCommandRepository,
    WorkstationRepository,
)
from gameclub_backend.modules.workstations.domain import WorkstationStatus
from gameclub_backend.modules.workstations.domain_commands import (
    WorkstationCommand,
    WorkstationCommandStatus,
)

ALLOWED_COMMAND_TYPES: frozenset[str] = frozenset(
    {
        "session.start",
        "session.stop",
        "display.lock",
        "theme.apply",
        "system.restart",
    }
)


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class WorkstationCommandService:
    def __init__(
        self,
        repository: WorkstationCommandRepository,
        workstations: WorkstationRepository,
        notifier: CommandNotifier,
        clock: Clock | None = None,
        command_ttl_seconds: int = 120,
    ) -> None:
        if command_ttl_seconds <= 0:
            raise ValueError("command_ttl_seconds must be positive")
        self._repository = repository
        self._workstations = workstations
        self._notifier = notifier
        self._clock = clock or UtcClock()
        self._command_ttl = datetime.timedelta(seconds=command_ttl_seconds)

    async def dispatch(
        self,
        workstation_id: uuid.UUID,
        command_type: str,
        payload_json: str,
        idempotency_key: str,
    ) -> WorkstationCommand:
        normalized_key = idempotency_key.strip()
        if not normalized_key or len(normalized_key) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        if command_type not in ALLOWED_COMMAND_TYPES:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Unsupported workstation command")
        try:
            payload = json.loads(payload_json or "{}")
        except json.JSONDecodeError as error:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "payload_json must be valid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "payload_json must be a JSON object")
        normalized_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        workstation = await self._workstations.get(workstation_id)
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        if workstation.status is WorkstationStatus.DISABLED:
            raise ApplicationError(ErrorCode.CONFLICT, "Workstation is disabled")

        existing = await self._repository.get_by_idempotency_key(normalized_key)
        if existing is not None:
            self._ensure_same_command(existing, workstation_id, command_type, normalized_payload)
            return existing

        created_at = self._clock.now()
        command = WorkstationCommand(
            id=uuid.uuid4(),
            workstation_id=workstation_id,
            command_type=command_type,
            payload_json=normalized_payload,
            idempotency_key=normalized_key,
            status=WorkstationCommandStatus.QUEUED,
            created_at=created_at,
            expires_at=created_at + self._command_ttl,
        )
        saved = await self._repository.save(command)
        self._ensure_same_command(saved, workstation_id, command_type, normalized_payload)
        if saved.id == command.id:
            await self._notifier.notify(workstation.device_id)
        return saved

    async def acknowledge(
        self,
        command_id: uuid.UUID,
        device_id: str,
        success: bool,
        message: str | None,
    ) -> WorkstationCommand:
        command = await self._repository.get(command_id)
        if command is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation command not found")
        workstation = await self._workstations.get(command.workstation_id)
        if workstation is None or workstation.device_id != device_id.strip():
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Command does not belong to device")
        return await self._repository.acknowledge(
            command_id,
            success,
            message,
            self._clock.now(),
        )

    async def get(
        self,
        workstation_id: uuid.UUID,
        command_id: uuid.UUID,
    ) -> WorkstationCommand:
        command = await self._repository.get(command_id)
        if command is None or command.workstation_id != workstation_id:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation command not found")
        if (
            command.status is WorkstationCommandStatus.QUEUED
            and command.expires_at <= self._clock.now()
        ):
            command = await self._repository.expire(command.id, self._clock.now())
        return command

    async def get_by_idempotency_key(self, idempotency_key: str) -> WorkstationCommand | None:
        """Return a durable command for recovery/status inspection by its key."""
        return await self._repository.get_by_idempotency_key(idempotency_key.strip())

    async def pending_for_device(self, device_id: str) -> list[WorkstationCommand]:
        workstation = await self._workstations.get_by_device_id(device_id.strip())
        if workstation is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Workstation not found")
        now = self._clock.now()
        await self._repository.expire_queued_before(now)
        return await self._repository.list_pending(workstation.id)

    async def wait_for_commands(self, device_id: str, wait_seconds: float = 15.0) -> None:
        try:
            async with asyncio.timeout(wait_seconds):
                await self._notifier.wait(device_id.strip())
        except TimeoutError:
            return

    @staticmethod
    def _ensure_same_command(
        command: WorkstationCommand,
        workstation_id: uuid.UUID,
        command_type: str,
        payload_json: str,
    ) -> None:
        if (
            command.workstation_id != workstation_id
            or command.command_type != command_type
            or command.payload_json != payload_json
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Idempotency key belongs to another command",
            )
