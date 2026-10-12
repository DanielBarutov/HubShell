import datetime
import typing
import uuid

import grpc
from google.protobuf import empty_pb2, timestamp_pb2

from gameclub.v1 import (
    clients_pb2,
    clients_pb2_grpc,
)
from gameclub.v2 import (
    device_control_service_pb2,
    device_control_service_pb2_grpc,
    offline_session_service_pb2,
    offline_session_service_pb2_grpc,
    offline_session_snapshot_pb2,
)
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import (
    InvalidTokenError,
    JwtTokenService,
)
from gameclub_backend.modules.clients.application.portal import (
    ClientPortalService,
    ClientPortalSnapshot,
)
from gameclub_backend.modules.clients.domain import Client
from gameclub_backend.modules.eventing_v2.application.guest_access import V2GuestAccessService
from gameclub_backend.modules.eventing_v2.application.login import V2OfflineLoginService
from gameclub_backend.modules.workstations.application.commands import (
    WorkstationCommandService,
)
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.domain import (
    WorkstationStatus,
)
from gameclub_backend.modules.workstations.domain_commands import (
    WorkstationCommand,
)


async def require_principal(
    context: grpc.aio.ServicerContext,
    token_service: JwtTokenService | None,
) -> Principal:
    if token_service is None:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Authentication is not configured")
        raise AssertionError("context.abort must not return")
    metadata = dict(context.invocation_metadata())
    authorization = metadata.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Bearer token is required")
        raise AssertionError("context.abort must not return")
    assert token_service is not None
    try:
        principal = token_service.validate_access_token(token)
    except InvalidTokenError:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid bearer token")
        raise AssertionError("context.abort must not return") from None
    return principal


async def require_operator(
    context: grpc.aio.ServicerContext,
    token_service: JwtTokenService | None,
    permission: str,
) -> Principal:
    principal = await require_principal(context, token_service)
    if not principal.can(permission):
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Permission denied")
        raise AssertionError("context.abort must not return")
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
    raise AssertionError("context.abort must not return")


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
    *,
    allow_password_reset: bool = False,
) -> Principal:
    principal = await require_principal(context, token_service)
    if (
        principal.subject_type is not SubjectType.CLIENT
        or principal.subject_id != client_id
        or principal.device_id != device_id
        or not principal.can("client.portal")
        or (principal.password_reset_required and not allow_password_reset)
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


def parse_uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid UUID") from error


async def abort_application_error(
    context: grpc.aio.ServicerContext,
    error: ApplicationError,
) -> typing.NoReturn:
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
    raise AssertionError("context.abort must not return")


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
                workstation_name=snapshot.workstation_names.get(session.workstation_id, ""),
                duration_minutes=snapshot.session_duration_minutes.get(session.id, 0),
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
                payment_parts=[
                    clients_pb2.PaymentPart(
                        method=part.method,
                        amount_cents=part.amount_cents,
                        reference=part.reference or "",
                    )
                    for part in purchase.payment_parts
                ],
            )
            for purchase in snapshot.purchases
        ],
        available_time_minutes=snapshot.available_time_minutes,
        payment_methods=[
            clients_pb2.PortalPaymentMethod(key=key, name=name)
            for key, name in sorted(snapshot.payment_method_names.items())
        ],
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
                time_restricted=item.time_restricted,
                sale_window_start_minute=item.sale_window_start_minute or 0,
                sale_window_end_minute=item.sale_window_end_minute or 0,
                usage_window_start_minute=item.usage_window_start_minute or 0,
                usage_window_end_minute=item.usage_window_end_minute or 0,
                window_timezone=item.window_timezone or "",
                audience=item.audience.value,
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
                time_restricted=tariff.time_restricted,
                sale_window_start_minute=tariff.sale_window_start_minute or 0,
                sale_window_end_minute=tariff.sale_window_end_minute or 0,
                usage_window_start_minute=tariff.usage_window_start_minute or 0,
                usage_window_end_minute=tariff.usage_window_end_minute or 0,
                window_timezone=tariff.window_timezone or "",
                audience=tariff.audience.value,
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


def to_v2_portal_snapshot_proto(
    snapshot: ClientPortalSnapshot,
) -> offline_session_service_pb2.OfflinePortalSnapshot:
    response = offline_session_service_pb2.OfflinePortalSnapshot(
        client_id=str(snapshot.client.id),
        nickname=snapshot.client.nickname,
        phone=snapshot.client.phone or "",
        balance_cents=snapshot.client.balance_cents,
        balance_bonus=snapshot.client.balance_bonus,
        available_time_minutes=snapshot.available_time_minutes,
        payment_methods=[
            offline_session_service_pb2.OfflinePaymentMethod(key=key, name=name)
            for key, name in sorted(snapshot.payment_method_names.items())
        ],
    )
    response.balance_operations.extend(
        offline_session_service_pb2.OfflineBalanceOperation(
            id=str(operation.id),
            operation_type=operation.operation_type.value,
            amount_cents=operation.amount_cents,
            bonus_amount=operation.bonus_amount,
            reason=operation.reason,
            created_at=operation.created_at.isoformat(),
            payment_parts=[
                offline_session_service_pb2.OfflinePaymentPart(
                    method=part.method,
                    amount_cents=part.amount_cents,
                    reference=part.reference or "",
                )
                for part in operation.payment_parts
            ],
        )
        for operation in snapshot.balance_operations
    )
    response.sessions.extend(
        offline_session_service_pb2.OfflinePortalSession(
            id=str(session.id),
            workstation_id=str(session.workstation_id),
            status=session.status.value,
            started_at=session.started_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else "",
            tariff_id=str(session.tariff_id) if session.tariff_id else "",
            tariff_name=(
                snapshot.tariff_names.get(session.tariff_id, "") if session.tariff_id else ""
            ),
            tariff_quantity=session.tariff_quantity,
            workstation_name=snapshot.workstation_names.get(session.workstation_id, ""),
            duration_minutes=snapshot.session_duration_minutes.get(session.id, 0),
        )
        for session in snapshot.sessions
    )
    response.charges.extend(
        offline_session_service_pb2.OfflinePortalCharge(
            id=str(charge.id),
            session_id=str(charge.session_id),
            tariff_id=str(charge.tariff_id),
            duration_minutes=charge.duration_minutes,
            amount_cents=charge.amount_cents,
            tariff_name=snapshot.tariff_names.get(charge.tariff_id, ""),
            created_at=charge.created_at.isoformat(),
        )
        for charge in snapshot.charges
    )
    response.purchases.extend(
        offline_session_service_pb2.OfflinePortalPurchase(
            id=str(purchase.id),
            product_name=purchase.product_name,
            quantity=purchase.quantity,
            total_price_cents=purchase.total_price_cents,
            payment_method=purchase.payment_method.value,
            created_at=purchase.created_at.isoformat(),
            payment_parts=[
                offline_session_service_pb2.OfflinePaymentPart(
                    method=part.method,
                    amount_cents=part.amount_cents,
                    reference=part.reference or "",
                )
                for part in purchase.payment_parts
            ],
        )
        for purchase in snapshot.purchases
    )
    response.entitlements.extend(
        offline_session_service_pb2.OfflinePortalEntitlement(
            id=str(item.id),
            tariff_id=str(item.tariff_id),
            zone_id=item.zone_id or "",
            status=item.status.value,
            duration_minutes=item.duration_minutes,
            remaining_minutes=item.remaining_minutes,
            price_cents=item.price_cents,
            queue_position=item.queue_position,
            tariff_name=snapshot.tariff_names.get(item.tariff_id, ""),
            purchased_at=item.purchased_at.isoformat(),
            activated_at=item.activated_at.isoformat() if item.activated_at else "",
            time_restricted=item.time_restricted,
            sale_window_start_minute=item.sale_window_start_minute or 0,
            sale_window_end_minute=item.sale_window_end_minute or 0,
            usage_window_start_minute=item.usage_window_start_minute or 0,
            usage_window_end_minute=item.usage_window_end_minute or 0,
            window_timezone=item.window_timezone or "",
            audience=item.audience.value,
        )
        for item in snapshot.entitlements
    )
    response.tariffs.extend(
        offline_session_service_pb2.OfflinePortalTariff(
            id=str(tariff.id),
            name=tariff.name,
            zone_id=tariff.group_id or "",
            duration_minutes=tariff.duration_minutes,
            price_cents=tariff.price_cents,
            time_restricted=tariff.time_restricted,
            sale_window_start_minute=tariff.sale_window_start_minute or 0,
            sale_window_end_minute=tariff.sale_window_end_minute or 0,
            usage_window_start_minute=tariff.usage_window_start_minute or 0,
            usage_window_end_minute=tariff.usage_window_end_minute or 0,
            window_timezone=tariff.window_timezone or "",
            audience=tariff.audience.value,
        )
        for tariff in snapshot.tariffs
    )
    response.reservations.extend(
        offline_session_service_pb2.OfflinePortalReservation(
            id=str(reservation.id),
            workstation_ids=[str(item) for item in reservation.workstation_ids],
            start_at=reservation.start_at.isoformat(),
            end_at=reservation.end_at.isoformat(),
            status=reservation.status.value,
            tariff_id=str(reservation.tariff_id) if reservation.tariff_id else "",
        )
        for reservation in snapshot.reservations
    )
    return response


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
        raise AssertionError("unreachable after gRPC abort")

    async def Resume(
        self,
        request: clients_pb2.ResumePortalRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ClientPortalSession:
        await require_device(context, self._token_service, request.device_id)
        try:
            snapshot = await self._service.resume_for_device(
                request.device_id,
                request.limit or 50,
            )
            if snapshot is None:
                return clients_pb2.ClientPortalSession(resumed=False)
            return await self._issue_session(
                snapshot.client,
                request.device_id,
                snapshot=snapshot,
                resumed=True,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def ChangePassword(
        self,
        request: clients_pb2.ChangePortalPasswordRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ClientPortalSession:
        try:
            principal = await require_principal(context, self._token_service)
            if not principal.password_reset_required:
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    "Password reset is not pending",
                )
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
                allow_password_reset=True,
            )
            client = await self._service.set_password(
                parse_uuid(principal.subject_id, "client_id"),
                request.new_password,
            )
            return await self._issue_session(client, request.device_id)
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def Refresh(
        self,
        request: clients_pb2.RefreshPortalRequest,
        context: grpc.aio.ServicerContext,
    ) -> clients_pb2.ClientPortalSession:
        try:
            principal = await require_principal(context, self._token_service)
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
            )
            snapshot = await self._service.snapshot_for_device(
                parse_uuid(principal.subject_id, "client_id"),
                request.device_id,
                request.limit or 50,
            )
            return await self._issue_session(
                snapshot.client,
                request.device_id,
                snapshot=snapshot,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

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
            snapshot = await self._service.snapshot_for_device(
                parse_uuid(principal.subject_id, "client_id"),
                request.device_id,
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
                request.device_id,
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
        snapshot: ClientPortalSnapshot | None = None,
        resumed: bool = False,
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
            password_reset_required=client.password_reset_required,
        )
        access_token, expires_in = self._token_service.issue_access_token(principal)
        snapshot = snapshot or await self._service.snapshot_for_device(client.id, device_id)
        return clients_pb2.ClientPortalSession(
            access_token=access_token,
            expires_in=expires_in,
            password_reset_required=client.password_reset_required,
            snapshot=to_portal_snapshot_proto(snapshot),
            resumed=resumed,
        )


class DeviceControlGrpcService(device_control_service_pb2_grpc.DeviceControlServiceServicer):
    """Workstation configuration transport for the local-ledger runtime."""

    def __init__(
        self,
        service: WorkstationService,
        token_service: JwtTokenService | None,
        command_service: WorkstationCommandService | None = None,
    ) -> None:
        self._service = service
        self._token_service = token_service
        self._command_service = command_service

    async def GetHealth(
        self,
        request: device_control_service_pb2.DeviceHealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> device_control_service_pb2.DeviceHealthResponse:
        del request, context
        return device_control_service_pb2.DeviceHealthResponse(
            service="gameclub-backend",
            status="ok",
            version="2.0.0",
        )

    async def Enroll(
        self,
        request: device_control_service_pb2.DeviceEnrollmentRequest,
        context: grpc.aio.ServicerContext,
    ) -> device_control_service_pb2.DeviceEnrollmentResponse:
        if self._token_service is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Authentication is not configured")
        try:
            workstation = await self._service.enroll_by_mac(
                request.mac_addresses,
                request.installation_id,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        if workstation is None:
            return device_control_service_pb2.DeviceEnrollmentResponse(state="pending")
        if workstation.status is WorkstationStatus.DISABLED:
            return device_control_service_pb2.DeviceEnrollmentResponse(
                state="disabled",
                device_id=workstation.device_id,
                workstation_id=str(workstation.id),
                workstation_name=workstation.name,
            )
        assert self._token_service is not None
        access_token, expires_in = self._token_service.issue_access_token(
            Principal(
                subject_id=workstation.device_id,
                subject_type=SubjectType.DEVICE,
                roles=frozenset({"device"}),
                permissions=frozenset({"workstations.connect"}),
            )
        )
        return device_control_service_pb2.DeviceEnrollmentResponse(
            state="approved",
            device_id=workstation.device_id,
            workstation_id=str(workstation.id),
            workstation_name=workstation.name,
            access_token=access_token,
            expires_in=expires_in,
        )

    async def Heartbeat(
        self,
        request: device_control_service_pb2.DeviceHeartbeatRequest,
        context: grpc.aio.ServicerContext,
    ) -> device_control_service_pb2.DeviceHeartbeatResponse:
        await require_device(context, self._token_service, request.device_id)
        try:
            workstation = await self._service.heartbeat(
                request.device_id,
                request.client_version or None,
                request.capabilities,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        policy = workstation.lockdown_policy
        return device_control_service_pb2.DeviceHeartbeatResponse(
            device_id=workstation.device_id,
            workstation_id=str(workstation.id),
            workstation_name=workstation.name,
            group_id=workstation.group_id or "",
            theme=workstation.theme,
            manager_password_verifier=workstation.manager_password_verifier or "",
            lockdown_policy=device_control_service_pb2.WorkstationLockdownPolicy(
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
            ),
        )

    async def WatchCommands(
        self,
        request: device_control_service_pb2.DeviceCommandWatchRequest,
        context: grpc.aio.ServicerContext,
    ) -> typing.AsyncIterator[device_control_service_pb2.DeviceCommand]:
        await require_device(context, self._token_service, request.device_id)
        if self._command_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Command delivery is not configured")
            raise AssertionError("context.abort must not return")
        sent_ids: set[uuid.UUID] = set()
        while True:
            try:
                pending = await self._command_service.pending_v2_for_device(request.device_id)
            except ApplicationError as error:
                await abort_application_error(context, error)
            fresh = [command for command in pending if command.id not in sent_ids]
            if fresh:
                for command in fresh:
                    sent_ids.add(command.id)
                    yield to_v2_device_command_proto(command)
                continue
            await self._command_service.wait_for_commands(request.device_id)

    async def AcknowledgeCommand(
        self,
        request: device_control_service_pb2.DeviceCommandAcknowledgementRequest,
        context: grpc.aio.ServicerContext,
    ) -> device_control_service_pb2.DeviceCommand:
        await require_device(context, self._token_service, request.device_id)
        if self._command_service is None:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Command delivery is not configured")
            raise AssertionError("context.abort must not return")
        try:
            command = await self._command_service.acknowledge_v2(
                command_id=parse_uuid(request.command_id, "command_id"),
                device_id=request.device_id,
                success=request.success,
                message=request.message,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        return to_v2_device_command_proto(command)


def to_v2_device_command_proto(
    command: WorkstationCommand,
) -> device_control_service_pb2.DeviceCommand:
    return device_control_service_pb2.DeviceCommand(
        id=str(command.id),
        command_type=command.command_type,
        payload_json=command.payload_json,
        idempotency_key=command.idempotency_key,
        status=command.status.value,
        acknowledgement_message=command.acknowledgement_message or "",
        expires_at=command.expires_at.isoformat(),
    )


class OfflineSessionGrpcService(offline_session_service_pb2_grpc.OfflineSessionServiceServicer):
    """Transport for the local client portal."""

    def __init__(
        self,
        service: V2OfflineLoginService | None,
        token_service: JwtTokenService | None,
        guest_access: V2GuestAccessService | None = None,
    ) -> None:
        self._service = service
        self._token_service = token_service
        self._guest_access = guest_access

    async def Login(
        self,
        request: offline_session_service_pb2.LoginOfflineSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot:
        await require_device(context, self._token_service, request.device_id)
        if self._service is None:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "V2 offline login is not configured",
            )
            raise AssertionError("context.abort must not return")
        try:
            return await self._service.login(
                device_id=request.device_id,
                identifier=request.identifier,
                password=request.password,
                idempotency_key=request.idempotency_key,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        except ValueError as error:
            message = str(error)
            status = (
                grpc.StatusCode.ALREADY_EXISTS
                if "active V2 lease" in message
                else grpc.StatusCode.INVALID_ARGUMENT
            )
            await context.abort(status, message)
        raise AssertionError("unreachable after gRPC abort")

    async def Register(
        self,
        request: offline_session_service_pb2.RegisterOfflineSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> offline_session_snapshot_pb2.SignedOfflineSessionSnapshot:
        await require_device(context, self._token_service, request.device_id)
        if self._service is None:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "V2 offline login is not configured",
            )
            raise AssertionError("context.abort must not return")
        try:
            return await self._service.register(
                device_id=request.device_id,
                nickname=request.nickname,
                phone=request.phone,
                password=request.password,
                idempotency_key=request.idempotency_key,
            )
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def ResumePortal(
        self,
        request: offline_session_service_pb2.ResumeOfflinePortalRequest,
        context: grpc.aio.ServicerContext,
    ) -> offline_session_service_pb2.ResumeOfflinePortalResponse:
        await require_device(context, self._token_service, request.device_id)
        if self._service is None:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "V2 offline login is not configured",
            )
            raise AssertionError("context.abort must not return")
        try:
            result = await self._service.resume_portal(
                device_id=request.device_id,
                session_id=parse_uuid(request.session_id, "session_id"),
                client_id=parse_uuid(request.client_id, "client_id"),
            )
            return offline_session_service_pb2.ResumeOfflinePortalResponse(
                client_id=str(result.client_id),
                portal_access_token=result.portal_access_token,
                portal_access_expires_in=result.portal_access_expires_in,
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def StopSession(
        self,
        request: offline_session_service_pb2.StopOfflineSessionRequest,
        context: grpc.aio.ServicerContext,
    ) -> empty_pb2.Empty:
        await require_device(context, self._token_service, request.device_id)
        if self._service is None:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "V2 offline login is not configured",
            )
            raise AssertionError("context.abort must not return")
        try:
            await self._service.stop_session(
                device_id=request.device_id,
                session_id=parse_uuid(request.session_id, "session_id"),
                client_id=parse_uuid(request.client_id, "client_id"),
            )
            return empty_pb2.Empty()
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def RedeemGuestAccess(
        self,
        request: offline_session_service_pb2.RedeemGuestAccessRequest,
        context: grpc.aio.ServicerContext,
    ) -> offline_session_snapshot_pb2.SignedGuestSessionAccess:
        await require_device(context, self._token_service, request.device_id)
        if self._guest_access is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "V2 guest access is not configured")
        try:
            return await self._guest_access.redeem(
                request.device_id,
                uuid.UUID(request.session_id) if request.session_id else None,
                tuple(uuid.UUID(value) for value in request.applied_grant_ids),
            )
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def StopGuestAccess(
        self,
        request: offline_session_service_pb2.StopGuestAccessRequest,
        context: grpc.aio.ServicerContext,
    ) -> empty_pb2.Empty:
        await require_device(context, self._token_service, request.device_id)
        if self._guest_access is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "V2 guest access is not configured")
        try:
            await self._guest_access.stop(
                request.device_id,
                parse_uuid(request.session_id, "session_id"),
                parse_uuid(request.payment_id, "payment_id"),
            )
            return empty_pb2.Empty()
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def ChangePassword(
        self,
        request: offline_session_service_pb2.ChangeOfflinePasswordRequest,
        context: grpc.aio.ServicerContext,
    ) -> empty_pb2.Empty:
        if self._service is None:
            await context.abort(
                grpc.StatusCode.UNAVAILABLE,
                "V2 offline login is not configured",
            )
            raise AssertionError("context.abort must not return")
        try:
            principal = await require_principal(context, self._token_service)
            if (
                principal.subject_type is not SubjectType.CLIENT
                or not principal.password_reset_required
            ):
                await context.abort(
                    grpc.StatusCode.PERMISSION_DENIED,
                    "V2 password reset identity is not permitted",
                )
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
                allow_password_reset=True,
            )
            await self._service.change_password(
                client_id=parse_uuid(principal.subject_id, "client_id"),
                device_id=request.device_id,
                new_password=request.new_password,
            )
            return empty_pb2.Empty()
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def GetPortalSnapshot(
        self,
        request: offline_session_service_pb2.GetOfflinePortalSnapshotRequest,
        context: grpc.aio.ServicerContext,
    ) -> offline_session_service_pb2.OfflinePortalSnapshot:
        if self._service is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "V2 offline login is not configured")
        try:
            principal = await require_principal(context, self._token_service)
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
            )
            snapshot = await self._service.get_portal_snapshot(
                client_id=parse_uuid(principal.subject_id, "client_id"),
                device_id=request.device_id,
                limit=request.limit or 50,
            )
            return to_v2_portal_snapshot_proto(snapshot)
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def ActivateEntitlement(
        self,
        request: offline_session_service_pb2.ActivateOfflineEntitlementRequest,
        context: grpc.aio.ServicerContext,
    ) -> offline_session_service_pb2.OfflinePortalSnapshot:
        if self._service is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "V2 offline login is not configured")
        try:
            principal = await require_principal(context, self._token_service)
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
            )
            snapshot = await self._service.activate_entitlement(
                client_id=parse_uuid(principal.subject_id, "client_id"),
                device_id=request.device_id,
                entitlement_id=parse_uuid(request.entitlement_id, "entitlement_id"),
            )
            return to_v2_portal_snapshot_proto(snapshot)
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")

    async def PurchaseEntitlement(
        self,
        request: offline_session_service_pb2.PurchaseOfflineEntitlementRequest,
        context: grpc.aio.ServicerContext,
    ) -> offline_session_service_pb2.OfflinePortalSnapshot:
        if self._service is None:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "V2 offline login is not configured")
        try:
            principal = await require_principal(context, self._token_service)
            await require_client_portal(
                context,
                self._token_service,
                principal.subject_id,
                request.device_id,
            )
            purchase = await self._service.purchase_entitlement(
                client_id=parse_uuid(principal.subject_id, "client_id"),
                device_id=request.device_id,
                tariff_id=parse_uuid(request.tariff_id, "tariff_id"),
                idempotency_key=request.idempotency_key,
            )
            response = to_v2_portal_snapshot_proto(purchase.portal)
            response.purchased_package.CopyFrom(purchase.purchased_package)
            return response
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except ApplicationError as error:
            await abort_application_error(context, error)
        raise AssertionError("unreachable after gRPC abort")
