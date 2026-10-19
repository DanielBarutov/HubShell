"""V2 вход: новый server session и один подписанный снимок для локального ledger."""

from __future__ import annotations

import dataclasses
import datetime
import typing
import uuid

from gameclub.v2 import offline_session_service_pb2, offline_session_snapshot_pb2
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.catalog.domain import TariffLifecycle
from gameclub_backend.modules.client_groups.application.service import ClientGroupService
from gameclub_backend.modules.clients.application.bonus import (
    BonusGameQuote,
    BonusPurchaseConfirmation,
)
from gameclub_backend.modules.clients.application.portal import (
    ClientPortalService,
    ClientPortalSnapshot,
)
from gameclub_backend.modules.entitlements.domain import EntitlementStatus
from gameclub_backend.modules.eventing_v2.application.bonus_budget import (
    BonusBudgetRequest,
    BonusBudgetService,
)
from gameclub_backend.modules.eventing_v2.application.lease import V2SessionLease
from gameclub_backend.modules.eventing_v2.application.snapshot import (
    V2OfflineSnapshotFactory,
    V2OfflineSnapshotInput,
)
from gameclub_backend.modules.eventing_v2.application.snapshot_issue import (
    V2SignedSnapshotIssue,
    V2SnapshotIssueService,
)
from gameclub_backend.modules.eventing_v2.infrastructure.snapshot_protobuf import (
    V2OfflineSnapshotSigner,
    sign_offline_session_snapshot,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.domain import SessionStatus
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import WorkstationSessionMode


class Clock(typing.Protocol):
    def now(self) -> datetime.datetime:
        """Return a timezone-aware UTC time."""


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


@dataclasses.dataclass(frozen=True)
class V2PortalResumeResult:
    client_id: uuid.UUID
    portal_access_token: str
    portal_access_expires_in: int


@dataclasses.dataclass(frozen=True)
class V2PortalPurchaseResult:
    portal: ClientPortalSnapshot
    purchased_package: offline_session_snapshot_pb2.SignedOfflineSessionSnapshot


class V2OfflineLoginService:
    """Does not reuse a V1 session and never asks the server to confirm minutes."""

    def __init__(
        self,
        *,
        workstations: WorkstationService,
        client_portal: ClientPortalService,
        sessions: SessionService,
        client_groups: ClientGroupService,
        snapshot_issues: V2SnapshotIssueService,
        signing_key_id: str,
        signer: V2OfflineSnapshotSigner,
        policy_version: str,
        token_service: JwtTokenService | None = None,
        clock: Clock | None = None,
        bonus_budgets: BonusBudgetService | None = None,
    ) -> None:
        if not signing_key_id.strip() or not policy_version.strip():
            raise ValueError("V2 signing key and policy version are required")
        self._workstations = workstations
        self._client_portal = client_portal
        self._sessions = sessions
        self._client_groups = client_groups
        self._snapshot_issues = snapshot_issues
        self._signing_key_id = signing_key_id.strip()
        self._signer = signer
        self._policy_version = policy_version.strip()
        self._token_service = token_service
        self._clock = clock or UtcClock()
        self._bonus_budgets = bonus_budgets

    async def enable_minute_bonus(
        self, request: BonusBudgetRequest, principal: Principal
    ) -> offline_session_service_pb2.SignedMinuteBonusBudget:
        await self._validate_bonus_session(request)
        grant = await self._bonus_budgets.issue(request, principal)
        payload = offline_session_service_pb2.MinuteBonusBudgetPayload(
            grant_id=str(grant.id),
            schema_version=1,
            grant_version=grant.version,
            client_id=str(request.client_id),
            session_id=str(request.session_id),
            device_id=request.device_id,
            snapshot_id=str(request.snapshot_id),
            snapshot_version=request.snapshot_version,
            checkpoint_sequence=request.last_sequence,
            checkpoint_hash=request.last_payload_hash,
            budget_cents=grant.budget_cents,
            payment_limit_bps=grant.payment_limit_bps,
            idempotency_key=request.idempotency_key,
        )
        payload.issued_at.FromDatetime(grant.issued_at)
        return offline_session_service_pb2.SignedMinuteBonusBudget(
            payload=payload,
            signing_key_id=self._signing_key_id,
            signature=self._signer.sign(payload.SerializeToString(deterministic=True)),
        )

    async def quote_minute_bonus(
        self, request: BonusBudgetRequest, principal: Principal
    ) -> BonusGameQuote:
        await self._validate_bonus_session(request)
        return await self._bonus_budgets.quote(request, principal)

    async def cancel_minute_bonus(self, request: BonusBudgetRequest, principal: Principal) -> None:
        await self._validate_bonus_session(request, require_active=False)
        await self._bonus_budgets.cancel(request, principal)

    async def _validate_bonus_session(
        self, request: BonusBudgetRequest, *, require_active: bool = True
    ) -> None:
        if self._bonus_budgets is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "Minute bonus is not configured"
            )
        session = await self._sessions.get(request.session_id)
        workstation = await self._workstations.get_by_device_id(request.device_id)
        if (
            session is None
            or (require_active and session.status is not SessionStatus.ACTIVE)
            or session.source != "local_ledger"
            or session.client_id != request.client_id
            or session.workstation_id != workstation.id
        ):
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED, "No active client session on this device"
            )

    async def login(
        self,
        *,
        device_id: str,
        identifier: str,
        password: str,
        idempotency_key: str,
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot:
        client = await self._client_portal.authenticate(identifier, password)
        if client.password_reset_required:
            if self._token_service is None:
                raise ApplicationError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "V2 password reset is not configured",
                )
            token, _ = self._token_service.issue_access_token(
                Principal(
                    subject_id=str(client.id),
                    subject_type=SubjectType.CLIENT,
                    roles=frozenset({"client"}),
                    permissions=frozenset({"client.portal"}),
                    device_id=device_id,
                    password_reset_required=True,
                )
            )
            return offline_session_snapshot_pb2.SignedOfflineSessionSnapshot(
                password_reset_required=True,
                password_reset_token=token,
            )
        return await self._start_v2_session_and_issue_snapshot(
            client_id=client.id,
            device_id=device_id,
            idempotency_key=idempotency_key,
        )

    async def change_password(
        self,
        *,
        client_id: uuid.UUID,
        device_id: str,
        new_password: str,
    ) -> None:
        del device_id
        client = await self._client_portal.get_client(client_id)
        if not client.password_reset_required:
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "Password reset is not pending",
            )
        await self._client_portal.set_password(client_id, new_password)

    async def resume_portal(
        self,
        *,
        device_id: str,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> V2PortalResumeResult:
        """Issue a fresh portal token only for this device's existing active V2 session."""
        if self._token_service is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "V2 portal authentication is not configured",
            )
        workstation = await self._workstations.get_by_device_id(device_id)
        session = await self._sessions.get(session_id)
        if (
            session is None
            or session.status is not SessionStatus.ACTIVE
            or session.source != "local_ledger"
            or session.client_id != client_id
            or session.workstation_id != workstation.id
            or workstation.session_mode is not WorkstationSessionMode.LOCAL_LEDGER
            or not await self._snapshot_issues.has_active_lease(
                session_id,
                client_id,
                device_id,
            )
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "No active V2 session matches this device and account",
            )

        token, expires_in = self._token_service.issue_access_token(
            Principal(
                subject_id=str(client_id),
                subject_type=SubjectType.CLIENT,
                roles=frozenset({"client"}),
                permissions=frozenset({"client.portal"}),
                device_id=device_id,
            )
        )
        return V2PortalResumeResult(
            client_id=client_id,
            portal_access_token=token,
            portal_access_expires_in=expires_in,
        )

    async def stop_session(
        self,
        *,
        device_id: str,
        session_id: uuid.UUID,
        client_id: uuid.UUID,
    ) -> None:
        workstation = await self._workstations.get_by_device_id(device_id)
        session = await self._sessions.get(session_id)
        if (
            session is None
            or session.source != "local_ledger"
            or session.client_id != client_id
            or session.workstation_id != workstation.id
            or workstation.session_mode is not WorkstationSessionMode.LOCAL_LEDGER
        ):
            raise ApplicationError(
                ErrorCode.PERMISSION_DENIED,
                "V2 session does not belong to this client and device",
            )
        await self._sessions.stop(session_id, device_id)

    async def register(
        self,
        *,
        device_id: str,
        nickname: str,
        phone: str,
        password: str,
        idempotency_key: str,
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot:
        """Create a profile in the preserved database, then open only a V2 session."""
        client = await self._client_portal.register(nickname, phone, password)
        return await self._start_v2_session_and_issue_snapshot(
            client_id=client.id,
            device_id=device_id,
            idempotency_key=idempotency_key,
        )

    async def get_portal_snapshot(
        self,
        *,
        client_id: uuid.UUID,
        device_id: str,
        limit: int,
    ) -> ClientPortalSnapshot:
        return await self._client_portal.snapshot_for_device(
            client_id,
            device_id,
            max(1, min(limit, 100)),
        )

    async def get_active_package_snapshot(
        self, *, client_id: uuid.UUID, device_id: str
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot | None:
        workstation = await self._workstations.get_by_device_id(device_id)
        sessions = [
            item
            for item in await self._sessions.list_for_client(client_id)
            if item.status is SessionStatus.ACTIVE
            and item.source == "local_ledger"
            and item.workstation_id == workstation.id
        ]
        if len(sessions) != 1 or not await self._snapshot_issues.has_active_lease(
            sessions[0].id, client_id, device_id
        ):
            return None
        source = await self._client_portal.v2_offline_snapshot_for_device(client_id, device_id)
        active = [item for item in source.entitlements if item.status is EntitlementStatus.ACTIVE]
        if not active:
            return None
        if len(active) != 1:
            raise ApplicationError(ErrorCode.CONFLICT, "Multiple active packages")
        package = active[0]
        if not package.is_compatible(workstation.group_id):
            raise ApplicationError(ErrorCode.CONFLICT, "Active package is incompatible with device")
        payload = V2OfflineSnapshotFactory.create_payload(
            V2OfflineSnapshotInput(
                snapshot_id=uuid.uuid5(sessions[0].id, f"active-package:{package.id}"),
                snapshot_version=1,
                issued_at=self._clock.now(),
                client=source.client,
                session=sessions[0],
                device_id=device_id,
                workstation_zone_id=workstation.group_id,
                debt_limit_cents=0,
                login_grant_remaining_minutes=0,
                entitlements=(package,),
                tariffs=(),
                policy_version=self._policy_version,
            )
        )
        return sign_offline_session_snapshot(payload, self._signing_key_id, self._signer)

    async def purchase_entitlement(
        self,
        *,
        client_id: uuid.UUID,
        device_id: str,
        tariff_id: uuid.UUID,
        idempotency_key: str,
        bonus_confirmation: BonusPurchaseConfirmation | None = None,
        principal: Principal | None = None,
    ) -> V2PortalPurchaseResult:
        workstation = await self._workstations.get_by_device_id(device_id)
        active = [
            item
            for item in await self._sessions.list_for_client(client_id)
            if item.status is SessionStatus.ACTIVE
            and item.source == "local_ledger"
            and item.workstation_id == workstation.id
        ]
        if len(active) != 1 or not await self._snapshot_issues.has_active_lease(
            active[0].id, client_id, device_id
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "No active V2 session for package purchase")
        portal = await self._client_portal.purchase_entitlement(
            client_id,
            tariff_id,
            idempotency_key,
            device_id=device_id,
            **(
                {"bonus_confirmation": bonus_confirmation, "principal": principal}
                if bonus_confirmation is not None
                else {}
            ),
        )
        package = portal.purchased_entitlement
        tariff = portal.purchased_tariff
        if package is None or tariff is None:
            raise ApplicationError(ErrorCode.CONFLICT, "Purchased package receipt is unavailable")
        tariff = dataclasses.replace(
            tariff,
            duration_minutes=package.duration_minutes,
            price_cents=package.price_cents,
            group_id=package.zone_id,
            active=True,
            lifecycle=TariffLifecycle.PUBLISHED,
        )
        payload = V2OfflineSnapshotFactory.create_payload(
            V2OfflineSnapshotInput(
                snapshot_id=uuid.uuid5(active[0].id, idempotency_key.strip()),
                snapshot_version=1,
                issued_at=self._clock.now(),
                client=portal.client,
                session=active[0],
                device_id=device_id,
                workstation_zone_id=workstation.group_id,
                debt_limit_cents=0,
                login_grant_remaining_minutes=0,
                entitlements=(
                    dataclasses.replace(package, remaining_minutes=package.duration_minutes),
                ),
                tariffs=(tariff,),
                policy_version=self._policy_version,
            )
        )
        payload.purchase_idempotency_key = idempotency_key.strip()
        payload.purchase_money_cents = package.price_cents - package.bonus_amount_cents
        payload.purchase_bonus_cents = package.bonus_amount_cents
        return V2PortalPurchaseResult(
            portal, sign_offline_session_snapshot(payload, self._signing_key_id, self._signer)
        )

    async def quote_entitlement(
        self, *, client_id: uuid.UUID, device_id: str, tariff_id: uuid.UUID, use_bonus: bool
    ) -> BonusGameQuote:
        workstation = await self._workstations.get_by_device_id(device_id)
        active = [
            item
            for item in await self._sessions.list_for_client(client_id)
            if item.status is SessionStatus.ACTIVE
            and item.source == "local_ledger"
            and item.workstation_id == workstation.id
        ]
        if len(active) != 1 or not await self._snapshot_issues.has_active_lease(
            active[0].id, client_id, device_id
        ):
            raise ApplicationError(ErrorCode.CONFLICT, "No active V2 session for package quote")
        return await self._client_portal.quote_entitlement(
            client_id, tariff_id, device_id, use_bonus
        )

    async def activate_entitlement(
        self,
        *,
        client_id: uuid.UUID,
        device_id: str,
        entitlement_id: uuid.UUID,
    ) -> ClientPortalSnapshot:
        return await self._client_portal.activate_entitlement(
            client_id,
            entitlement_id,
            device_id=device_id,
        )

    async def _start_v2_session_and_issue_snapshot(
        self,
        *,
        client_id: uuid.UUID,
        device_id: str,
        idempotency_key: str,
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot:
        workstation = await self._workstations.get_by_device_id(device_id)
        if workstation.session_mode is not WorkstationSessionMode.LOCAL_LEDGER:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Workstation is not configured for the V2 local ledger mode",
            )
        session = await self._sessions.start(
            workstation_id=workstation.id,
            client_id=client_id,
            created_by=f"client:{client_id}",
            source="local_ledger",
            idempotency_key=idempotency_key,
            device_id=device_id,
            persist=False,
        )
        source = await self._client_portal.v2_offline_snapshot_for_device(client_id, device_id)
        group = (
            await self._client_groups.get(source.client.client_group_id)
            if source.client.client_group_id is not None
            else await self._client_groups.get_default()
        )
        if not group.active:
            raise ApplicationError(ErrorCode.CONFLICT, "Client group is inactive")
        issued_at = self._clock.now()
        lease = V2SessionLease(
            session_id=session.id,
            client_id=client_id,
            device_id=device_id,
            snapshot_id=uuid.uuid4(),
            snapshot_version=1,
            policy_version=self._policy_version,
            issued_at=issued_at,
        )
        payload = V2OfflineSnapshotFactory.create_payload(
            V2OfflineSnapshotInput(
                snapshot_id=lease.snapshot_id,
                snapshot_version=lease.snapshot_version,
                issued_at=issued_at,
                client=source.client,
                session=session,
                device_id=device_id,
                workstation_zone_id=workstation.group_id,
                debt_limit_cents=group.negative_balance_limit_cents
                if group.allow_negative_balance
                else 0,
                login_grant_remaining_minutes=session.login_grant_minutes,
                entitlements=source.entitlements,
                tariffs=source.tariffs,
                policy_version=lease.policy_version,
            )
        )
        signed_snapshot = sign_offline_session_snapshot(
            payload,
            self._signing_key_id,
            self._signer,
        )
        if self._token_service is None:
            raise ApplicationError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "V2 portal authentication is not configured",
            )
        portal_access_token, portal_access_expires_in = self._token_service.issue_access_token(
            Principal(
                subject_id=str(client_id),
                subject_type=SubjectType.CLIENT,
                roles=frozenset({"client"}),
                permissions=frozenset({"client.portal"}),
                device_id=device_id,
            )
        )
        signed_snapshot.portal_access_token = portal_access_token
        signed_snapshot.portal_access_expires_in = portal_access_expires_in
        result = await self._snapshot_issues.issue_with_new_session(
            V2SignedSnapshotIssue(lease=lease, signed_snapshot=signed_snapshot),
            session,
        )
        return result.signed_snapshot
