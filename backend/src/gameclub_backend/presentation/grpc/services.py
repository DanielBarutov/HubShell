import datetime
import json
import secrets
import typing
import uuid

import grpc
from google.protobuf import timestamp_pb2

from gameclub.v1 import (
    analytics_pb2,
    analytics_pb2_grpc,
    billing_pb2,
    billing_pb2_grpc,
    cash_shifts_pb2,
    cash_shifts_pb2_grpc,
    catalog_pb2,
    catalog_pb2_grpc,
    clients_pb2,
    clients_pb2_grpc,
    reservations_pb2,
    reservations_pb2_grpc,
    sessions_pb2,
    sessions_pb2_grpc,
    workstations_pb2,
    workstations_pb2_grpc,
)
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.analytics.application.service import AnalyticsService
from gameclub_backend.modules.analytics.domain import (
    AnalyticsBreakdown,
    AnalyticsBucket,
    AnalyticsOverview,
    AnalyticsPayment,
    ClientAnalytics,
    TopClient,
    TopProduct,
)
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import (
    InvalidTokenError,
    JwtTokenService,
)
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.domain import RevenueSummary, SessionCharge
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.domain import (
    CashApproval,
    CashMovement,
    CashMovementDirection,
    CashShift,
    CashShiftStatus,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import (
    BillingMode,
    DiscountRule,
    Product,
    Tariff,
    TariffLifecycle,
)
from gameclub_backend.modules.clients.application.guests import GuestService
from gameclub_backend.modules.clients.application.portal import (
    ClientPortalService,
    ClientPortalSnapshot,
)
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.domain import BalanceOperation, Client, Guest
from gameclub_backend.modules.offline.application.service import OfflineReplayService
from gameclub_backend.modules.offline.domain import (
    OfflineBatch,
    OfflineOperationKind,
    OfflineOperationResult,
)
from gameclub_backend.modules.offline.domain import (
    OfflineOperation as DomainOfflineOperation,
)
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.domain import (
    EntryDecision,
    Reservation,
    ReservationStatus,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.transfer import SessionTransferService
from gameclub_backend.modules.sessions.domain import (
    Session,
    SessionSnapshot,
    SessionStatus,
    SessionTransferOffer,
)
from gameclub_backend.modules.workstations.application.commands import (
    WorkstationCommandService,
)
from gameclub_backend.modules.workstations.application.groups import WorkstationGroupService
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import (
    LockdownDeploymentMode,
    LockdownPolicy,
    Workstation,
    WorkstationGroup,
    WorkstationStatus,
)
from gameclub_backend.modules.workstations.domain_commands import (
    WorkstationCommand,
    WorkstationCommandStatus,
)


async def require_principal(
    context: grpc.aio.ServicerContext,
    token_service: JwtTokenService | None,
) -> Principal:
    if token_service is None:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication is not configured")
    metadata = dict(context.invocation_metadata())
    authorization = metadata.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Bearer token is required")
    try:
        principal = token_service.validate_access_token(token)
    except InvalidTokenError:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid bearer token")
    return principal


async def require_operator(
    context: grpc.aio.ServicerContext,
    token_service: JwtTokenService | None,
    permission: str,
) -> Principal:
    principal = await require_principal(context, token_service)
    if not principal.can(permission):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Permission denied")
    return principal


async def require_session_actor(
    context: grpc.aio.ServicerContext,
    token_service: JwtTokenService | None,
    device_id: str,
) -> Principal:
    principal = await require_principal(context, token_service)
    if principal.can("sessions.manage"):
        return principal
    if (
        principal.subject_type is SubjectType.DEVICE
        and principal.subject_id == device_id
        and principal.can("workstations.connect")
    ):
        return principal
    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Session identity is not permitted")


async def require_device(
    context: grpc.aio.ServicerContext,
    token_service: JwtTokenService | None,
    device_id: str,
) -> Principal:
    principal = await require_principal(context, token_service)
    if (
        principal.subject_type is not SubjectType.DEVICE
        or principal.subject_id != device_id
        or not principal.can("workstations.connect")
    ):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Device identity is not permitted")
    return principal


async def require_client_portal(
    context: grpc.aio.ServicerContext,
    token_service: JwtTokenService | None,
    client_id: str,
    device_id: str,
) -> Principal:
    principal = await require_principal(context, token_service)
    if (
        principal.subject_type is not SubjectType.CLIENT
        or principal.subject_id != client_id
        or principal.device_id != device_id
        or not principal.can("client.portal")
    ):
        await context.abort(
            grpc.StatusCode.PERMISSION_DENIED,
            "Client portal identity is not permitted",
        )
    return principal


async def require_workstation_actor(
    context: grpc.aio.ServicerContext,
    token_service: JwtTokenService | None,
    device_id: str,
) -> Principal:
    principal = await require_principal(context, token_service)
    is_matching_device = (
        principal.subject_type is SubjectType.DEVICE
        and principal.subject_id == device_id
        and principal.can("workstations.connect")
    )
    if not is_matching_device and not principal.can("workstations.manage"):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Device identity is not permitted")
    return principal


def to_timestamp(value: datetime.datetime | None) -> timestamp_pb2.Timestamp | None:
    if value is None:
        return None
    timestamp = timestamp_pb2.Timestamp()
    timestamp.FromDatetime(value)
    return timestamp


def from_timestamp(value: timestamp_pb2.Timestamp, field_name: str) -> datetime.datetime:
    return value.ToDatetime(tzinfo=datetime.UTC)


def required_timestamp(message: typing.Any, field_name: str) -> datetime.datetime:
    if not message.HasField(field_name):
        raise ValueError(f"{field_name} is required")
    return from_timestamp(getattr(message, field_name), field_name)


def parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid UUID") from error


def to_analytics_bucket_proto(item: AnalyticsBucket) -> analytics_pb2.AnalyticsBucket:
    return analytics_pb2.AnalyticsBucket(
        key=item.key,
        label=item.label,
        session_revenue_cents=item.session_revenue_cents,
        product_revenue_cents=item.product_revenue_cents,
        total_revenue_cents=item.total_revenue_cents,
        session_count=item.session_count,
        product_sale_count=item.product_sale_count,
        product_units=item.product_units,
        played_minutes=item.played_minutes,
        guest_session_count=item.guest_session_count,
    )


def to_analytics_breakdown_proto(item: AnalyticsBreakdown) -> analytics_pb2.AnalyticsBreakdown:
    return analytics_pb2.AnalyticsBreakdown(
        key=item.key,
        label=item.label,
        session_revenue_cents=item.session_revenue_cents,
        product_revenue_cents=item.product_revenue_cents,
        revenue_cents=item.revenue_cents,
        product_cost_cents=item.product_cost_cents,
        gross_profit_cents=item.gross_profit_cents,
        session_count=item.session_count,
        product_sale_count=item.product_sale_count,
        product_units=item.product_units,
        played_minutes=item.played_minutes,
        share_bps=item.share_bps,
        discount_cents=item.discount_cents,
    )


def to_analytics_payment_proto(item: AnalyticsPayment) -> analytics_pb2.AnalyticsPayment:
    return analytics_pb2.AnalyticsPayment(
        key=item.key,
        label=item.label,
        revenue_cents=item.revenue_cents,
        operation_count=item.operation_count,
        share_bps=item.share_bps,
    )


def to_analytics_top_product_proto(item: TopProduct) -> analytics_pb2.AnalyticsTopProduct:
    return analytics_pb2.AnalyticsTopProduct(
        product_id=str(item.product_id),
        product_name=item.product_name,
        units=item.units,
        revenue_cents=item.revenue_cents,
        gross_profit_cents=item.gross_profit_cents,
    )


def to_analytics_top_client_proto(item: TopClient) -> analytics_pb2.AnalyticsTopClient:
    return analytics_pb2.AnalyticsTopClient(
        client_id=str(item.client_id),
        nickname=item.nickname,
        played_minutes=item.played_minutes,
        session_spend_cents=item.session_spend_cents,
        product_spend_cents=item.product_spend_cents,
        product_units=item.product_units,
        session_count=item.session_count,
    )


def to_analytics_overview_proto(item: AnalyticsOverview) -> analytics_pb2.AnalyticsOverview:
    response = analytics_pb2.AnalyticsOverview(
        session_revenue_cents=item.session_revenue_cents,
        product_revenue_cents=item.product_revenue_cents,
        total_revenue_cents=item.total_revenue_cents,
        session_count=item.session_count,
        product_sale_count=item.product_sale_count,
        product_units=item.product_units,
        played_minutes=item.played_minutes,
        guest_session_count=item.guest_session_count,
        client_count=item.client_count,
        product_cost_cents=item.product_cost_cents,
        gross_profit_cents=item.gross_profit_cents,
        discount_cents=item.discount_cents,
        active_client_count=item.active_client_count,
        new_client_count=item.new_client_count,
        returning_client_count=item.returning_client_count,
        unique_visitor_count=item.unique_visitor_count,
        workstation_count=item.workstation_count,
        occupancy_percent=item.occupancy_percent,
        peak_usage_hour=item.peak_usage_hour or "",
        top_products=[to_analytics_top_product_proto(value) for value in item.top_products],
        top_clients=[to_analytics_top_client_proto(value) for value in item.top_clients],
        daily_activity=[to_analytics_bucket_proto(value) for value in item.daily_activity],
        hourly_activity=[to_analytics_bucket_proto(value) for value in item.hourly_activity],
        zones=[to_analytics_breakdown_proto(value) for value in item.zones],
        workstations=[to_analytics_breakdown_proto(value) for value in item.workstations],
        tariffs=[to_analytics_breakdown_proto(value) for value in item.tariffs],
        payment_methods=[to_analytics_payment_proto(value) for value in item.payment_methods],
        product_categories=[
            to_analytics_breakdown_proto(value) for value in item.product_categories
        ],
    )
    response.start_at.CopyFrom(to_timestamp(item.start_at))
    response.end_at.CopyFrom(to_timestamp(item.end_at))
    return response


def to_analytics_client_proto(item: ClientAnalytics) -> analytics_pb2.ClientAnalytics:
    response = analytics_pb2.ClientAnalytics(
        client_id=str(item.client_id),
        nickname=item.nickname,
        phone=item.phone or "",
        played_minutes=item.played_minutes,
        session_count=item.session_count,
        session_spend_cents=item.session_spend_cents,
        product_spend_cents=item.product_spend_cents,
        product_units=item.product_units,
        product_cost_cents=item.product_cost_cents,
        favorite_products=[
            to_analytics_top_product_proto(value) for value in item.favorite_products
        ],
        daily_activity=[to_analytics_bucket_proto(value) for value in item.daily_activity],
        payment_methods=[to_analytics_payment_proto(value) for value in item.payment_methods],
    )
    response.start_at.CopyFrom(to_timestamp(item.start_at))
    response.end_at.CopyFrom(to_timestamp(item.end_at))
    for field_name, value in (
        ("first_session_at", item.first_session_at),
        ("last_session_at", item.last_session_at),
        ("last_purchase_at", item.last_purchase_at),
    ):
        timestamp = to_timestamp(value)
        if timestamp is not None:
            getattr(response, field_name).CopyFrom(timestamp)
    return response


class AnalyticsGrpcService(analytics_pb2_grpc.AnalyticsServiceServicer):
    def __init__(
        self,
        service: AnalyticsService,
        token_service: JwtTokenService | None,
    ) -> None:
        self._service = service
        self._token_service = token_service

    async def GetOverview(
        self,
        request: analytics_pb2.GetAnalyticsOverviewRequest,
        context: grpc.aio.ServicerContext,
    ) -> analytics_pb2.AnalyticsOverview:
        await require_operator(context, self._token_service, "analytics.read")
        try:
            result = await self._service.overview(
                required_timestamp(request, "start_at"),
                required_timestamp(request, "end_at"),
                request.limit or 10,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_analytics_overview_proto(result)

    async def GetClient(
        self,
        request: analytics_pb2.GetClientAnalyticsRequest,
        context: grpc.aio.ServicerContext,
    ) -> analytics_pb2.ClientAnalytics:
        await require_operator(context, self._token_service, "analytics.read")
        try:
            result = await self._service.client(
                parse_uuid(request.client_id, "client_id"),
                required_timestamp(request, "start_at"),
                required_timestamp(request, "end_at"),
                request.limit or 10,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_analytics_client_proto(result)


def to_proto(
    workstation: Workstation,
    include_manager_password_verifier: bool = False,
    session_snapshot: SessionSnapshot | None = None,
) -> workstations_pb2.Workstation:
    response = workstations_pb2.Workstation(
        id=str(workstation.id),
        device_id=workstation.device_id,
        name=workstation.name,
        group_id=workstation.group_id or "",
        position=workstation.position or 0,
        status={
            WorkstationStatus.UNKNOWN: workstations_pb2.WORKSTATION_STATUS_UNKNOWN,
            WorkstationStatus.ONLINE: workstations_pb2.WORKSTATION_STATUS_ONLINE,
            WorkstationStatus.STALE: workstations_pb2.WORKSTATION_STATUS_STALE,
            WorkstationStatus.OFFLINE: workstations_pb2.WORKSTATION_STATUS_OFFLINE,
            WorkstationStatus.DISABLED: workstations_pb2.WORKSTATION_STATUS_DISABLED,
        }[workstation.status],
        client_version=workstation.client_version or "",
        disabled_reason=workstation.disabled_reason or "",
        capabilities=list(workstation.capabilities),
        theme=workstation.theme,
        lockdown_policy=to_lockdown_policy_proto(workstation.lockdown_policy),
        active_session_id=str(session_snapshot.session.id) if session_snapshot else "",
        active_session_status=session_snapshot.session.status.value if session_snapshot else "",
    )
    if include_manager_password_verifier and workstation.manager_password_verifier:
        response.manager_password_verifier = workstation.manager_password_verifier
    last_seen_at = to_timestamp(workstation.last_seen_at)
    if last_seen_at is not None:
        response.last_seen_at.CopyFrom(last_seen_at)
    if session_snapshot is not None:
        server_time = to_timestamp(session_snapshot.server_time)
        if server_time is not None:
            response.session_server_time.CopyFrom(server_time)
        response.session_snapshot.CopyFrom(to_session_snapshot_proto(session_snapshot))
    return response


async def abort_application_error(
    context: grpc.aio.ServicerContext,
    error: ApplicationError,
) -> None:
    status_codes = {
        ErrorCode.INVALID_ARGUMENT: grpc.StatusCode.INVALID_ARGUMENT,
        ErrorCode.UNAUTHENTICATED: grpc.StatusCode.UNAUTHENTICATED,
        ErrorCode.PERMISSION_DENIED: grpc.StatusCode.PERMISSION_DENIED,
        ErrorCode.NOT_FOUND: grpc.StatusCode.NOT_FOUND,
        ErrorCode.CONFLICT: grpc.StatusCode.ALREADY_EXISTS,
        ErrorCode.DEPENDENCY_UNAVAILABLE: grpc.StatusCode.UNAVAILABLE,
        ErrorCode.INTERNAL: grpc.StatusCode.INTERNAL,
    }
    await context.abort(status_codes[error.code], error.message)


class WorkstationGrpcService(workstations_pb2_grpc.WorkstationServiceServicer):
    def __init__(
        self,
        service: WorkstationService,
        token_service: JwtTokenService | None,
        command_service: WorkstationCommandService | None = None,
        group_service: WorkstationGroupService | None = None,
        session_service: SessionService | None = None,
    ) -> None:
        self._service = service
        self._token_service = token_service
        self._command_service = command_service
        self._group_service = group_service
        self._session_service = session_service

    async def Register(
        self,
        request: workstations_pb2.RegisterWorkstationRequest,
        context: grpc.aio.ServicerContext,
    ) -> workstations_pb2.Workstation:
        await require_operator(context, self._token_service, "workstations.manage")
        try:
            workstation = await self._service.register(
                device_id=request.device_id,
                name=request.name,
                group_id=request.group_id or None,
                position=request.position or None,
                client_version=request.client_version or None,
                capabilities=request.capabilities,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_proto(workstation)

    async def Heartbeat(
        self,
        request: workstations_pb2.HeartbeatRequest,
        context: grpc.aio.ServicerContext,
    ) -> workstations_pb2.Workstation:
        await require_workstation_actor(context, self._token_service, request.device_id)
        try:
            workstation = await self._service.heartbeat(
                request.device_id,
                request.client_version or None,
                request.capabilities,
            )
            session_snapshot = None
            if self._session_service is not None:
                active_sessions = await self._session_service.list(
                    workstation_id=workstation.id,
                    active_only=True,
                )
                if active_sessions:
                    session_snapshot = await self._session_service.snapshot(active_sessions[0].id)
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_proto(
            workstation,
            include_manager_password_verifier=True,
            session_snapshot=session_snapshot,
        )

    async def List(
        self,
        request: workstations_pb2.ListWorkstationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> workstations_pb2.ListWorkstationsResponse:
        await require_operator(context, self._token_service, "workstations.manage")
        workstations = await self._service.list()
        if request.group_id:
            workstations = [
                workstation
                for workstation in workstations
                if workstation.group_id == request.group_id
            ]
        return workstations_pb2.ListWorkstationsResponse(
            workstations=[to_proto(workstation) for workstation in workstations]
        )

    async def Disable(
        self,
        request: workstations_pb2.DisableWorkstationRequest,
        context: grpc.aio.ServicerContext,
    ) -> workstations_pb2.Workstation:
        await require_operator(context, self._token_service, "workstations.manage")
        try:
            workstation = await self._service.disable(
                parse_uuid(request.workstation_id, "workstation_id"),
                request.reason,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_proto(workstation)

    async def DispatchCommand(
        self,
        request: workstations_pb2.DispatchCommandRequest,
        context: grpc.aio.ServicerContext,
    ) -> workstations_pb2.WorkstationCommand:
        await require_operator(context, self._token_service, "workstations.manage")
        if self._command_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Command delivery is not configured")
        try:
            command = await self._command_service.dispatch(
                workstation_id=parse_uuid(request.workstation_id, "workstation_id"),
                command_type=request.command_type,
                payload_json=request.payload_json,
                idempotency_key=request.idempotency_key,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_command_proto(command)

    async def WatchCommands(
        self,
        request: workstations_pb2.WatchCommandsRequest,
        context: grpc.aio.ServicerContext,
    ) -> typing.AsyncIterator[workstations_pb2.WorkstationCommand]:
        await require_device(context, self._token_service, request.device_id)
        if self._command_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Command delivery is not configured")
        sent_ids: set[uuid.UUID] = set()
        while True:
            try:
                pending = await self._command_service.pending_for_device(request.device_id)
            except ApplicationError as error:
                await abort_application_error(context, error)
            fresh = [command for command in pending if command.id not in sent_ids]
            if fresh:
                for command in fresh:
                    sent_ids.add(command.id)
                    yield to_command_proto(command)
                continue
            await self._command_service.wait_for_commands(request.device_id)

    async def AcknowledgeCommand(
        self,
        request: workstations_pb2.AcknowledgeCommandRequest,
        context: grpc.aio.ServicerContext,
    ) -> workstations_pb2.WorkstationCommand:
        await require_device(context, self._token_service, request.device_id)
        if self._command_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Command delivery is not configured")
        try:
            command = await self._command_service.acknowledge(
                command_id=parse_uuid(request.command_id, "command_id"),
                device_id=request.device_id,
                success=request.success,
                message=request.message,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_command_proto(command)

    async def ListGroups(
        self,
        request: workstations_pb2.ListWorkstationGroupsRequest,
        context: grpc.aio.ServicerContext,
    ) -> workstations_pb2.ListWorkstationGroupsResponse:
        del request
        await require_operator(context, self._token_service, "workstations.manage")
        if self._group_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Group settings are not configured")
        return workstations_pb2.ListWorkstationGroupsResponse(
            groups=[to_group_proto(group) for group in await self._group_service.list()]
        )

    async def UpsertGroup(
        self,
        request: workstations_pb2.UpsertWorkstationGroupRequest,
        context: grpc.aio.ServicerContext,
    ) -> workstations_pb2.WorkstationGroup:
        await require_operator(context, self._token_service, "workstations.manage")
        if self._group_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Group settings are not configured")
        try:
            policy = (
                from_lockdown_policy_proto(request.lockdown_policy)
                if request.HasField("lockdown_policy")
                else None
            )
            group = await self._group_service.save(
                request.id,
                request.name,
                request.theme,
                policy,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_group_proto(group)


def to_command_proto(command: WorkstationCommand) -> workstations_pb2.WorkstationCommand:
    status = {
        WorkstationCommandStatus.QUEUED: workstations_pb2.WORKSTATION_COMMAND_STATUS_QUEUED,
        WorkstationCommandStatus.ACKNOWLEDGED: (
            workstations_pb2.WORKSTATION_COMMAND_STATUS_ACKNOWLEDGED
        ),
        WorkstationCommandStatus.FAILED: workstations_pb2.WORKSTATION_COMMAND_STATUS_FAILED,
        WorkstationCommandStatus.EXPIRED: workstations_pb2.WORKSTATION_COMMAND_STATUS_EXPIRED,
    }[command.status]
    response = workstations_pb2.WorkstationCommand(
        id=str(command.id),
        workstation_id=str(command.workstation_id),
        command_type=command.command_type,
        payload_json=command.payload_json,
        idempotency_key=command.idempotency_key,
        status=status,
        acknowledgement_message=command.acknowledgement_message or "",
    )
    for field_name, value in (
        ("created_at", command.created_at),
        ("expires_at", command.expires_at),
        ("acknowledged_at", command.acknowledged_at),
    ):
        timestamp = to_timestamp(value)
        if timestamp is not None:
            getattr(response, field_name).CopyFrom(timestamp)
    return response


def to_group_proto(group: WorkstationGroup) -> workstations_pb2.WorkstationGroup:
    response = workstations_pb2.WorkstationGroup(
        id=group.id,
        name=group.name,
        theme=group.theme,
        lockdown_policy=to_lockdown_policy_proto(group.lockdown_policy),
    )
    updated_at = to_timestamp(group.updated_at)
    if updated_at is not None:
        response.updated_at.CopyFrom(updated_at)
    return response


def to_lockdown_policy_proto(policy: LockdownPolicy) -> workstations_pb2.WorkstationLockdownPolicy:
    return workstations_pb2.WorkstationLockdownPolicy(
        deployment_mode=policy.deployment_mode.value,
        shell_enabled=policy.shell_enabled,
        user_self_login_enabled=policy.user_self_login_enabled,
        lock_after_session=policy.lock_after_session,
        restart_after_session=policy.restart_after_session,
        hidden_drives=list(policy.hidden_drives),
        block_external_storage=policy.block_external_storage,
        disable_start_menu=policy.disable_start_menu,
        disable_desktop_switching=policy.disable_desktop_switching,
        blocked_window_rules=list(policy.blocked_window_rules),
        allowed_application_ids=list(policy.allowed_application_ids),
        version=policy.version,
    )


def from_lockdown_policy_proto(
    policy: workstations_pb2.WorkstationLockdownPolicy,
) -> LockdownPolicy:
    if policy.ByteSize() == 0:
        return LockdownPolicy()
    return LockdownPolicy(
        deployment_mode=LockdownDeploymentMode(policy.deployment_mode or "app_gate"),
        shell_enabled=policy.shell_enabled,
        user_self_login_enabled=policy.user_self_login_enabled,
        lock_after_session=policy.lock_after_session,
        restart_after_session=policy.restart_after_session,
        hidden_drives=tuple(policy.hidden_drives),
        block_external_storage=policy.block_external_storage,
        disable_start_menu=policy.disable_start_menu,
        disable_desktop_switching=policy.disable_desktop_switching,
        blocked_window_rules=tuple(policy.blocked_window_rules),
        allowed_application_ids=tuple(policy.allowed_application_ids),
        version=policy.version or 1,
    )


def to_client_proto(client: Client) -> clients_pb2.Client:
    response = clients_pb2.Client(
        id=str(client.id),
        nickname=client.nickname,
        phone=client.phone or "",
        discount_category=client.discount_category or "",
        balance_cents=client.balance_cents,
        balance_bonus=client.balance_bonus,
    )
    created_at = to_timestamp(client.created_at)
    updated_at = to_timestamp(client.updated_at)
    blocked_at = to_timestamp(client.blocked_at)
    if created_at is not None:
        response.created_at.CopyFrom(created_at)
    if updated_at is not None:
        response.updated_at.CopyFrom(updated_at)
    if blocked_at is not None:
        response.blocked_at.CopyFrom(blocked_at)
    return response


def to_guest_proto(guest: Guest) -> clients_pb2.Guest:
    response = clients_pb2.Guest(
        id=str(guest.id),
        nickname=guest.nickname,
        phone=guest.phone or "",
        discount_category=guest.discount_category or "",
    )
    for field_name, value in (
        ("created_at", guest.created_at),
        ("updated_at", guest.updated_at),
    ):
        timestamp = to_timestamp(value)
        if timestamp is not None:
            getattr(response, field_name).CopyFrom(timestamp)
    return response


def to_balance_operation_proto(
    operation: BalanceOperation,
) -> clients_pb2.BalanceOperation:
    response = clients_pb2.BalanceOperation(
        id=str(operation.id),
        client_id=str(operation.client_id),
        operation_type=operation.operation_type.value,
        amount_cents=operation.amount_cents,
        bonus_amount=operation.bonus_amount,
        reason=operation.reason,
        actor_id=operation.actor_id,
        idempotency_key=operation.idempotency_key,
        payment_parts=[
            clients_pb2.PaymentPart(
                method=part.method,
                amount_cents=part.amount_cents,
                reference=part.reference or "",
            )
            for part in operation.payment_parts
        ],
    )
    created_at = to_timestamp(operation.created_at)
    if created_at is not None:
        response.created_at.CopyFrom(created_at)
    return response


def to_portal_snapshot_proto(
    snapshot: ClientPortalSnapshot,
) -> clients_pb2.ClientPortalSnapshot:
    response = clients_pb2.ClientPortalSnapshot(
        client=to_client_proto(snapshot.client),
        balance_operations=[
            clients_pb2.PortalBalanceOperation(
                id=str(operation.id),
                operation_type=operation.operation_type.value,
                amount_cents=operation.amount_cents,
                bonus_amount=operation.bonus_amount,
                reason=operation.reason,
                created_at=to_timestamp(operation.created_at),
                payment_parts=[
                    clients_pb2.PaymentPart(
                        method=part.method,
                        amount_cents=part.amount_cents,
                        reference=part.reference or "",
                    )
                    for part in operation.payment_parts
                ],
            )
            for operation in snapshot.balance_operations
        ],
        sessions=[
            clients_pb2.PortalSession(
                id=str(session.id),
                workstation_id=str(session.workstation_id),
                status=session.status.value,
                started_at=to_timestamp(session.started_at),
                ended_at=to_timestamp(session.ended_at),
                tariff_id=str(session.tariff_id) if session.tariff_id else "",
                tariff_quantity=session.tariff_quantity,
                tariff_name=(
                    snapshot.tariff_names.get(session.tariff_id, "") if session.tariff_id else ""
                ),
            )
            for session in snapshot.sessions
        ],
        charges=[
            clients_pb2.PortalCharge(
                id=str(charge.id),
                session_id=str(charge.session_id),
                tariff_id=str(charge.tariff_id),
                duration_minutes=charge.duration_minutes,
                amount_cents=charge.amount_cents,
                created_at=to_timestamp(charge.created_at),
                tariff_name=snapshot.tariff_names.get(charge.tariff_id, ""),
            )
            for charge in snapshot.charges
        ],
        purchases=[
            clients_pb2.PortalPurchase(
                id=str(purchase.id),
                product_name=purchase.product_name,
                quantity=purchase.quantity,
                total_price_cents=purchase.total_price_cents,
                payment_method=purchase.payment_method.value,
                created_at=to_timestamp(purchase.created_at),
            )
            for purchase in snapshot.purchases
        ],
        available_time_minutes=snapshot.available_time_minutes,
        entitlements=[
            clients_pb2.PortalEntitlement(
                id=str(item.id),
                tariff_id=str(item.tariff_id),
                zone_id=item.zone_id or "",
                duration_minutes=item.duration_minutes,
                remaining_minutes=item.remaining_minutes,
                price_cents=item.price_cents,
                queue_position=item.queue_position,
                status=item.status.value,
                tariff_name=snapshot.tariff_names.get(item.tariff_id, ""),
                purchased_at=to_timestamp(item.purchased_at),
                activated_at=to_timestamp(item.activated_at),
            )
            for item in snapshot.entitlements
        ],
        tariffs=[
            clients_pb2.PortalTariff(
                id=str(tariff.id),
                name=tariff.name,
                zone_id=tariff.group_id or "",
                duration_minutes=tariff.duration_minutes,
                price_cents=tariff.price_cents,
            )
            for tariff in snapshot.tariffs
        ],
        reservations=[
            clients_pb2.PortalReservation(
                id=str(reservation.id),
                workstation_ids=[str(item) for item in reservation.workstation_ids],
                start_at=to_timestamp(reservation.start_at),
                end_at=to_timestamp(reservation.end_at),
                status=reservation.status.value,
                tariff_id=str(reservation.tariff_id) if reservation.tariff_id else "",
            )
            for reservation in snapshot.reservations
        ],
    )
    return response


class ClientGrpcService(clients_pb2_grpc.ClientServiceServicer):
    def __init__(
        self,
        service: ClientService,
        token_service: JwtTokenService | None,
        guest_service: GuestService | None = None,
    ) -> None:
        self._service = service
        self._token_service = token_service
        self._guest_service = guest_service

    async def Create(
        self,
        request: clients_pb2.CreateClientRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.Client:
        await require_operator(context, self._token_service, "clients.manage")
        try:
            client = await self._service.create(
                nickname=request.nickname,
                phone=request.phone or None,
                discount_category=request.discount_category or None,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_client_proto(client)

    async def Search(
        self,
        request: clients_pb2.SearchClientsRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.SearchClientsResponse:
        await require_operator(context, self._token_service, "clients.manage")
        fields = {
            clients_pb2.SearchClientsRequest.FIELD_NICKNAME: "nickname",
            clients_pb2.SearchClientsRequest.FIELD_PHONE: "phone",
        }
        field = fields.get(request.field, "nickname")
        try:
            clients = await self._service.search(request.query, field)
        except ApplicationError as error:
            await abort_application_error(context, error)
        return clients_pb2.SearchClientsResponse(
            clients=[to_client_proto(client) for client in clients]
        )

    async def Get(
        self,
        request: clients_pb2.GetClientRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.Client:
        await require_operator(context, self._token_service, "clients.manage")
        try:
            client = await self._service.get(parse_uuid(request.client_id, "client_id"))
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_client_proto(client)

    async def TopUp(
        self,
        request: clients_pb2.TopUpRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.TopUpResponse:
        principal = await require_operator(context, self._token_service, "clients.manage")
        try:
            client, operation = await self._service.top_up(
                client_id=parse_uuid(request.client_id, "client_id"),
                amount_cents=request.amount_cents,
                bonus_amount=request.bonus_amount,
                reason=request.reason,
                actor_id=principal.subject_id,
                idempotency_key=request.idempotency_key,
                payment_parts=[
                    {
                        "method": part.method,
                        "amount_cents": part.amount_cents,
                        "reference": part.reference or None,
                    }
                    for part in request.payment_parts
                ],
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return clients_pb2.TopUpResponse(
            client=to_client_proto(client),
            operation_id=str(operation.id),
            idempotency_key=operation.idempotency_key,
        )

    async def ListBalanceOperations(
        self,
        request: clients_pb2.ListBalanceOperationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ListBalanceOperationsResponse:
        await require_operator(context, self._token_service, "clients.manage")
        try:
            operations = await self._service.list_operations(
                parse_uuid(request.client_id, "client_id"),
                request.limit or 50,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return clients_pb2.ListBalanceOperationsResponse(
            operations=[to_balance_operation_proto(operation) for operation in operations]
        )

    async def CreateGuest(
        self,
        request: clients_pb2.CreateGuestRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.Guest:
        await require_operator(context, self._token_service, "clients.manage")
        if self._guest_service is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Guest service is not configured")
        try:
            guest = await self._guest_service.create(
                nickname=request.nickname,
                phone=request.phone or None,
                discount_category=request.discount_category or None,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_guest_proto(guest)

    async def SearchGuests(
        self,
        request: clients_pb2.SearchGuestsRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.SearchGuestsResponse:
        await require_operator(context, self._token_service, "clients.manage")
        if self._guest_service is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Guest service is not configured")
        fields = {
            clients_pb2.SearchGuestsRequest.FIELD_NICKNAME: "nickname",
            clients_pb2.SearchGuestsRequest.FIELD_PHONE: "phone",
        }
        try:
            guests = await self._guest_service.search(
                request.query,
                fields.get(request.field, "nickname"),
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        return clients_pb2.SearchGuestsResponse(guests=[to_guest_proto(guest) for guest in guests])

    async def GetGuest(
        self,
        request: clients_pb2.GetGuestRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.Guest:
        await require_operator(context, self._token_service, "clients.manage")
        if self._guest_service is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Guest service is not configured")
        try:
            guest = await self._guest_service.get(parse_uuid(request.guest_id, "guest_id"))
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_guest_proto(guest)

    async def ListGuests(
        self,
        request: clients_pb2.ListGuestsRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ListGuestsResponse:
        del request
        await require_operator(context, self._token_service, "clients.manage")
        if self._guest_service is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Guest service is not configured")
        guests = await self._guest_service.list_guests()
        return clients_pb2.ListGuestsResponse(guests=[to_guest_proto(guest) for guest in guests])


class ClientPortalGrpcService(clients_pb2_grpc.ClientPortalServiceServicer):
    def __init__(
        self,
        service: ClientPortalService,
        token_service: JwtTokenService | None,
    ) -> None:
        self._service = service
        self._token_service = token_service

    async def Register(
        self,
        request: clients_pb2.RegisterPortalRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ClientPortalSession:
        await require_device(context, self._token_service, request.device_id)
        try:
            client = await self._service.register(request.nickname, request.phone, request.password)
            return await self._issue_session(client, request.device_id)
        except ApplicationError as error:
            await abort_application_error(context, error)

    async def Login(
        self,
        request: clients_pb2.LoginPortalRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ClientPortalSession:
        await require_device(context, self._token_service, request.device_id)
        try:
            client = await self._service.authenticate(request.identifier, request.password)
            return await self._issue_session(client, request.device_id)
        except ApplicationError as error:
            await abort_application_error(context, error)

    async def Get(
        self,
        request: clients_pb2.GetPortalRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ClientPortalSnapshot:
        try:
            principal = await require_principal(context, self._token_service)
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
            )
            snapshot = await self._service.snapshot(
                parse_uuid(principal.subject_id, "client_id"),
                request.limit or 50,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_portal_snapshot_proto(snapshot)

    async def ActivateEntitlement(
        self,
        request: clients_pb2.ActivateEntitlementRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ClientPortalSnapshot:
        try:
            principal = await require_principal(context, self._token_service)
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
            )
            snapshot = await self._service.activate_entitlement(
                parse_uuid(principal.subject_id, "client_id"),
                parse_uuid(request.entitlement_id, "entitlement_id"),
                request.device_id,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_portal_snapshot_proto(snapshot)

    async def PurchaseEntitlement(
        self,
        request: clients_pb2.PurchaseEntitlementRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ClientPortalSnapshot:
        try:
            principal = await require_principal(context, self._token_service)
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
            )
            snapshot = await self._service.purchase_entitlement(
                parse_uuid(principal.subject_id, "client_id"),
                parse_uuid(request.tariff_id, "tariff_id"),
                request.idempotency_key,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_portal_snapshot_proto(snapshot)

    async def _issue_session(
        self,
        client: Client,
        device_id: str,
    ) -> clients_pb2.ClientPortalSession:
        if self._token_service is None:
            raise ApplicationError(
                ErrorCode.UNAUTHENTICATED,
                "Authentication is not configured",
            )
        principal = Principal(
            subject_id=str(client.id),
            subject_type=SubjectType.CLIENT,
            roles=frozenset({"client"}),
            permissions=frozenset({"client.portal"}),
            device_id=device_id,
        )
        access_token, expires_in = self._token_service.issue_access_token(principal)
        snapshot = await self._service.snapshot(client.id)
        return clients_pb2.ClientPortalSession(
            access_token=access_token,
            expires_in=expires_in,
            snapshot=to_portal_snapshot_proto(snapshot),
        )


def to_product_proto(product: Product) -> catalog_pb2.Product:
    return catalog_pb2.Product(
        id=str(product.id),
        name=product.name,
        category=product.category,
        price_cents=product.price_cents,
        active=product.active,
        cost_price_cents=product.cost_price_cents,
        stock_quantity=product.stock_quantity,
    )


def to_tariff_proto(tariff: Tariff) -> catalog_pb2.Tariff:
    lifecycle = {
        TariffLifecycle.DRAFT: catalog_pb2.TARIFF_LIFECYCLE_DRAFT,
        TariffLifecycle.PUBLISHED: catalog_pb2.TARIFF_LIFECYCLE_PUBLISHED,
        TariffLifecycle.ARCHIVED: catalog_pb2.TARIFF_LIFECYCLE_ARCHIVED,
    }[tariff.lifecycle]
    response = catalog_pb2.Tariff(
        id=str(tariff.id),
        name=tariff.name,
        group_id=tariff.group_id or "",
        duration_minutes=tariff.duration_minutes,
        price_cents=tariff.price_cents,
        active=tariff.active,
        tariff_key=tariff.tariff_key,
        version=tariff.version,
        lifecycle=lifecycle,
        billing_mode={
            BillingMode.BLOCK: catalog_pb2.BILLING_MODE_BLOCK,
            BillingMode.PER_MINUTE: catalog_pb2.BILLING_MODE_PER_MINUTE,
        }[tariff.billing_mode],
        price_per_minute_cents=tariff.price_per_minute_cents,
        free_minutes=tariff.free_minutes,
    )
    if tariff.window_start_minute is not None:
        response.window_start_minute = tariff.window_start_minute
    if tariff.window_end_minute is not None:
        response.window_end_minute = tariff.window_end_minute
    if tariff.window_timezone is not None:
        response.window_timezone = tariff.window_timezone
    valid_from = to_timestamp(tariff.valid_from)
    valid_to = to_timestamp(tariff.valid_to)
    if valid_from is not None:
        response.valid_from.CopyFrom(valid_from)
    if valid_to is not None:
        response.valid_to.CopyFrom(valid_to)
    return response


def to_discount_rule_proto(rule: DiscountRule) -> catalog_pb2.DiscountRule:
    response = catalog_pb2.DiscountRule(
        id=str(rule.id),
        category=rule.category,
        percent_bps=rule.percent_bps,
        priority=rule.priority,
        active=rule.active,
    )
    valid_from = to_timestamp(rule.valid_from)
    valid_to = to_timestamp(rule.valid_to)
    if valid_from is not None:
        response.valid_from.CopyFrom(valid_from)
    if valid_to is not None:
        response.valid_to.CopyFrom(valid_to)
    return response


class CatalogGrpcService(catalog_pb2_grpc.CatalogServiceServicer):
    def __init__(
        self,
        service: CatalogService,
        token_service: JwtTokenService | None,
    ) -> None:
        self._service = service
        self._token_service = token_service

    async def CreateProduct(
        self,
        request: catalog_pb2.CreateProductRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.Product:
        await require_operator(context, self._token_service, "catalog.manage")
        try:
            product = await self._service.create_product(
                request.name,
                request.category,
                request.price_cents,
                request.cost_price_cents,
                request.stock_quantity,
                request.active if request.HasField("active") else True,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_product_proto(product)

    async def ListProducts(
        self,
        request: catalog_pb2.ListProductsRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.ListProductsResponse:
        del request
        await require_operator(context, self._token_service, "catalog.manage")
        products = await self._service.list_products()
        return catalog_pb2.ListProductsResponse(
            products=[to_product_proto(product) for product in products]
        )

    async def CreateTariff(
        self,
        request: catalog_pb2.CreateTariffRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.Tariff:
        await require_operator(context, self._token_service, "catalog.manage")
        try:
            valid_from = required_timestamp(request, "valid_from")
            valid_to = (
                from_timestamp(request.valid_to, "valid_to")
                if request.HasField("valid_to")
                else None
            )
            tariff = await self._service.create_tariff(
                name=request.name,
                group_id=request.group_id or None,
                duration_minutes=request.duration_minutes,
                price_cents=request.price_cents,
                valid_from=valid_from,
                valid_to=valid_to,
                tariff_key=request.tariff_key or None,
                lifecycle={
                    catalog_pb2.TARIFF_LIFECYCLE_DRAFT: TariffLifecycle.DRAFT,
                    catalog_pb2.TARIFF_LIFECYCLE_PUBLISHED: TariffLifecycle.PUBLISHED,
                    catalog_pb2.TARIFF_LIFECYCLE_ARCHIVED: TariffLifecycle.ARCHIVED,
                }.get(request.lifecycle, TariffLifecycle.PUBLISHED),
                billing_mode={
                    catalog_pb2.BILLING_MODE_BLOCK: BillingMode.BLOCK,
                    catalog_pb2.BILLING_MODE_PER_MINUTE: BillingMode.PER_MINUTE,
                }.get(request.billing_mode, BillingMode.BLOCK),
                price_per_minute_cents=request.price_per_minute_cents,
                free_minutes=request.free_minutes,
                window_start_minute=(
                    request.window_start_minute if request.HasField("window_start_minute") else None
                ),
                window_end_minute=(
                    request.window_end_minute if request.HasField("window_end_minute") else None
                ),
                window_timezone=request.window_timezone or None,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_tariff_proto(tariff)

    async def ListTariffs(
        self,
        request: catalog_pb2.ListTariffsRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.ListTariffsResponse:
        del request
        await require_operator(context, self._token_service, "catalog.manage")
        tariffs = await self._service.list_tariffs()
        return catalog_pb2.ListTariffsResponse(
            tariffs=[to_tariff_proto(tariff) for tariff in tariffs]
        )

    async def PublishTariff(
        self,
        request: catalog_pb2.PublishTariffRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.Tariff:
        await require_operator(context, self._token_service, "catalog.manage")
        try:
            tariff = await self._service.publish_tariff(parse_uuid(request.tariff_id, "tariff_id"))
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_tariff_proto(tariff)

    async def ArchiveTariff(
        self,
        request: catalog_pb2.ArchiveTariffRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.Tariff:
        await require_operator(context, self._token_service, "catalog.manage")
        try:
            tariff = await self._service.archive_tariff(parse_uuid(request.tariff_id, "tariff_id"))
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_tariff_proto(tariff)

    async def CreateDiscountRule(
        self,
        request: catalog_pb2.CreateDiscountRuleRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.DiscountRule:
        await require_operator(context, self._token_service, "catalog.manage")
        try:
            valid_from = required_timestamp(request, "valid_from")
            valid_to = (
                from_timestamp(request.valid_to, "valid_to")
                if request.HasField("valid_to")
                else None
            )
            rule = await self._service.create_discount_rule(
                category=request.category,
                percent_bps=request.percent_bps,
                priority=request.priority,
                valid_from=valid_from,
                valid_to=valid_to,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_discount_rule_proto(rule)

    async def ListDiscountRules(
        self,
        request: catalog_pb2.ListDiscountRulesRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.ListDiscountRulesResponse:
        del request
        await require_operator(context, self._token_service, "catalog.manage")
        rules = await self._service.list_discount_rules()
        return catalog_pb2.ListDiscountRulesResponse(
            rules=[to_discount_rule_proto(rule) for rule in rules]
        )

    async def GetCatalogSnapshot(
        self,
        request: catalog_pb2.GetCatalogSnapshotRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.CatalogSnapshot:
        del request
        await require_operator(context, self._token_service, "catalog.manage")
        snapshot = await self._service.snapshot()
        return catalog_pb2.CatalogSnapshot(
            tariffs=[to_tariff_proto(tariff) for tariff in snapshot.tariffs],
            discount_rules=[to_discount_rule_proto(rule) for rule in snapshot.discount_rules],
        )

    async def Quote(
        self,
        request: catalog_pb2.QuoteRequest,
        context: grpc.aio.ServicerContext,
    ) -> catalog_pb2.QuoteResponse:
        await require_operator(context, self._token_service, "catalog.manage")
        try:
            moment = required_timestamp(request, "moment")
            quote = await self._service.quote(
                duration_minutes=request.duration_minutes,
                group_id=request.group_id or None,
                moment=moment,
                discount_category=request.discount_category or None,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return catalog_pb2.QuoteResponse(
            tariff_id=str(quote.tariff_id),
            duration_minutes=quote.duration_minutes,
            price_cents=quote.price_cents,
            price_before_discount_cents=quote.price_before_discount_cents,
            discount_amount_cents=quote.discount_amount_cents,
            discount_percent_bps=quote.discount_percent_bps,
            discount_category=quote.discount_category or "",
        )


def to_reservation_proto(reservation: Reservation) -> reservations_pb2.Reservation:
    status = {
        ReservationStatus.CONFIRMED: reservations_pb2.RESERVATION_STATUS_CONFIRMED,
        ReservationStatus.ACTIVE: reservations_pb2.RESERVATION_STATUS_ACTIVE,
        ReservationStatus.COMPLETED: reservations_pb2.RESERVATION_STATUS_COMPLETED,
        ReservationStatus.CANCELLED: reservations_pb2.RESERVATION_STATUS_CANCELLED,
        ReservationStatus.NO_SHOW: reservations_pb2.RESERVATION_STATUS_NO_SHOW,
    }[reservation.status]
    response = reservations_pb2.Reservation(
        id=str(reservation.id),
        workstation_ids=[str(item) for item in reservation.workstation_ids],
        client_id=str(reservation.client_id) if reservation.client_id else "",
        guest_name=reservation.guest_name or "",
        guest_id=str(reservation.guest_id) if reservation.guest_id else "",
        status=status,
        notes=reservation.notes or "",
        tariff_id=str(reservation.tariff_id) if reservation.tariff_id else "",
        created_by=reservation.created_by,
    )
    for field_name, value in (
        ("start_at", reservation.start_at),
        ("end_at", reservation.end_at),
        ("created_at", reservation.created_at),
        ("cancelled_at", reservation.cancelled_at),
    ):
        timestamp = to_timestamp(value)
        if timestamp is not None:
            getattr(response, field_name).CopyFrom(timestamp)
    return response


def to_entry_decision_proto(decision: EntryDecision) -> reservations_pb2.CheckEntryResponse:
    response = reservations_pb2.CheckEntryResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        reservation_id=str(decision.reservation_id) if decision.reservation_id else "",
        assigned_client_id=(
            str(decision.assigned_client_id) if decision.assigned_client_id else ""
        ),
    )
    starts_at = to_timestamp(decision.starts_at)
    ends_at = to_timestamp(decision.ends_at)
    if starts_at is not None:
        response.starts_at.CopyFrom(starts_at)
    if ends_at is not None:
        response.ends_at.CopyFrom(ends_at)
    return response


class ReservationGrpcService(reservations_pb2_grpc.ReservationServiceServicer):
    def __init__(
        self,
        service: ReservationService,
        token_service: JwtTokenService | None,
    ) -> None:
        self._service = service
        self._token_service = token_service

    async def CheckAvailability(
        self,
        request: reservations_pb2.CheckAvailabilityRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.CheckAvailabilityResponse:
        await require_operator(context, self._token_service, "reservations.manage")
        try:
            availability = await self._service.check_availability(
                workstation_ids=[
                    parse_uuid(item, "workstation_id") for item in request.workstation_ids
                ],
                start_at=required_timestamp(request, "start_at"),
                end_at=required_timestamp(request, "end_at"),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return reservations_pb2.CheckAvailabilityResponse(
            available=availability.available,
            conflicting_reservation_ids=[
                str(item) for item in availability.conflicting_reservation_ids
            ],
            reason=availability.reason or "",
        )

    async def CheckEntry(
        self,
        request: reservations_pb2.CheckEntryRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.CheckEntryResponse:
        await require_session_actor(context, self._token_service, request.workstation_id)
        try:
            decision = await self._service.check_entry(
                workstation_id=parse_uuid(request.workstation_id, "workstation_id"),
                client_id=parse_uuid(request.client_id, "client_id") if request.client_id else None,
                guest_id=parse_uuid(request.guest_id, "guest_id") if request.guest_id else None,
                now=from_timestamp(request.at, "at") if request.HasField("at") else None,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_entry_decision_proto(decision)

    async def Create(
        self,
        request: reservations_pb2.CreateReservationRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.Reservation:
        principal = await require_operator(context, self._token_service, "reservations.manage")
        try:
            reservation = await self._service.create(
                workstation_ids=[
                    parse_uuid(item, "workstation_id") for item in request.workstation_ids
                ],
                start_at=required_timestamp(request, "start_at"),
                end_at=required_timestamp(request, "end_at"),
                created_by=principal.subject_id,
                client_id=parse_uuid(request.client_id, "client_id") if request.client_id else None,
                guest_name=request.guest_name or None,
                notes=request.notes or None,
                tariff_id=parse_uuid(request.tariff_id, "tariff_id") if request.tariff_id else None,
                idempotency_key=request.idempotency_key or None,
                guest_id=parse_uuid(request.guest_id, "guest_id") if request.guest_id else None,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_reservation_proto(reservation)

    async def Update(
        self,
        request: reservations_pb2.UpdateReservationRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.Reservation:
        await require_operator(context, self._token_service, "reservations.manage")
        try:
            reservation = await self._service.update(
                reservation_id=parse_uuid(request.reservation_id, "reservation_id"),
                workstation_ids=[
                    parse_uuid(item, "workstation_id") for item in request.workstation_ids
                ],
                start_at=required_timestamp(request, "start_at"),
                end_at=required_timestamp(request, "end_at"),
                client_id=parse_uuid(request.client_id, "client_id") if request.client_id else None,
                guest_name=request.guest_name or None,
                notes=request.notes or None,
                tariff_id=parse_uuid(request.tariff_id, "tariff_id") if request.tariff_id else None,
                guest_id=parse_uuid(request.guest_id, "guest_id") if request.guest_id else None,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_reservation_proto(reservation)

    async def List(
        self,
        request: reservations_pb2.ListReservationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.ListReservationsResponse:
        await require_operator(context, self._token_service, "reservations.manage")
        try:
            reservations = await self._service.list(
                required_timestamp(request, "start_at"),
                required_timestamp(request, "end_at"),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        return reservations_pb2.ListReservationsResponse(
            reservations=[to_reservation_proto(item) for item in reservations]
        )

    async def Cancel(
        self,
        request: reservations_pb2.CancelReservationRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.Reservation:
        await require_operator(context, self._token_service, "reservations.manage")
        try:
            reservation = await self._service.cancel(
                parse_uuid(request.reservation_id, "reservation_id")
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_reservation_proto(reservation)

    async def Get(
        self,
        request: reservations_pb2.GetReservationRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.Reservation:
        await require_operator(context, self._token_service, "reservations.manage")
        try:
            reservation = await self._service.get(
                parse_uuid(request.reservation_id, "reservation_id")
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_reservation_proto(reservation)

    async def Activate(
        self,
        request: reservations_pb2.ActivateReservationRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.Reservation:
        await require_operator(context, self._token_service, "reservations.manage")
        try:
            reservation = await self._service.activate(
                parse_uuid(request.reservation_id, "reservation_id")
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_reservation_proto(reservation)

    async def Complete(
        self,
        request: reservations_pb2.CompleteReservationRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.Reservation:
        await require_operator(context, self._token_service, "reservations.manage")
        try:
            reservation = await self._service.complete(
                parse_uuid(request.reservation_id, "reservation_id")
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_reservation_proto(reservation)

    async def MarkNoShow(
        self,
        request: reservations_pb2.MarkNoShowReservationRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservations_pb2.Reservation:
        await require_operator(context, self._token_service, "reservations.manage")
        try:
            reservation = await self._service.mark_no_show(
                parse_uuid(request.reservation_id, "reservation_id")
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_reservation_proto(reservation)


def to_session_proto(session: Session) -> sessions_pb2.Session:
    response = sessions_pb2.Session(
        id=str(session.id),
        workstation_id=str(session.workstation_id),
        client_id=str(session.client_id) if session.client_id else "",
        guest_name=session.guest_name or "",
        guest_id=str(session.guest_id) if session.guest_id else "",
        status=(
            sessions_pb2.SESSION_STATUS_ACTIVE
            if session.status is SessionStatus.ACTIVE
            else sessions_pb2.SESSION_STATUS_COMPLETED
        ),
        source=session.source,
        created_by=session.created_by,
        reservation_id=str(session.reservation_id) if session.reservation_id else "",
        idempotency_key=session.idempotency_key or "",
        tariff_id=str(session.tariff_id) if session.tariff_id else "",
        tariff_quantity=session.tariff_quantity,
        guest_payment_id=str(session.guest_payment_id) if session.guest_payment_id else "",
        login_grant_minutes=session.login_grant_minutes,
        entitlement_id=str(session.entitlement_id) if session.entitlement_id else "",
    )
    for field_name, value in (
        ("started_at", session.started_at),
        ("ended_at", session.ended_at),
    ):
        timestamp = to_timestamp(value)
        if timestamp is not None:
            getattr(response, field_name).CopyFrom(timestamp)
    return response


def to_package_snapshot_proto(item) -> sessions_pb2.PackageSnapshot:
    return sessions_pb2.PackageSnapshot(
        id=str(item.id),
        tariff_id=str(item.tariff_id),
        zone_id=item.zone_id or "",
        duration_minutes=item.duration_minutes,
        remaining_minutes=item.remaining_minutes,
        queue_position=item.queue_position,
        status=item.status.value,
        window_start_minute=item.window_start_minute or 0,
        window_end_minute=item.window_end_minute or 0,
        window_timezone=item.window_timezone or "",
    )


def to_session_snapshot_proto(snapshot: SessionSnapshot) -> sessions_pb2.SessionSnapshot:
    response = sessions_pb2.SessionSnapshot(
        schema_version=snapshot.schema_version,
        session=to_session_proto(snapshot.session),
        workstation_id=str(snapshot.workstation_id),
        device_id=snapshot.device_id,
        zone_id=snapshot.zone_id or "",
        client_id=str(snapshot.client_id) if snapshot.client_id else "",
        balance_cents=snapshot.balance_cents or 0,
        balance_bonus=snapshot.balance_bonus or 0,
        package_queue=[to_package_snapshot_proto(item) for item in snapshot.entitlements],
        allowed_actions=list(snapshot.allowed_actions),
    )
    server_time = to_timestamp(snapshot.server_time)
    if server_time is not None:
        response.server_time.CopyFrom(server_time)
    if snapshot.active_entitlement is not None:
        response.active_package.CopyFrom(to_package_snapshot_proto(snapshot.active_entitlement))
    if snapshot.meter is not None:
        meter = snapshot.meter
        response.meter.CopyFrom(
            sessions_pb2.SessionMeterSnapshot(
                session_id=str(meter.session_id),
                billed_minutes=meter.billed_minutes,
                billed_cents=meter.billed_cents,
                package_minutes=meter.package_minutes,
                active_entitlement_id=(
                    str(meter.active_entitlement_id) if meter.active_entitlement_id else ""
                ),
                status=meter.status.value,
                updated_at=to_timestamp(meter.updated_at),
            )
        )
    return response


def to_transfer_offer_proto(offer: SessionTransferOffer) -> sessions_pb2.TransferOffer:
    response = sessions_pb2.TransferOffer(
        id=str(offer.id),
        session_id=str(offer.session_id),
        client_id=str(offer.client_id),
        source_workstation_id=str(offer.source_workstation_id),
        target_workstation_id=str(offer.target_workstation_id),
        token=offer.token,
        status=offer.status.value,
        requires_package_burn=offer.requires_package_burn,
        warning=offer.warning or "",
    )
    for field_name, value in (
        ("created_at", offer.created_at),
        ("expires_at", offer.expires_at),
        ("confirmed_at", offer.confirmed_at),
    ):
        timestamp = to_timestamp(value)
        if timestamp is not None:
            getattr(response, field_name).CopyFrom(timestamp)
    return response


def to_offline_result_proto(
    result: OfflineOperationResult,
) -> sessions_pb2.OfflineOperationResult:
    response = sessions_pb2.OfflineOperationResult(
        operation_id=str(result.operation_id),
        sequence=result.sequence,
        status=result.status.value,
        message=result.message,
    )
    applied_at = to_timestamp(result.applied_at)
    if applied_at is not None:
        response.applied_at.CopyFrom(applied_at)
    return response


class SessionGrpcService(sessions_pb2_grpc.SessionServiceServicer):
    def __init__(
        self,
        service: SessionService,
        token_service: JwtTokenService | None,
        transfer_service: SessionTransferService | None = None,
        offline_service: OfflineReplayService | None = None,
    ) -> None:
        self._service = service
        self._token_service = token_service
        self._transfer_service = transfer_service
        self._offline_service = offline_service

    async def Start(
        self,
        request: sessions_pb2.StartSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.Session:
        actor_device_id = request.device_id
        principal = await require_session_actor(
            context,
            self._token_service,
            actor_device_id,
        )
        try:
            session = await self._service.start(
                workstation_id=parse_uuid(request.workstation_id, "workstation_id"),
                created_by=principal.subject_id,
                client_id=parse_uuid(request.client_id, "client_id") if request.client_id else None,
                guest_name=request.guest_name or None,
                source=(
                    "device" if principal.subject_type is SubjectType.DEVICE else request.source
                )
                or "operator",
                reservation_id=(
                    parse_uuid(request.reservation_id, "reservation_id")
                    if request.reservation_id
                    else None
                ),
                idempotency_key=request.idempotency_key or None,
                device_id=actor_device_id or None,
                guest_id=parse_uuid(request.guest_id, "guest_id") if request.guest_id else None,
                tariff_id=parse_uuid(request.tariff_id, "tariff_id") if request.tariff_id else None,
                tariff_quantity=request.tariff_quantity or 1,
                guest_payment_id=(
                    parse_uuid(request.guest_payment_id, "guest_payment_id")
                    if request.guest_payment_id
                    else None
                ),
                entitlement_id=(
                    parse_uuid(request.entitlement_id, "entitlement_id")
                    if request.entitlement_id
                    else None
                ),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_session_proto(session)

    async def Get(
        self,
        request: sessions_pb2.GetSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.Session:
        await require_operator(context, self._token_service, "sessions.manage")
        try:
            session = await self._service.get(parse_uuid(request.session_id, "session_id"))
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_session_proto(session)

    async def GetSnapshot(
        self,
        request: sessions_pb2.GetSessionSnapshotRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.SessionSnapshot:
        principal = await require_session_actor(
            context,
            self._token_service,
            request.device_id,
        )
        try:
            snapshot = await self._service.snapshot(parse_uuid(request.session_id, "session_id"))
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        if principal.subject_type is SubjectType.DEVICE and snapshot.device_id != request.device_id:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Session device does not match")
        return to_session_snapshot_proto(snapshot)

    async def List(
        self,
        request: sessions_pb2.ListSessionsRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.ListSessionsResponse:
        await require_operator(context, self._token_service, "sessions.manage")
        try:
            workstation_id = (
                parse_uuid(request.workstation_id, "workstation_id")
                if request.workstation_id
                else None
            )
            sessions = await self._service.list(workstation_id, request.active_only)
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        return sessions_pb2.ListSessionsResponse(
            sessions=[to_session_proto(item) for item in sessions]
        )

    async def Stop(
        self,
        request: sessions_pb2.StopSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.Session:
        actor_device_id = request.device_id
        principal = await require_session_actor(
            context,
            self._token_service,
            actor_device_id,
        )
        try:
            session = await self._service.stop(
                parse_uuid(request.session_id, "session_id"),
                device_id=actor_device_id if principal.subject_type is SubjectType.DEVICE else None,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_session_proto(session)

    async def CreateTransferOffer(
        self,
        request: sessions_pb2.CreateTransferOfferRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.TransferOffer:
        if self._transfer_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Transfer service is not configured")
        principal = await require_session_actor(
            context,
            self._token_service,
            request.device_id,
        )
        try:
            offer = await self._transfer_service.create_offer(
                parse_uuid(request.session_id, "session_id"),
                parse_uuid(request.target_workstation_id, "target_workstation_id"),
                request.idempotency_key,
                actor_device_id=(
                    request.device_id if principal.subject_type is SubjectType.DEVICE else None
                ),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_transfer_offer_proto(offer)

    async def GetTransferOffer(
        self,
        request: sessions_pb2.GetTransferOfferRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.TransferOffer:
        principal = await require_principal(context, self._token_service)
        if not principal.can("sessions.manage"):
            if principal.subject_type is not SubjectType.DEVICE:
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    "Transfer identity is not permitted",
                )
            if not request.device_id or principal.subject_id != request.device_id:
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    "Transfer identity is not permitted",
                )
        if not request.token and not principal.can("sessions.manage"):
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Transfer token is required")
        try:
            offer = await self._transfer_service.get(parse_uuid(request.offer_id, "offer_id"))
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        if request.token and not secrets.compare_digest(request.token, offer.token):
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Invalid transfer token")
        return to_transfer_offer_proto(offer)

    async def ConfirmTransfer(
        self,
        request: sessions_pb2.ConfirmTransferRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.TransferResult:
        principal = await require_session_actor(
            context,
            self._token_service,
            request.device_id,
        )
        try:
            offer = await self._transfer_service.get(parse_uuid(request.offer_id, "offer_id"))
            confirmed, session = await self._transfer_service.confirm(
                offer.id,
                request.idempotency_key,
                token=request.token or None,
                actor_device_id=(
                    request.device_id if principal.subject_type is SubjectType.DEVICE else None
                ),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return sessions_pb2.TransferResult(
            offer=to_transfer_offer_proto(confirmed),
            session=to_session_proto(session),
        )

    async def ReplayOfflineBatch(
        self,
        request: sessions_pb2.ReplayOfflineBatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> sessions_pb2.ReplayOfflineBatchResponse:
        if self._offline_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Offline service is not configured")
        principal = await require_session_actor(
            context,
            self._token_service,
            request.device_id,
        )
        try:
            session_id = parse_uuid(request.session_id, "session_id")
            operations = []
            for item in request.operations:
                payload = json.loads(item.payload_json)
                if not isinstance(payload, dict):
                    raise ValueError("Offline payload must be a JSON object")
                operations.append(
                    DomainOfflineOperation(
                        id=parse_uuid(item.id, "operation_id"),
                        session_id=session_id,
                        device_id=request.device_id,
                        sequence=item.sequence,
                        kind=OfflineOperationKind(item.kind),
                        payload_json=item.payload_json,
                        snapshot_version=item.snapshot_version,
                        idempotency_key=item.idempotency_key,
                        checksum=item.checksum,
                        created_at=required_timestamp(item, "created_at"),
                    )
                )
            result = await self._offline_service.replay(
                OfflineBatch(
                    protocol_version=request.protocol_version,
                    device_id=request.device_id,
                    session_id=session_id,
                    operations=tuple(operations),
                ),
                actor_device_id=(
                    request.device_id if principal.subject_type is SubjectType.DEVICE else None
                ),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        response = sessions_pb2.ReplayOfflineBatchResponse(
            protocol_version=result.protocol_version,
            session_id=str(result.session_id),
            results=[to_offline_result_proto(item) for item in result.results],
        )
        if result.snapshot is not None:
            response.snapshot.CopyFrom(to_session_snapshot_proto(result.snapshot))
        return response


def to_charge_proto(charge: SessionCharge) -> billing_pb2.SessionCharge:
    response = billing_pb2.SessionCharge(
        id=str(charge.id),
        session_id=str(charge.session_id),
        client_id=str(charge.client_id),
        balance_operation_id=str(charge.balance_operation_id),
        tariff_id=str(charge.tariff_id),
        duration_minutes=charge.duration_minutes,
        amount_cents=charge.amount_cents,
        amount_before_discount_cents=charge.amount_before_discount_cents,
        discount_amount_cents=charge.discount_amount_cents,
        discount_percent_bps=charge.discount_percent_bps,
        discount_category=charge.discount_category or "",
        charged_by=charge.charged_by,
        idempotency_key=charge.idempotency_key,
    )
    timestamp = to_timestamp(charge.created_at)
    if timestamp is not None:
        response.created_at.CopyFrom(timestamp)
    return response


def to_revenue_proto(summary: RevenueSummary) -> billing_pb2.RevenueSummary:
    response = billing_pb2.RevenueSummary(
        amount_cents=summary.amount_cents,
        charge_count=summary.charge_count,
    )
    start_at = to_timestamp(summary.start_at)
    end_at = to_timestamp(summary.end_at)
    if start_at is not None:
        response.start_at.CopyFrom(start_at)
    if end_at is not None:
        response.end_at.CopyFrom(end_at)
    return response


def to_cash_shift_proto(shift: CashShift) -> cash_shifts_pb2.CashShift:
    status = {
        CashShiftStatus.OPEN: cash_shifts_pb2.CASH_SHIFT_STATUS_OPEN,
        CashShiftStatus.CLOSED: cash_shifts_pb2.CASH_SHIFT_STATUS_CLOSED,
    }[shift.status]
    response = cash_shifts_pb2.CashShift(
        id=str(shift.id),
        register_id=shift.register_id,
        opened_by=shift.opened_by,
        opening_balance_cents=shift.opening_balance_cents,
        expected_close_cents=shift.expected_close_cents,
        status=status,
        closed_by=shift.closed_by or "",
        actual_close_cents=shift.actual_close_cents or 0,
        difference_cents=shift.difference_cents or 0,
    )
    opened_at = to_timestamp(shift.opened_at)
    closed_at = to_timestamp(shift.closed_at)
    if opened_at is not None:
        response.opened_at.CopyFrom(opened_at)
    if closed_at is not None:
        response.closed_at.CopyFrom(closed_at)
    return response


def to_cash_movement_proto(movement: CashMovement) -> cash_shifts_pb2.CashMovement:
    direction = {
        CashMovementDirection.CASH_IN: cash_shifts_pb2.CASH_MOVEMENT_DIRECTION_CASH_IN,
        CashMovementDirection.CASH_OUT: cash_shifts_pb2.CASH_MOVEMENT_DIRECTION_CASH_OUT,
        CashMovementDirection.CORRECTION: cash_shifts_pb2.CASH_MOVEMENT_DIRECTION_CORRECTION,
    }[movement.direction]
    response = cash_shifts_pb2.CashMovement(
        id=str(movement.id),
        shift_id=str(movement.shift_id),
        direction=direction,
        amount_cents=movement.amount_cents,
        reason=movement.reason,
        actor_id=movement.actor_id,
        idempotency_key=movement.idempotency_key,
        reference_type=movement.reference_type or "",
        reference_id=movement.reference_id or "",
    )
    created_at = to_timestamp(movement.created_at)
    if created_at is not None:
        response.created_at.CopyFrom(created_at)
    return response


def to_cash_approval_proto(approval: CashApproval) -> cash_shifts_pb2.CashApproval:
    response = cash_shifts_pb2.CashApproval(
        id=str(approval.id),
        shift_id=str(approval.shift_id),
        kind=approval.kind.value,
        target_key=approval.target_key,
        approved_by=approval.approved_by,
        reason=approval.reason,
        idempotency_key=approval.idempotency_key,
    )
    created_at = to_timestamp(approval.created_at)
    if created_at is not None:
        response.created_at.CopyFrom(created_at)
    return response


class BillingGrpcService(billing_pb2_grpc.BillingServiceServicer):
    def __init__(
        self,
        service: BillingService,
        token_service: JwtTokenService | None,
    ) -> None:
        self._service = service
        self._token_service = token_service

    async def ChargeSession(
        self,
        request: billing_pb2.ChargeSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> billing_pb2.SessionCharge:
        principal = await require_operator(context, self._token_service, "billing.manage")
        try:
            charge, _ = await self._service.charge_session(
                session_id=parse_uuid(request.session_id, "session_id"),
                charged_by=principal.subject_id,
                idempotency_key=request.idempotency_key,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_charge_proto(charge)

    async def GetSessionCharge(
        self,
        request: billing_pb2.GetSessionChargeRequest,
        context: grpc.aio.ServicerContext,
    ) -> billing_pb2.SessionCharge:
        await require_operator(context, self._token_service, "billing.manage")
        try:
            charge = await self._service.get_by_session_id(
                parse_uuid(request.session_id, "session_id")
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_charge_proto(charge)

    async def GetRevenue(
        self,
        request: billing_pb2.GetRevenueRequest,
        context: grpc.aio.ServicerContext,
    ) -> billing_pb2.RevenueSummary:
        await require_operator(context, self._token_service, "dashboard.read")
        try:
            summary = await self._service.revenue_between(
                required_timestamp(request, "start_at"),
                required_timestamp(request, "end_at"),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_revenue_proto(summary)


class CashShiftGrpcService(cash_shifts_pb2_grpc.CashShiftServiceServicer):
    def __init__(
        self,
        service: CashShiftService,
        token_service: JwtTokenService | None,
    ) -> None:
        self._service = service
        self._token_service = token_service

    async def Open(
        self,
        request: cash_shifts_pb2.OpenCashShiftRequest,
        context: grpc.aio.ServicerContext,
    ) -> cash_shifts_pb2.CashShift:
        principal = await require_operator(context, self._token_service, "cashier.manage")
        try:
            shift = await self._service.open(
                register_id=request.register_id,
                opening_balance_cents=request.opening_balance_cents,
                opened_by=principal.subject_id,
                idempotency_key=request.idempotency_key,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_cash_shift_proto(shift)

    async def Get(
        self,
        request: cash_shifts_pb2.GetCashShiftRequest,
        context: grpc.aio.ServicerContext,
    ) -> cash_shifts_pb2.CashShift:
        await require_operator(context, self._token_service, "cashier.read")
        try:
            shift = await self._service.get(parse_uuid(request.shift_id, "shift_id"))
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_cash_shift_proto(shift)

    async def List(
        self,
        request: cash_shifts_pb2.ListCashShiftsRequest,
        context: grpc.aio.ServicerContext,
    ) -> cash_shifts_pb2.ListCashShiftsResponse:
        await require_operator(context, self._token_service, "cashier.read")
        shifts = await self._service.list(request.limit or 50)
        return cash_shifts_pb2.ListCashShiftsResponse(
            shifts=[to_cash_shift_proto(shift) for shift in shifts]
        )

    async def ListMovements(
        self,
        request: cash_shifts_pb2.ListCashMovementsRequest,
        context: grpc.aio.ServicerContext,
    ) -> cash_shifts_pb2.ListCashMovementsResponse:
        await require_operator(context, self._token_service, "cashier.read")
        try:
            movements = await self._service.list_movements(
                parse_uuid(request.shift_id, "shift_id"),
                request.limit or 50,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return cash_shifts_pb2.ListCashMovementsResponse(
            movements=[to_cash_movement_proto(movement) for movement in movements]
        )

    async def RecordMovement(
        self,
        request: cash_shifts_pb2.RecordCashMovementRequest,
        context: grpc.aio.ServicerContext,
    ) -> cash_shifts_pb2.CashMovement:
        principal = await require_operator(context, self._token_service, "cashier.manage")
        directions = {
            cash_shifts_pb2.CASH_MOVEMENT_DIRECTION_CASH_IN: CashMovementDirection.CASH_IN.value,
            cash_shifts_pb2.CASH_MOVEMENT_DIRECTION_CASH_OUT: CashMovementDirection.CASH_OUT.value,
            cash_shifts_pb2.CASH_MOVEMENT_DIRECTION_CORRECTION: (
                CashMovementDirection.CORRECTION.value
            ),
        }
        direction = directions.get(request.direction)
        if direction is None:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "direction is required")
        if direction == CashMovementDirection.CORRECTION.value and not principal.can(
            "cashier.correct"
        ):
            await context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Cash corrections require cashier.correct permission",
            )
        try:
            parsed_shift_id = parse_uuid(request.shift_id, "shift_id")
            _, movement = await self._service.record_movement(
                shift_id=parsed_shift_id,
                direction=direction,
                amount_cents=request.amount_cents,
                reason=request.reason,
                actor_id=principal.subject_id,
                idempotency_key=request.idempotency_key,
                reference_type=request.reference_type or None,
                reference_id=request.reference_id or None,
                approval_id=(
                    parse_uuid(request.approval_id, "approval_id") if request.approval_id else None
                ),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_cash_movement_proto(movement)

    async def Close(
        self,
        request: cash_shifts_pb2.CloseCashShiftRequest,
        context: grpc.aio.ServicerContext,
    ) -> cash_shifts_pb2.CashShift:
        principal = await require_operator(context, self._token_service, "cashier.manage")
        try:
            parsed_shift_id = parse_uuid(request.shift_id, "shift_id")
            current = await self._service.get(parsed_shift_id)
            if request.approval_id and not principal.can("cashier.supervise"):
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    "Cash approval requires cashier.supervise permission",
                )
            if current.expected_close_cents != request.actual_close_cents:
                if not principal.can("cashier.supervise") or not request.approval_id:
                    await context.abort(
                        grpc.StatusCode.PERMISSION_DENIED,
                        "Closing a shift with a difference requires supervisor approval",
                    )
            shift = await self._service.close(
                shift_id=parsed_shift_id,
                actual_close_cents=request.actual_close_cents,
                closed_by=principal.subject_id,
                idempotency_key=request.idempotency_key,
                approval_id=(
                    parse_uuid(request.approval_id, "approval_id") if request.approval_id else None
                ),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_cash_shift_proto(shift)

    async def Approve(
        self,
        request: cash_shifts_pb2.CreateCashApprovalRequest,
        context: grpc.aio.ServicerContext,
    ) -> cash_shifts_pb2.CashApproval:
        principal = await require_operator(context, self._token_service, "cashier.supervise")
        try:
            approval = await self._service.approve(
                shift_id=parse_uuid(request.shift_id, "shift_id"),
                kind=request.kind,
                target_key=request.target_key,
                approved_by=principal.subject_id,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_cash_approval_proto(approval)
