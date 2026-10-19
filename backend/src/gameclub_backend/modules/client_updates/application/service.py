"""Authorized deployment mutations; all device reports stay bound to their identity."""

from __future__ import annotations

import dataclasses
import datetime
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.domain.equipment import EquipmentType
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.application.ports import (
    ClientFactConfirmation,
    DeploymentRepository,
)
from gameclub_backend.modules.client_updates.domain import (
    Deployment,
    DeploymentPhase,
    DeviceUpdateReport,
)
from gameclub_backend.modules.sessions.application.ports import SessionAdmission
from gameclub_backend.modules.workstations.application.ports import (
    WorkstationDeploymentFreeze,
    WorkstationRepository,
)
from gameclub_backend.modules.workstations.domain import WorkstationStatus


class ClientUpdateService:
    def __init__(
        self,
        deployments: DeploymentRepository,
        admission: SessionAdmission,
        workstations: WorkstationRepository,
        park: WorkstationDeploymentFreeze,
        financial: ClientFactConfirmation | None = None,
    ) -> None:
        self._deployments = deployments
        self._admission = admission
        self._workstations = workstations
        self._park = park
        self._financial = financial

    @staticmethod
    def require_operator(principal: Principal) -> None:
        if principal.subject_type is not SubjectType.OPERATOR or not principal.can(
            "workstations.manage"
        ):
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED, "Workstation management permission required"
            )

    async def _targets(self) -> dict[str, uuid.UUID]:
        items = await self._workstations.list()
        return {
            item.device_id: item.id
            for item in items
            if item.equipment_type is EquipmentType.PC
            and item.archived_at is None
            and item.device_id is not None
        }

    async def _barrier_targets(self) -> tuple[uuid.UUID, ...]:
        # An archived PC may still have a session; it must not bypass the idle check.
        return tuple(
            item.id
            for item in await self._workstations.list_including_archived()
            if item.equipment_type is EquipmentType.PC
        )

    async def _require_target_device(self, value: Deployment, device_id: str) -> None:
        workstation = await self._workstations.get_by_device_id(device_id)
        if (
            workstation is None
            or workstation.archived_at is not None
            or workstation.status is WorkstationStatus.DISABLED
            or value.targets.get(device_id) != workstation.id
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Device enrollment is not active")

    async def create(
        self, principal: Principal, operation_id: uuid.UUID, release_id: str, executable_sha256: str
    ) -> Deployment:
        self.require_operator(principal)
        return await self._deployments.create(
            Deployment(
                id=uuid.uuid4(),
                operation_id=operation_id,
                release_id=release_id,
                executable_sha256=executable_sha256,
                targets=await self._targets(),
                created_by=principal.subject_id,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )

    async def get(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        value = await self._deployments.get(deployment_id)
        if value is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Deployment not found")
        return value

    async def latest(self, principal: Principal) -> Deployment | None:
        self.require_operator(principal)
        return await self._deployments.latest()

    async def _require_financial_confirmation(self, value: Deployment) -> None:
        for report in value.reports.values():
            if report.session_id is not None:
                if self._financial is None or not await self._financial.is_confirmed(
                    report.device_id,
                    report.session_id,
                    report.last_sequence,
                    report.last_payload_hash,
                ):
                    raise ApplicationError(
                        ErrorCode.CONFLICT,
                        f"Financial facts are not confirmed for {report.device_id}",
                    )

    async def refresh_targets(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        async with self._deployments.change(deployment_id) as value:
            if value.phase is not DeploymentPhase.POLLING:
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Final preparation already froze membership"
                )
            current = await self._targets()
            if any(
                current.get(device_id) != workstation_id
                for device_id, workstation_id in value.targets.items()
            ):
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Cannot remove or replace deployment targets"
                )
            value.targets = current
            value.round_id = uuid.uuid4()
            value.reports.clear()
            return value

    async def prepare(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        async with self._deployments.change(deployment_id) as value:
            await self._park.freeze(value.id)
            if value.targets != await self._targets():
                raise ApplicationError(ErrorCode.CONFLICT, "Workstation membership changed")
            if value.phase is DeploymentPhase.PREPARING:
                return value
            await self._require_financial_confirmation(value)
            value.begin_preparation(datetime.datetime.now(datetime.UTC))
            await self._admission.block(value.id, await self._barrier_targets())
            return value

    async def server_ready(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        async with self._deployments.change(deployment_id) as value:
            if value.phase is not DeploymentPhase.PREPARING:
                raise ApplicationError(ErrorCode.CONFLICT, "Deployment is not preparing")
            value.server_ready = True
            return value

    async def authorize(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        async with self._deployments.change(deployment_id) as value:
            await self._park.freeze(value.id)
            if value.targets != await self._targets():
                raise ApplicationError(ErrorCode.CONFLICT, "Workstation membership changed")
            if value.phase is DeploymentPhase.AUTHORIZED:
                return value
            await self._require_financial_confirmation(value)
            value.authorize(datetime.datetime.now(datetime.UTC))
            return value

    async def begin_install(
        self, principal: Principal, deployment_id: uuid.UUID, report: DeviceUpdateReport
    ) -> Deployment:
        if (
            principal.subject_type is not SubjectType.UPDATER
            or not principal.can("client_updates.report")
            or principal.subject_id != report.device_id
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Updater identity required")
        async with self._deployments.change(deployment_id) as value:
            await self._require_target_device(value, principal.subject_id)
            previous = value.reports.get(principal.subject_id)
            if (
                not value.may_install(principal.subject_id)
                or previous is None
                or previous.stage not in {"ready", "installing"}
                or previous.instance_id != report.instance_id
                or report.stage != "installing"
                or not report.ready
                or report.active_session
                or report.pending_facts != 0
                or report.error_code is not None
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Installation is not permitted")
            if previous.stage == "installing" and previous.sequence != report.sequence:
                raise ApplicationError(ErrorCode.CONFLICT, "Installation was already started")
            value.report(
                dataclasses.replace(report, received_at=datetime.datetime.now(datetime.UTC))
            )
            await self._require_financial_confirmation(value)
            return value

    async def report(
        self, principal: Principal, deployment_id: uuid.UUID, report: DeviceUpdateReport
    ) -> Deployment:
        if (
            principal.subject_type is not SubjectType.UPDATER
            or not principal.can("client_updates.report")
            or principal.subject_id != report.device_id
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Updater identity required")
        async with self._deployments.change(deployment_id) as value:
            await self._require_target_device(value, principal.subject_id)
            previous = value.reports.get(principal.subject_id)
            if report.stage in {"installing", "verifying", "installed"} and (
                previous is None or previous.stage not in {"installing", "verifying", "installed"}
            ):
                raise ApplicationError(ErrorCode.CONFLICT, "Installation was not started")
            value.report(
                dataclasses.replace(report, received_at=datetime.datetime.now(datetime.UTC))
            )
            return value

    async def confirm_gui(
        self, principal: Principal, deployment_id: uuid.UUID, release_id: str
    ) -> Deployment:
        if (
            principal.subject_type is not SubjectType.DEVICE
            or not principal.can("workstations.connect")
            or principal.can("client_updates.report")
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Device identity required")
        async with self._deployments.change(deployment_id) as value:
            await self._require_target_device(value, principal.subject_id)
            value.confirm_gui(principal.subject_id, release_id)
            return value

    async def current(self, principal: Principal) -> Deployment | None:
        if not (
            (principal.subject_type is SubjectType.UPDATER and principal.can("client_updates.poll"))
            or (
                principal.subject_type is SubjectType.DEVICE
                and principal.can("workstations.connect")
            )
        ):
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED, "Device or updater identity required"
            )
        value = await self._deployments.latest_for_device(principal.subject_id)
        if value is not None:
            await self._require_target_device(value, principal.subject_id)
        return value

    async def agent_command(self, principal: Principal, instance_id: uuid.UUID) -> dict:
        if principal.subject_type is not SubjectType.UPDATER:
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Updater identity required")
        value = await self.current(principal)
        if value is None:
            return {"deployment": None, "backend_protocol": 1}
        report = value.reports.get(principal.subject_id)
        return {
            "deployment": {
                "id": value.id,
                "round_id": value.round_id,
                "release_id": value.release_id,
                "executable_sha256": value.executable_sha256,
                "phase": value.phase.value,
                "block_gui": value.phase
                in {DeploymentPhase.PREPARING, DeploymentPhase.AUTHORIZED, DeploymentPhase.FAILED},
                "may_install": bool(
                    value.may_install(principal.subject_id)
                    and report
                    and report.instance_id == instance_id
                ),
                "last_sequence": report.sequence if report else 0,
                "report_stage": report.stage if report else None,
                "gui_confirmed": value.gui_confirmations.get(principal.subject_id)
                == value.release_id,
            },
            "backend_protocol": 1,
        }

    async def retry(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        async with self._deployments.change(deployment_id) as value:
            await self._park.freeze(value.id)
            if value.targets != await self._targets():
                raise ApplicationError(ErrorCode.CONFLICT, "Workstation membership changed")
            value.retry_preparation()
            await self._admission.block(value.id, await self._barrier_targets())
            return value

    async def finish(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        async with self._deployments.change(deployment_id) as value:
            if value.phase is DeploymentPhase.COMPLETED:
                return value
            await self._require_financial_confirmation(value)
            value.finish()
            await self._admission.unblock(value.id)
            await self._park.unfreeze(value.id)
            return value
