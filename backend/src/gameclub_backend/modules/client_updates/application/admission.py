"""Release compatibility at the public Sessions admission boundary."""

from __future__ import annotations

import uuid

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.client_updates.application.ports import DeploymentRepository
from gameclub_backend.modules.workstations.application.ports import WorkstationRepository
from gameclub_backend.modules.workstations.domain import EquipmentType


class ClientReleaseAdmissionService:
    def __init__(
        self, deployments: DeploymentRepository, workstations: WorkstationRepository
    ) -> None:
        self._deployments = deployments
        self._workstations = workstations

    async def require_release(self, workstation_id: uuid.UUID) -> None:
        policy = await self._deployments.current_policy()
        if policy is None:
            return
        workstation = await self._workstations.get(workstation_id)
        if workstation is not None and workstation.equipment_type is not EquipmentType.PC:
            return
        release = None
        if workstation is not None and workstation.device_id and workstation.installation_id:
            release = await self._deployments.running_release(
                workstation.device_id,
                workstation.id,
                workstation.installation_id,
            )
        if release not in policy.accepted_release_ids:
            raise ApplicationError(
                ErrorCode.CONFLICT, "Client release must be updated before new access"
            )
