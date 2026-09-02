import contextlib
import datetime
import logging
import typing
import uuid

from fastapi import FastAPI, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.responses import JSONResponse

from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.application.health import check_readiness
from gameclub_backend.config import Settings, get_settings
from gameclub_backend.infrastructure.audit_memory import InMemoryAuditRepository
from gameclub_backend.infrastructure.audit_postgres import PostgresAuditRepository
from gameclub_backend.infrastructure.database import EngineProvider
from gameclub_backend.infrastructure.resources import InfrastructureResources, create_resources
from gameclub_backend.modules.analytics.application.service import AnalyticsService
from gameclub_backend.modules.analytics.infrastructure.memory import InMemoryAnalyticsRepository
from gameclub_backend.modules.analytics.infrastructure.postgres import PostgresAnalyticsRepository
from gameclub_backend.modules.analytics.presentation.http import (
    create_router as create_analytics_router,
)
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.auth.infrastructure.refresh_memory import (
    InMemoryRefreshTokenRepository,
)
from gameclub_backend.modules.auth.infrastructure.refresh_redis import RedisRefreshTokenRepository
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.infrastructure.memory import (
    InMemoryChargeReconciliationRepository,
    InMemoryChargeRepository,
    InMemoryMeterRepository,
)
from gameclub_backend.modules.billing.infrastructure.postgres import (
    PostgresChargeReconciliationRepository,
    PostgresChargeRepository,
    PostgresMeterRepository,
)
from gameclub_backend.modules.billing.presentation.http import (
    create_router as create_billing_router,
)
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.infrastructure.memory import (
    InMemoryCashApprovalRepository,
    InMemoryCashShiftRepository,
)
from gameclub_backend.modules.cash_shifts.infrastructure.postgres import (
    PostgresCashApprovalRepository,
    PostgresCashShiftRepository,
)
from gameclub_backend.modules.cash_shifts.presentation.http import (
    create_router as create_cash_shifts_router,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.catalog.presentation.http import (
    create_router as create_catalog_router,
)
from gameclub_backend.modules.clients.application.guests import GuestService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.guests_memory import InMemoryGuestRepository
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.clients.infrastructure.postgres import (
    PostgresClientRepository,
    PostgresGuestRepository,
)
from gameclub_backend.modules.clients.presentation.http import (
    create_guest_router,
)
from gameclub_backend.modules.clients.presentation.http import (
    create_router as create_clients_router,
)
from gameclub_backend.modules.direct_payments.application.service import (
    GuestSessionPaymentService,
)
from gameclub_backend.modules.direct_payments.infrastructure.cash import (
    CashShiftGuestPaymentSettlement,
)
from gameclub_backend.modules.direct_payments.infrastructure.memory import (
    InMemoryGuestSessionPaymentRepository,
)
from gameclub_backend.modules.direct_payments.infrastructure.postgres import (
    PostgresGuestSessionPaymentRepository,
)
from gameclub_backend.modules.direct_payments.presentation.http import (
    create_router as create_guest_payment_router,
)
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.infrastructure.memory import (
    InMemoryEntitlementRepository,
)
from gameclub_backend.modules.entitlements.infrastructure.postgres import (
    PostgresEntitlementRepository,
)
from gameclub_backend.modules.entitlements.presentation.http import (
    create_router as create_entitlements_router,
)
from gameclub_backend.modules.offline.application.service import OfflineReplayService
from gameclub_backend.modules.offline.infrastructure.memory import (
    InMemoryOfflineReplayRepository,
)
from gameclub_backend.modules.offline.infrastructure.postgres import (
    PostgresOfflineReplayRepository,
)
from gameclub_backend.modules.offline.presentation.http import (
    create_router as create_offline_router,
)
from gameclub_backend.modules.payment_methods.application.service import PaymentMethodService
from gameclub_backend.modules.payment_methods.infrastructure.memory import (
    InMemoryPaymentMethodRepository,
)
from gameclub_backend.modules.payment_methods.infrastructure.postgres import (
    PostgresPaymentMethodRepository,
)
from gameclub_backend.modules.payment_methods.presentation.http import (
    create_router as create_payment_methods_router,
)
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.infrastructure.memory import (
    InMemoryReservationRepository,
)
from gameclub_backend.modules.reservations.infrastructure.postgres import (
    PostgresReservationRepository,
)
from gameclub_backend.modules.reservations.presentation.http import (
    create_router as create_reservations_router,
)
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.cash import CashShiftSaleSettlement
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
from gameclub_backend.modules.sales.infrastructure.postgres import PostgresProductSaleRepository
from gameclub_backend.modules.sales.presentation.http import create_router as create_sales_router
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.transfer import SessionTransferService
from gameclub_backend.modules.sessions.infrastructure.memory import (
    InMemorySessionRepository,
)
from gameclub_backend.modules.sessions.infrastructure.postgres import PostgresSessionRepository
from gameclub_backend.modules.sessions.infrastructure.transfers_memory import (
    InMemorySessionTransferRepository,
)
from gameclub_backend.modules.sessions.infrastructure.transfers_postgres import (
    PostgresSessionTransferRepository,
)
from gameclub_backend.modules.sessions.presentation.http import (
    create_router as create_sessions_router,
)
from gameclub_backend.modules.sessions.presentation.transfer_http import (
    create_router as create_session_transfer_router,
)
from gameclub_backend.modules.workstations.application.commands import (
    WorkstationCommandService,
)
from gameclub_backend.modules.workstations.application.groups import WorkstationGroupService
from gameclub_backend.modules.workstations.application.service import WorkstationService
from gameclub_backend.modules.workstations.infrastructure.cache_redis import (
    RedisWorkstationSnapshotCache,
)
from gameclub_backend.modules.workstations.infrastructure.commands_memory import (
    InMemoryCommandNotifier,
    InMemoryWorkstationCommandRepository,
)
from gameclub_backend.modules.workstations.infrastructure.commands_postgres import (
    PostgresWorkstationCommandRepository,
)
from gameclub_backend.modules.workstations.infrastructure.groups_memory import (
    InMemoryWorkstationGroupRepository,
)
from gameclub_backend.modules.workstations.infrastructure.groups_postgres import (
    PostgresWorkstationGroupRepository,
)
from gameclub_backend.modules.workstations.infrastructure.memory import (
    InMemoryWorkstationRepository,
)
from gameclub_backend.modules.workstations.infrastructure.postgres import (
    PostgresWorkstationRepository,
)
from gameclub_backend.modules.workstations.presentation.groups import (
    create_router as create_workstation_groups_router,
)
from gameclub_backend.modules.workstations.presentation.http import (
    create_router as create_workstations_router,
)
from gameclub_backend.presentation.http.audit import create_router as create_audit_router
from gameclub_backend.presentation.http.auth import router as auth_router

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or get_settings()

    @contextlib.asynccontextmanager
    async def lifespan(application: FastAPI) -> typing.AsyncIterator[None]:
        application.state.settings = current_settings
        application.state.jwt_service = (
            JwtTokenService(current_settings) if current_settings.jwt_secret else None
        )
        application.state.resources = create_resources(current_settings)
        yield
        resources: InfrastructureResources = application.state.resources
        await resources.close()

    application = FastAPI(
        title="GameClub backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    def engine_provider() -> AsyncEngine | None:
        return application.state.resources.engine

    workstation_repository: object
    workstation_group_repository: object
    client_repository: object
    guest_repository: object
    if current_settings.postgres_dsn:
        postgres_engine_provider: EngineProvider = engine_provider
        workstation_repository = PostgresWorkstationRepository(postgres_engine_provider)
        workstation_group_repository = PostgresWorkstationGroupRepository(postgres_engine_provider)
        client_repository = PostgresClientRepository(postgres_engine_provider)
        guest_repository = PostgresGuestRepository(postgres_engine_provider)
        catalog_repository = PostgresCatalogRepository(postgres_engine_provider)
        reservation_repository = PostgresReservationRepository(postgres_engine_provider)
        command_repository = PostgresWorkstationCommandRepository(postgres_engine_provider)
        session_repository = PostgresSessionRepository(postgres_engine_provider)
        billing_repository = PostgresChargeRepository(postgres_engine_provider)
        billing_reconciliation_repository = PostgresChargeReconciliationRepository(
            postgres_engine_provider
        )
        meter_repository = PostgresMeterRepository(postgres_engine_provider)
        cash_shift_repository = PostgresCashShiftRepository(postgres_engine_provider)
        cash_approval_repository = PostgresCashApprovalRepository(postgres_engine_provider)
        sales_repository = PostgresProductSaleRepository(postgres_engine_provider)
        payment_method_repository = PostgresPaymentMethodRepository(postgres_engine_provider)
        entitlement_repository = PostgresEntitlementRepository(postgres_engine_provider)
        guest_payment_repository = PostgresGuestSessionPaymentRepository(postgres_engine_provider)
        transfer_repository = PostgresSessionTransferRepository(postgres_engine_provider)
        offline_repository = PostgresOfflineReplayRepository(postgres_engine_provider)
    else:
        workstation_repository = InMemoryWorkstationRepository()
        workstation_group_repository = InMemoryWorkstationGroupRepository()
        client_repository = InMemoryClientRepository()
        guest_repository = InMemoryGuestRepository()
        catalog_repository = InMemoryCatalogRepository()
        reservation_repository = InMemoryReservationRepository()
        command_repository = InMemoryWorkstationCommandRepository()
        session_repository = InMemorySessionRepository()
        billing_repository = InMemoryChargeRepository()
        billing_reconciliation_repository = InMemoryChargeReconciliationRepository()
        meter_repository = InMemoryMeterRepository()
        cash_shift_repository = InMemoryCashShiftRepository()
        cash_approval_repository = InMemoryCashApprovalRepository()
        sales_repository = InMemoryProductSaleRepository(catalog_repository)
        payment_method_repository = InMemoryPaymentMethodRepository()
        entitlement_repository = InMemoryEntitlementRepository()
        guest_payment_repository = InMemoryGuestSessionPaymentRepository()
        transfer_repository = InMemorySessionTransferRepository()
        offline_repository = InMemoryOfflineReplayRepository()
    if current_settings.postgres_dsn:
        audit_repository = PostgresAuditRepository(engine_provider)
        analytics_repository = PostgresAnalyticsRepository(engine_provider)
    else:
        audit_repository = InMemoryAuditRepository()
        analytics_repository = InMemoryAnalyticsRepository()
    if current_settings.redis_url:
        workstation_cache = RedisWorkstationSnapshotCache(
            lambda: application.state.resources.redis,
        )
        refresh_tokens = RedisRefreshTokenRepository(
            lambda: application.state.resources.redis,
        )
    else:
        workstation_cache = None
        refresh_tokens = InMemoryRefreshTokenRepository()
    workstations = WorkstationService(
        workstation_repository,
        stale_after_seconds=current_settings.workstation_stale_after_seconds,
        offline_after_seconds=current_settings.workstation_offline_after_seconds,
        groups=workstation_group_repository,
        cache=workstation_cache,
        cache_ttl_seconds=20,
    )
    workstation_groups = WorkstationGroupService(workstation_group_repository)
    clients = ClientService(client_repository)
    guests = GuestService(guest_repository)
    catalog = CatalogService(catalog_repository)
    entitlements = EntitlementService(
        entitlement_repository,
        tariffs=catalog,
        clients=clients,
        active_sessions=session_repository,
        workstations=workstation_repository,
    )
    reservations = ReservationService(
        reservation_repository,
        workstations=workstation_repository,
        clients=client_repository,
        guests=guest_repository,
        grace_period_minutes=current_settings.reservation_grace_period_minutes,
    )
    billing = BillingService(
        billing_repository,
        sessions=session_repository,
        workstations=workstation_repository,
        clients=clients,
        catalog=catalog,
        reconciliation=billing_reconciliation_repository,
        meter_repository=meter_repository,
        entitlements=entitlements,
    )
    cash_shifts = CashShiftService(cash_shift_repository, approvals=cash_approval_repository)
    guest_payments = GuestSessionPaymentService(
        guest_payment_repository,
        tariffs=catalog,
        cash=CashShiftGuestPaymentSettlement(cash_shifts),
        audit=audit_repository,
    )
    sessions = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        reservations=reservations,
        guests=guest_repository,
        guest_payments=guest_payments,
        entitlements=entitlements,
        meters=meter_repository,
    )
    offline = OfflineReplayService(
        offline_repository,
        sessions=sessions,
        session_repository=session_repository,
        workstations=workstation_repository,
        billing=billing,
    )
    sales = ProductSaleService(
        sales_repository,
        products=catalog,
        clients=clients,
        cash=CashShiftSaleSettlement(cash_shifts),
        audit=audit_repository,
    )
    payment_methods = PaymentMethodService(payment_method_repository)
    analytics = AnalyticsService(analytics_repository)
    command_service = WorkstationCommandService(
        command_repository,
        workstations=workstation_repository,
        notifier=InMemoryCommandNotifier(),
        command_ttl_seconds=current_settings.workstation_command_ttl_seconds,
    )
    session_transfers = SessionTransferService(
        transfer_repository,
        sessions=session_repository,
        workstations=workstation_repository,
        reservations=reservations,
        entitlements=entitlements,
        commands=command_service,
    )
    application.state.workstations = workstations
    application.state.workstation_groups = workstation_groups
    application.state.clients = clients
    application.state.guests = guests
    application.state.catalog = catalog
    application.state.entitlements = entitlements
    application.state.offline = offline
    application.state.guest_payments = guest_payments
    application.state.reservations = reservations
    application.state.sessions = sessions
    application.state.billing = billing
    application.state.billing_reconciliation = billing_reconciliation_repository
    application.state.cash_shifts = cash_shifts
    application.state.sales = sales
    application.state.payment_methods = payment_methods
    application.state.analytics = analytics
    application.state.session_transfers = session_transfers
    application.state.audit_repository = audit_repository
    application.state.refresh_tokens = refresh_tokens
    application.include_router(auth_router)
    application.include_router(create_audit_router(audit_repository))
    application.include_router(create_workstations_router(workstations, command_service, sessions))
    application.include_router(create_workstation_groups_router(workstation_groups))
    application.include_router(create_clients_router(clients))
    application.include_router(create_entitlements_router(entitlements))
    application.include_router(create_offline_router(offline))
    application.include_router(create_guest_payment_router(guest_payments))
    application.include_router(create_guest_router(guests))
    application.include_router(create_catalog_router(catalog))
    application.include_router(create_reservations_router(reservations))
    application.include_router(create_sessions_router(sessions))
    application.include_router(create_session_transfer_router(session_transfers))
    application.include_router(create_billing_router(billing))
    application.include_router(create_cash_shifts_router(cash_shifts))
    application.include_router(create_sales_router(sales))
    application.include_router(create_payment_methods_router(payment_methods))
    application.include_router(create_analytics_router(analytics))

    @application.exception_handler(ApplicationError)
    async def application_error_handler(
        request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        status_codes = {
            ErrorCode.INVALID_ARGUMENT: 400,
            ErrorCode.UNAUTHENTICATED: 401,
            ErrorCode.PERMISSION_DENIED: 403,
            ErrorCode.NOT_FOUND: 404,
            ErrorCode.CONFLICT: 409,
            ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
            ErrorCode.INTERNAL: 500,
        }
        response = JSONResponse(
            status_code=status_codes[error.code],
            content={"code": error.code.value, "message": error.message},
        )
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            response.headers["x-request-id"] = request_id
        return response

    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next: typing.Callable) -> typing.Any:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @application.middleware("http")
    async def audit_middleware(request: Request, call_next: typing.Callable) -> typing.Any:
        audited_prefixes = (
            "/api/v1/workstations",
            "/api/v1/workstation-groups",
            "/api/v1/clients",
            "/api/v1/clients/",
            "/api/v1/guest-payments",
            "/api/v1/guests",
            "/api/v1/catalog",
            "/api/v1/reservations",
            "/api/v1/sessions",
            "/api/v1/session-transfers",
            "/api/v1/offline",
            "/api/v1/billing",
            "/api/v1/cash-shifts",
            "/api/v1/sales",
            "/api/v1/payment-methods",
        )
        should_audit = request.method in {"POST", "PUT", "PATCH", "DELETE"} and any(
            request.url.path.startswith(prefix) for prefix in audited_prefixes
        )
        try:
            response = await call_next(request)
        except Exception:
            if should_audit:
                await write_audit_event(request, 500)
            raise
        if should_audit:
            await write_audit_event(request, response.status_code)
        return response

    async def write_audit_event(request: Request, status_code: int) -> None:
        actor_id: str | None = None
        token_service: JwtTokenService | None = getattr(request.app.state, "jwt_service", None)
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if token_service is not None and scheme.lower() == "bearer" and token:
            try:
                actor_id = token_service.validate_access_token(token).subject_id
            except Exception:
                actor_id = None

        event = AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=request.method,
            resource_path=request.url.path[:512],
            outcome="success" if 200 <= status_code < 400 else "failure",
            status_code=status_code,
            request_id=str(getattr(request.state, "request_id", ""))[:128] or None,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        try:
            await request.app.state.audit_repository.record(event)
        except Exception:
            logger.warning(
                "audit_event_write_failed action=%s path=%s status_code=%s",
                event.action,
                event.resource_path,
                event.status_code,
            )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    async def ready(request: Request) -> ReadinessResponse:
        resources: InfrastructureResources = request.app.state.resources
        readiness = await check_readiness(resources.checks)
        return ReadinessResponse(
            status="ready" if readiness.ready else "not_ready",
            checks=readiness.checks,
        )

    return application


app = create_app()
