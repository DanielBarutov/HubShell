import base64
import hashlib

import pytest

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.modules.workstations.application.groups import WorkstationGroupService
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.groups_memory import (
    InMemoryWorkstationGroupRepository,
)
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.presentation.grpc.services import to_proto


@pytest.mark.asyncio
async def test_manager_password_is_stored_as_verifier_and_reaches_device_config() -> None:
    groups = InMemoryWorkstationGroupRepository()
    group_service = WorkstationGroupService(groups)
    await group_service.save("vip", "VIP-зона", "vip")

    updated = await group_service.set_manager_password("vip", "manager-secret")

    assert updated.manager_password_verifier is not None
    assert "manager-secret" not in updated.manager_password_verifier
    scheme, iterations, salt_text, expected_text = updated.manager_password_verifier.split("$")
    assert scheme == "pbkdf2-sha256"
    assert iterations == "210000"
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        b"manager-secret",
        base64.b64decode(salt_text),
        int(iterations),
        dklen=len(base64.b64decode(expected_text)),
    )
    assert actual == base64.b64decode(expected_text)

    await group_service.save("vip", "VIP-зона обновлена", "neon")
    preserved = await groups.get("vip")
    assert preserved is not None
    assert preserved.manager_password_verifier == updated.manager_password_verifier

    workstations = InMemoryWorkstationRepository()
    service = WorkstationService(workstations, groups=groups)
    workstation = await service.register("device-vip", "VIP-01", group_id="vip")
    assert workstation.manager_password_verifier == updated.manager_password_verifier
    assert to_proto(workstation).manager_password_verifier == ""
    assert (
        to_proto(workstation, include_manager_password_verifier=True).manager_password_verifier
        == updated.manager_password_verifier
    )


@pytest.mark.asyncio
async def test_manager_password_rejects_short_values_and_unknown_group() -> None:
    groups = InMemoryWorkstationGroupRepository()
    service = WorkstationGroupService(groups)

    with pytest.raises(ApplicationError):
        await service.set_manager_password("vip", "short")

    await service.save("main", "Обычный зал", "standard")
    with pytest.raises(ApplicationError):
        await service.set_manager_password("missing", "manager-secret")
