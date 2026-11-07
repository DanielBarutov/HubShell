"""Authorized deployment mutations; all device reports stay bound to their identity."""

from __future__ import annotations

import dataclasses
import datetime
import re
import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.domain.equipment import EquipmentType
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.client_updates.application.ports import (
    ClientFactConfirmation,
    DeploymentRepository,
)
from gameclub_backend.modules.client_updates.application.releases import ClientReleaseStore
from gameclub_backend.modules.client_updates.domain import (
    ClientReleasePolicy,
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
        releases: ClientReleaseStore | None = None,
    ) -> None:
        self._deployments = deployments
        self._admission = admission
        self._workstations = workstations
        self._park = park
        self._financial = financial
        self._releases = releases

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
        self,
        principal: Principal,
        operation_id: uuid.UUID,
        release_id: str,
        executable_sha256: str,
        device_id: str | None = None,
    ) -> Deployment:
        self.require_operator(principal)
        targets = await self._targets()
        if device_id is not None:
            if device_id not in targets:
                raise ApplicationError(ErrorCode.NOT_FOUND, "Active target PC not found")
            targets = {device_id: targets[device_id]}
        return await self._deployments.create(
            Deployment(
                id=uuid.uuid4(),
                operation_id=operation_id,
                release_id=release_id,
                executable_sha256=executable_sha256,
                targets=targets,
                independent=device_id is not None,
                created_by=principal.subject_id,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )

    async def publish_policy(
        self,
        principal: Principal,
        operation_id: uuid.UUID,
        release_id: str,
        accepted_release_ids: tuple[str, ...],
    ) -> ClientReleasePolicy:
        self.require_operator(principal)
        if self._releases is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "Trusted release mirror is not configured"
            )
        executable_hash = await self._releases.executable_hash(release_id)
        async with self._deployments.policy_change(), self._admission.policy_change():
            return await self._deployments.publish_policy(
                ClientReleasePolicy(
                    operation_id,
                    release_id,
                    executable_hash,
                    tuple(sorted(set((release_id, *accepted_release_ids)))),
                    principal.subject_id,
                    datetime.datetime.now(datetime.UTC),
                )
            )

    async def release_policy(self, principal: Principal) -> ClientReleasePolicy | None:
        self.require_operator(principal)
        return await self._deployments.current_policy()

    async def get(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        value = await self._deployments.get(deployment_id)
        if value is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Deployment not found")
        return value

    async def latest(self, principal: Principal) -> Deployment | None:
        self.require_operator(principal)
        return await self._deployments.latest()

    async def fleet_status(self, principal: Principal) -> dict | None:
        self.require_operator(principal)
        policy = await self._deployments.current_policy()
        if policy is None:
            return None
        latest = await self._deployments.latest()
        if (
            latest is not None
            and not latest.independent
            and latest.phase is not DeploymentPhase.COMPLETED
        ):
            return None
        workstations = [
            item
            for item in await self._workstations.list()
            if item.equipment_type is EquipmentType.PC
            and item.archived_at is None
            and item.device_id
        ]
        device_ids = tuple(item.device_id for item in workstations)
        deliveries = await self._deployments.latest_for_devices(device_ids)
        observations = await self._deployments.release_observations(device_ids)
        now = datetime.datetime.now(datetime.UTC)
        devices = []
        for workstation in sorted(workstations, key=lambda item: item.device_id):
            device_id = workstation.device_id
            delivery = deliveries.get(device_id)
            if delivery is not None and delivery.targets.get(device_id) != workstation.id:
                delivery = None
            report = delivery.reports.get(device_id) if delivery else None
            observed = observations.get(device_id)
            installation_changed = observed is not None and (
                observed.workstation_id != workstation.id
                or observed.installation_id != workstation.installation_id
            )
            if installation_changed:
                observed = None
            running = report.running_release_id if report and not installation_changed else None
            received_at = report.received_at if report and not installation_changed else None
            if observed is not None and (
                received_at is None or observed.observed_at >= received_at
            ):
                running, received_at = observed.release_id, observed.observed_at
            confirmed = bool(
                delivery
                and delivery.release_id == policy.release_id
                and delivery.executable_sha256 == policy.executable_sha256
                and delivery.device_succeeded(device_id)
                and not installation_changed
                and not (
                    observed
                    and report
                    and observed.observed_at >= report.received_at
                    and observed.release_id != policy.release_id
                )
            )
            if workstation.status is WorkstationStatus.DISABLED:
                status = "disabled"
            elif confirmed:
                status = "confirmed"
            elif delivery is not None:
                status = delivery.device_status(device_id, now)
                if status == "confirmed":
                    status = "unreachable"
            else:
                status = "unreachable"
            if (
                status == "unreachable"
                and received_at is not None
                and 0 <= (now - received_at).total_seconds() <= 30
            ):
                status = "awaiting_agent"
            devices.append(
                {
                    "device_id": device_id,
                    "workstation_id": workstation.id,
                    "status": status,
                    "old_release_id": delivery.old_releases.get(device_id) if delivery else None,
                    "running_release_id": running,
                    "received_at": received_at,
                    "error_code": report.error_code if report else None,
                    "assigned_release_id": delivery.release_id if delivery else policy.release_id,
                    "deployment_id": delivery.id if delivery else None,
                    "round_id": delivery.round_id if delivery else None,
                }
            )
        confirmed_count = sum(item["status"] == "confirmed" for item in devices)
        if devices and confirmed_count == len(devices):
            phase = "completed"
        elif any(item["status"] in {"failed", "rolled_back"} for item in devices):
            phase = "failed"
        elif any(item["status"] in {"installing", "verifying", "waiting_gui"} for item in devices):
            phase = "authorized"
        else:
            phase = "polling"
        return {
            "id": policy.operation_id,
            "mode": "independent",
            "release_id": policy.release_id,
            "phase": phase,
            "created_at": policy.created_at,
            "observed_at": now,
            "confirmed": confirmed_count,
            "total": len(devices),
            "devices": devices,
        }

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
            if value.independent:
                raise ApplicationError(ErrorCode.CONFLICT, "Independent target is immutable")
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
            if not value.independent:
                await self._park.freeze(value.id)
            if not value.independent and value.targets != await self._targets():
                raise ApplicationError(ErrorCode.CONFLICT, "Workstation membership changed")
            if value.phase is DeploymentPhase.PREPARING:
                return value
            await self._require_financial_confirmation(value)
            value.begin_preparation(datetime.datetime.now(datetime.UTC))
            await self._admission.block(
                value.id,
                tuple(value.targets.values())
                if value.independent
                else await self._barrier_targets(),
            )
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
            if not value.independent:
                await self._park.freeze(value.id)
            if not value.independent and value.targets != await self._targets():
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
        if not principal.can("client_updates.poll"):
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED, "Updater polling permission required"
            )
        workstation = await self._workstations.get_by_device_id(principal.subject_id)
        if (
            workstation is None
            or workstation.archived_at is not None
            or workstation.status is WorkstationStatus.DISABLED
            or workstation.equipment_type is not EquipmentType.PC
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Device enrollment is not active")
        value = await self._deployments.assign_current(principal.subject_id, workstation.id)
        if value is not None:
            await self._require_target_device(value, principal.subject_id)
        if value is None:
            return {"deployment": None, "backend_protocol": 1}
        if value.independent:
            value = await self._advance_independent(value.id, principal.subject_id)
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

    async def _advance_independent(self, deployment_id: uuid.UUID, device_id: str) -> Deployment:
        async with self._deployments.change(deployment_id) as value:
            await self._require_target_device(value, device_id)
            now = datetime.datetime.now(datetime.UTC)
            if value.phase is DeploymentPhase.POLLING and value.all_ready(now):
                await self._require_financial_confirmation(value)
                await self._admission.block(value.id, tuple(value.targets.values()))
                value.begin_preparation(now)
            elif value.phase is DeploymentPhase.PREPARING and value.all_ready(now):
                await self._require_financial_confirmation(value)
                value.server_ready = True
                value.authorize(now)
            elif value.phase is DeploymentPhase.AUTHORIZED and value.device_succeeded(device_id):
                await self._require_financial_confirmation(value)
                value.finish()
                await self._admission.unblock(value.id)
            return value

    async def observe_gui_release(self, principal: Principal, release_id: str | None) -> bool:
        if release_id is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release_id
        ):
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Invalid GUI release id")
        if principal.subject_type is not SubjectType.DEVICE or not principal.can(
            "workstations.connect"
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Device identity required")
        workstation = await self._workstations.get_by_device_id(principal.subject_id)
        if (
            workstation is None
            or workstation.archived_at is not None
            or workstation.status is WorkstationStatus.DISABLED
            or workstation.equipment_type is not EquipmentType.PC
            or not workstation.installation_id
        ):
            raise ApplicationError(ErrorCode.PERMISSION_DENIED, "Device enrollment is not active")
        if release_id is not None and principal.installation_id != workstation.installation_id:
            raise ApplicationError(
                ErrorCode.UNAUTHENTICATED, "GUI installation enrollment is no longer active"
            )
        async with self._deployments.policy_change(), self._admission.policy_change():
            if release_id is not None:
                await self._deployments.observe_release(
                    principal.subject_id,
                    workstation.id,
                    workstation.installation_id,
                    release_id,
                )
            policy = await self._deployments.current_policy()
            return policy is None or release_id in policy.accepted_release_ids

    async def retry(self, principal: Principal, deployment_id: uuid.UUID) -> Deployment:
        self.require_operator(principal)
        async with self._deployments.change(deployment_id) as value:
            if not value.independent:
                await self._park.freeze(value.id)
            if not value.independent and value.targets != await self._targets():
                raise ApplicationError(ErrorCode.CONFLICT, "Workstation membership changed")
            value.retry_preparation()
            await self._admission.block(
                value.id,
                tuple(value.targets.values())
                if value.independent
                else await self._barrier_targets(),
            )
            return value

    async def retry_current(
        self,
        principal: Principal,
        deployment_id: uuid.UUID,
        operation_id: uuid.UUID,
    ) -> Deployment:
        self.require_operator(principal)
        async with self._deployments.change(deployment_id) as value:
            previous = next(
                (item for item in value.previous_attempts if item.operation_id == operation_id),
                None,
            )
            if previous is not None:
                if previous.created_by != principal.subject_id:
                    raise ApplicationError(
                        ErrorCode.CONFLICT, "Retry operation id belongs to another author"
                    )
                return value
            if not value.independent or value.phase is not DeploymentPhase.FAILED:
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Only a failed independent update can retry current release"
                )
            await self._require_target_device(value, next(iter(value.targets)))
            policy = await self._deployments.current_policy()
            if policy is None or self._releases is None:
                raise ApplicationError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE, "Current trusted release is not configured"
                )
            if await self._releases.executable_hash(policy.release_id) != policy.executable_sha256:
                raise ApplicationError(
                    ErrorCode.CONFLICT, "Current release differs from approved policy"
                )
            value.retry_current_release(
                policy, operation_id, principal.subject_id, datetime.datetime.now(datetime.UTC)
            )
            await self._admission.block(value.id, tuple(value.targets.values()))
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
