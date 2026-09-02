import asyncio

import pytest

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.transfer import SessionTransferService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.sessions.infrastructure.transfers_memory import (
    InMemorySessionTransferRepository,
)
from gameclub_backend.modules.workstations.application.commands import WorkstationCommandService
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.commands_memory import (
    InMemoryCommandNotifier,
    InMemoryWorkstationCommandRepository,
)
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)


async def build_transfer_services():
    workstation_repository = InMemoryWorkstationRepository()
    workstations = WorkstationService(workstation_repository)
    source = await workstations.register("transfer-source", "Source PC", group_id="vip")
    target = await workstations.register("transfer-target", "Target PC", group_id="vip")
    occupied = await workstations.register("transfer-occupied", "Occupied PC", group_id="vip")

    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("TransferFox")
    session_repository = InMemorySessionRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
    )
    session = await sessions.start(
        source.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="transfer-session",
    )
    transfer = SessionTransferService(
        InMemorySessionTransferRepository(),
        sessions=session_repository,
        workstations=workstation_repository,
    )
    return transfer, sessions, session, target, occupied


@pytest.mark.asyncio
async def test_transfer_confirm_is_idempotent_under_concurrency() -> None:
    transfer, sessions, session, target, _occupied = await build_transfer_services()
    offer = await transfer.create_offer(session.id, target.id, "transfer-offer")

    first, second = await asyncio.gather(
        transfer.confirm(offer.id, "transfer-confirm"),
        transfer.confirm(offer.id, "transfer-confirm"),
    )

    assert first[0].id == second[0].id == offer.id
    assert first[0].status.value == "confirmed"
    assert first[1].id == second[1].id == session.id
    assert first[1].workstation_id == target.id
    active_on_target = await sessions.list(target.id, active_only=True)
    assert active_on_target == [first[1]]


@pytest.mark.asyncio
async def test_transfer_rejects_second_confirmation_with_another_key() -> None:
    transfer, _sessions, session, target, _occupied = await build_transfer_services()
    offer = await transfer.create_offer(session.id, target.id, "transfer-offer-2")
    await transfer.confirm(offer.id, "transfer-confirm-2")

    with pytest.raises(ApplicationError, match="already confirmed"):
        await transfer.confirm(offer.id, "another-confirmation")


@pytest.mark.asyncio
async def test_transfer_rejects_target_with_active_session() -> None:
    transfer, sessions, session, target, occupied = await build_transfer_services()
    await sessions.start(
        occupied.id,
        created_by="operator",
        guest_name="Occupied guest",
        idempotency_key="occupied-session",
    )

    with pytest.raises(ApplicationError, match="target already has an active session"):
        await transfer.create_offer(session.id, occupied.id, "transfer-conflict")


@pytest.mark.asyncio
async def test_transfer_publishes_duplicate_safe_restart_command_status() -> None:
    workstation_repository = InMemoryWorkstationRepository()
    workstations = WorkstationService(workstation_repository)
    source = await workstations.register("restart-source", "Restart source", group_id="vip")
    target = await workstations.register("restart-target", "Restart target", group_id="vip")
    client_repository = InMemoryClientRepository()
    client = await ClientService(client_repository).create("RestartClient")
    session_repository = InMemorySessionRepository()
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
    )
    session = await sessions.start(
        source.id,
        created_by="operator",
        client_id=client.id,
        idempotency_key="restart-session",
    )
    command_service = WorkstationCommandService(
        InMemoryWorkstationCommandRepository(),
        workstations=workstation_repository,
        notifier=InMemoryCommandNotifier(),
    )
    transfer = SessionTransferService(
        InMemorySessionTransferRepository(),
        sessions=session_repository,
        workstations=workstation_repository,
        commands=command_service,
    )

    offer = await transfer.create_offer(session.id, target.id, "restart-offer")
    await transfer.confirm(offer.id, "restart-confirm")

    command = await transfer.restart_status(offer.id)
    repeated = await transfer.restart_status(offer.id)
    assert command.id == repeated.id
    assert command.command_type == "system.restart"
    assert command.idempotency_key == f"transfer-restart:{offer.id}"
    assert command.status.value == "queued"
