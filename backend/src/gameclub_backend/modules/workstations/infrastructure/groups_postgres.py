import datetime
import json

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gameclub_backend.infrastructure.database import EngineProvider, open_session
from gameclub_backend.modules.workstations.domain import (
    LockdownDeploymentMode,
    LockdownPolicy,
    WorkstationGroup,
)


def policy_to_json(policy: LockdownPolicy) -> str:
    return json.dumps(
        {
            "deployment_mode": policy.deployment_mode.value,
            "shell_enabled": policy.shell_enabled,
            "user_self_login_enabled": policy.user_self_login_enabled,
            "lock_after_session": policy.lock_after_session,
            "restart_after_session": policy.restart_after_session,
            "hidden_drives": list(policy.hidden_drives),
            "block_external_storage": policy.block_external_storage,
            "disable_start_menu": policy.disable_start_menu,
            "disable_desktop_switching": policy.disable_desktop_switching,
            "blocked_window_rules": list(policy.blocked_window_rules),
            "allowed_application_ids": list(policy.allowed_application_ids),
            "version": policy.version,
        },
        separators=(",", ":"),
    )


def policy_from_json(value: str | None) -> LockdownPolicy:
    if not value:
        return LockdownPolicy()
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            return LockdownPolicy()

        def read_bool(name: str, default: bool) -> bool:
            candidate = payload.get(name, default)
            if not isinstance(candidate, bool):
                raise ValueError(f"{name} must be a boolean")
            return candidate

        def read_strings(name: str) -> tuple[str, ...]:
            candidate = payload.get(name, [])
            if not isinstance(candidate, list) or any(
                not isinstance(item, str) for item in candidate
            ):
                raise ValueError(f"{name} must be a list of strings")
            return tuple(candidate)

        deployment_mode = payload.get("deployment_mode", "app_gate")
        version = payload.get("version", 1)
        if (
            not isinstance(deployment_mode, str)
            or not isinstance(version, int)
            or isinstance(version, bool)
        ):
            raise ValueError("Lockdown policy scalar has an invalid type")
        return LockdownPolicy(
            deployment_mode=LockdownDeploymentMode(deployment_mode),
            shell_enabled=read_bool("shell_enabled", True),
            user_self_login_enabled=read_bool("user_self_login_enabled", True),
            lock_after_session=read_bool("lock_after_session", True),
            restart_after_session=read_bool("restart_after_session", True),
            hidden_drives=read_strings("hidden_drives"),
            block_external_storage=read_bool("block_external_storage", False),
            disable_start_menu=read_bool("disable_start_menu", False),
            disable_desktop_switching=read_bool("disable_desktop_switching", False),
            blocked_window_rules=read_strings("blocked_window_rules"),
            allowed_application_ids=read_strings("allowed_application_ids"),
            version=version,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        # A malformed stored policy must never enable a more permissive unknown
        # configuration. The domain safe default keeps the app gate active.
        return LockdownPolicy()


class WorkstationGroupBase(DeclarativeBase):
    pass


class WorkstationGroupModel(WorkstationGroupBase):
    __tablename__ = "workstation_groups"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    theme: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    manager_password_verifier: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    lockdown_policy_json: Mapped[str] = mapped_column(Text, default="{}")

    def to_domain(self) -> WorkstationGroup:
        return WorkstationGroup(
            id=self.id,
            name=self.name,
            theme=self.theme,
            updated_at=self.updated_at,
            manager_password_verifier=self.manager_password_verifier,
            lockdown_policy=policy_from_json(self.lockdown_policy_json),
        )

    @classmethod
    def from_domain(cls, group: WorkstationGroup) -> "WorkstationGroupModel":
        return cls(
            id=group.id,
            name=group.name,
            theme=group.theme,
            updated_at=group.updated_at or datetime.datetime.now(datetime.UTC),
            manager_password_verifier=group.manager_password_verifier,
            lockdown_policy_json=policy_to_json(group.lockdown_policy),
        )


class PostgresWorkstationGroupRepository:
    def __init__(self, engine_provider: EngineProvider) -> None:
        self._engine_provider = engine_provider

    async def get(self, group_id: str) -> WorkstationGroup | None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(WorkstationGroupModel, group_id)
            return model.to_domain() if model else None

    async def list(self) -> list[WorkstationGroup]:
        async with open_session(self._engine_provider) as session:
            result = await session.scalars(
                select(WorkstationGroupModel).order_by(WorkstationGroupModel.id)
            )
            return [model.to_domain() for model in result]

    async def save(self, group: WorkstationGroup) -> WorkstationGroup:
        async with open_session(self._engine_provider) as session:
            model = await session.get(WorkstationGroupModel, group.id)
            if model is None:
                session.add(WorkstationGroupModel.from_domain(group))
            else:
                model.name = group.name
                model.theme = group.theme
                model.updated_at = group.updated_at or datetime.datetime.now(datetime.UTC)
                model.manager_password_verifier = group.manager_password_verifier
                model.lockdown_policy_json = policy_to_json(group.lockdown_policy)
            await session.commit()
            return group

    async def delete(self, group_id: str) -> None:
        async with open_session(self._engine_provider) as session:
            model = await session.get(WorkstationGroupModel, group_id)
            if model is not None:
                await session.delete(model)
                await session.commit()
