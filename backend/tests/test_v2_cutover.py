import pytest

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import SessionStatus
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationSessionMode
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)

pytestmark = pytest.mark.unit


async def test_v2_cutover_terminates_only_active_v1_sessions_and_is_repeatable() -> None:
    """Проверяет завершение V1 и повторяемый перевод мест в V2 без затрагивания V2 ledger."""
    workstations = InMemoryWorkstationRepository()
    workstation_service = WorkstationService(workstations)
    v1_first = await workstation_service.register(
        "cutover-v1-01",
        "V1 PC 01",
        session_mode=WorkstationSessionMode.V1_SERVER_OWNED,
    )
    v1_second = await workstation_service.register(
        "cutover-v1-02",
        "V1 PC 02",
        session_mode=WorkstationSessionMode.V1_SERVER_OWNED,
    )
    v2 = await workstation_service.register(
        "cutover-v2-01",
        "V2 PC",
        session_mode=WorkstationSessionMode.V2_LOCAL_LEDGER,
    )
    clients = ClientService(InMemoryClientRepository())
    first_client = await clients.create("CutoverV1First")
    second_client = await clients.create("CutoverV1Second")
    v2_client = await clients.create("CutoverV2")
    service = SessionService(
        InMemorySessionRepository(),
        workstations=workstations,
        clients=clients,
    )

    v1_first_session = await service.start(
        workstation_id=v1_first.id,
        client_id=first_client.id,
        created_by="operator",
        source="device",
    )
    v1_second_session = await service.start(
        workstation_id=v1_second.id,
        client_id=second_client.id,
        created_by="operator",
        source="operator",
    )
    v2_session = await service.start(
        workstation_id=v2.id,
        client_id=v2_client.id,
        created_by="client:cutover",
        source="v2_local_ledger",
    )

    terminated = await service.terminate_active_v1_sessions_for_cutover()

    assert {item.id for item in terminated} == {v1_first_session.id, v1_second_session.id}
    assert (await service.get(v1_first_session.id)).status is SessionStatus.COMPLETED
    assert (await service.get(v1_second_session.id)).status is SessionStatus.COMPLETED
    assert (await service.get(v2_session.id)).status is SessionStatus.ACTIVE
    assert await service.terminate_active_v1_sessions_for_cutover() == []

    migrated = await workstation_service.migrate_all_to_v2_for_cutover()

    assert {item.id for item in migrated} == {v1_first.id, v1_second.id}
    assert (await workstation_service.get_by_device_id(v1_first.device_id)).session_mode is (
        WorkstationSessionMode.V2_LOCAL_LEDGER
    )
    assert (await workstation_service.get_by_device_id(v1_second.device_id)).session_mode is (
        WorkstationSessionMode.V2_LOCAL_LEDGER
    )
    assert (await workstation_service.get_by_device_id(v2.device_id)).session_mode is (
        WorkstationSessionMode.V2_LOCAL_LEDGER
    )
    assert await workstation_service.migrate_all_to_v2_for_cutover() == []

    with pytest.raises(ApplicationError) as error:
        await service.start(
            workstation_id=v1_first.id,
            client_id=first_client.id,
            created_by="operator",
            source="operator",
        )
    assert error.value.code is ErrorCode.CONFLICT
