import datetime

from gameclub.v1 import workstations_pb2
from gameclub_backend.modules.workstations.application.groups import WorkstationGroupService
from gameclub_backend.modules.workstations.domain import (
    LockdownDeploymentMode,
    LockdownPolicy,
)
from gameclub_backend.modules.workstations.infrastructure.groups_memory import (
    InMemoryWorkstationGroupRepository,
)
from gameclub_backend.modules.workstations.infrastructure.groups_postgres import (
    policy_from_json,
    policy_to_json,
)
from gameclub_backend.presentation.grpc.services import (
    from_lockdown_policy_proto,
    to_lockdown_policy_proto,
)


def test_lockdown_policy_round_trips_through_storage_and_proto() -> None:
    policy = LockdownPolicy(
        deployment_mode=LockdownDeploymentMode.SHELL_LAUNCHER,
        user_self_login_enabled=False,
        lock_after_session=True,
        restart_after_session=False,
        hidden_drives=("C:", "D:"),
        block_external_storage=True,
        disable_start_menu=True,
        disable_desktop_switching=True,
        blocked_window_rules=("CabinetWClass", "*cmd*"),
        allowed_application_ids=("steam", "battle-net"),
        version=4,
    )

    restored = policy_from_json(policy_to_json(policy))
    proto = to_lockdown_policy_proto(restored)
    from_proto = from_lockdown_policy_proto(proto)

    assert restored == policy
    assert proto.deployment_mode == "shell_launcher"
    assert from_proto == policy


def test_malformed_or_permissive_policy_data_falls_back_to_safe_app_gate() -> None:
    assert policy_from_json("not-json") == LockdownPolicy()
    assert policy_from_json('{"shell_enabled":"false"}') == LockdownPolicy()
    assert policy_from_json('{"hidden_drives":["C"]}') == LockdownPolicy()
    assert policy_from_json('{"version":true}') == LockdownPolicy()


async def test_group_policy_is_preserved_when_only_theme_changes() -> None:
    repository = InMemoryWorkstationGroupRepository()
    service = WorkstationGroupService(repository)
    policy = LockdownPolicy(
        deployment_mode=LockdownDeploymentMode.ASSIGNED_ACCESS,
        block_external_storage=True,
    )

    await service.save("vip", "VIP-зона", "vip", policy)
    updated = await service.save("vip", "VIP-зона 2", "neon")

    assert updated.lockdown_policy == policy
    assert updated.updated_at is not None
    assert updated.updated_at >= datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=5)


def test_empty_policy_proto_uses_safe_defaults() -> None:
    policy = from_lockdown_policy_proto(workstations_pb2.WorkstationLockdownPolicy())

    assert policy == LockdownPolicy()
