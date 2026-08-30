import asyncio
import datetime
import uuid

import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.workstations.application.commands import WorkstationCommandService
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain_commands import WorkstationCommandStatus
from gameclub_backend.modules.workstations.infrastructure.commands_memory import (
    InMemoryCommandNotifier,
    InMemoryWorkstationCommandRepository,
)
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)


async def test_command_delivery_is_idempotent_and_acknowledgement_is_safe() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        "device-commands-01",
        "VIP-01",
    )
    command_service = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=workstation_repository,
        notifier=InMemoryCommandNotifier(),
    )

    commands = await asyncio.gather(
        *(
            command_service.dispatch(
                workstation_id=workstation.id,
                command_type="display.lock",
                payload_json='{"reason":"operator"}',
                idempotency_key="command-001",
            )
            for _ in range(3)
        )
    )

    assert {command.id for command in commands} == {commands[0].id}
    assert commands[0].status is WorkstationCommandStatus.QUEUED
    pending = await command_service.pending_for_device("device-commands-01")
    assert [command.id for command in pending] == [commands[0].id]

    acknowledged = await command_service.acknowledge(
        command_id=commands[0].id,
        device_id="device-commands-01",
        success=True,
        message="applied",
    )
    repeated = await command_service.acknowledge(
        command_id=commands[0].id,
        device_id="device-commands-01",
        success=False,
        message="must not overwrite acknowledgement",
    )

    assert acknowledged.status is WorkstationCommandStatus.ACKNOWLEDGED
    assert repeated == acknowledged
    assert await command_service.pending_for_device("device-commands-01") == []


async def test_command_idempotency_key_cannot_change_command_payload() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository).register(
        f"device-{uuid.uuid4()}",
        "PC-01",
    )
    command_service = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=workstation_repository,
        notifier=InMemoryCommandNotifier(),
    )

    await command_service.dispatch(
        workstation.id,
        "theme.apply",
        '{"theme":"vip"}',
        "command-002",
    )

    with pytest.raises(ApplicationError) as error:
        await command_service.dispatch(
            workstation.id,
            "theme.apply",
            '{"theme":"regular"}',
            "command-002",
        )

    assert error.value.code is ErrorCode.CONFLICT


async def test_expired_command_is_not_delivered_or_acknowledged() -> None:
    class FixedClock:
        def __init__(self) -> None:
            self.current = datetime.datetime(2026, 8, 27, 12, tzinfo=datetime.UTC)

        def now(self) -> datetime.datetime:
            return self.current

    clock = FixedClock()
    workstation_repository = InMemoryWorkstationRepository()
    workstation = await WorkstationService(workstation_repository, clock=clock).register(
        "device-expiry-01",
        "PC-01",
    )
    command_service = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=workstation_repository,
        notifier=InMemoryCommandNotifier(),
        clock=clock,
        command_ttl_seconds=10,
    )
    command = await command_service.dispatch(
        workstation_id=workstation.id,
        command_type="display.lock",
        payload_json="{}",
        idempotency_key="command-expiry-001",
    )
    clock.current += datetime.timedelta(seconds=11)

    assert await command_service.pending_for_device("device-expiry-01") == []
    expired = await command_service.get(workstation.id, command.id)
    late_ack = await command_service.acknowledge(
        command.id,
        "device-expiry-01",
        success=True,
        message="late success",
    )

    assert expired.status is WorkstationCommandStatus.EXPIRED
    assert late_ack.status is WorkstationCommandStatus.EXPIRED
    assert late_ack.acknowledgement_message == "Command expired before acknowledgement"
