from __future__ import annotations

import contextlib
import datetime
import logging
import typing
import uuid

from fastapi import FastAPI, Request
from faststream.kafka import KafkaBroker
from pydantic import BaseModel
from starlette.responses import JSONResponse

from gameclub_backend.application.audit import AuditEvent
from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.application.health import check_readiness
from gameclub_backend.bootstrap import ApplicationServices, build_application_services
from gameclub_backend.config import Settings, get_settings
from gameclub_backend.infrastructure.resources import InfrastructureResources, create_resources
from gameclub_backend.jobs.reports import generate_analytics_report
from gameclub_backend.modules.analytics.presentation.finance_http import (
    create_v2_router as create_analytics_v2_router,
)
from gameclub_backend.modules.analytics.presentation.http import (
    create_router as create_analytics_router,
)
from gameclub_backend.modules.analytics.presentation.read_v2_http import (
    create_v2_read_router as create_analytics_read_v2_router,
)
from gameclub_backend.modules.analytics.presentation.reports_http import (
    create_reports_router,
)
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.auth.infrastructure.refresh_memory import (
    InMemoryRefreshTokenRepository,
)
from gameclub_backend.modules.auth.infrastructure.refresh_redis import RedisRefreshTokenRepository
from gameclub_backend.modules.billing.presentation.http import (
    create_router as create_billing_router,
)
from gameclub_backend.modules.cash_shifts.presentation.http import (
    create_router as create_cash_shifts_router,
)
from gameclub_backend.modules.catalog.presentation.http import (
    create_router as create_catalog_router,
)
from gameclub_backend.modules.clients.presentation.http import (
    create_client_groups_router,
    create_guest_router,
)
from gameclub_backend.modules.clients.presentation.http import (
    create_router as create_clients_router,
)
from gameclub_backend.modules.direct_payments.presentation.http import (
    create_router as create_guest_payment_router,
)
from gameclub_backend.modules.direct_payments.presentation.xbox import (
    create_router as create_xbox_router,
)
from gameclub_backend.modules.entitlements.presentation.http import (
    create_router as create_entitlements_router,
)
from gameclub_backend.modules.eventing_v2.application.outbox import V2ServerOutboxService
from gameclub_backend.modules.eventing_v2.infrastructure.postgres import (
    PostgresV2ServerOutboxRepository,
)
from gameclub_backend.modules.eventing_v2.presentation.client_facts_http import (
    V2ClientFactIngress,
    create_v2_client_facts_router,
)
from gameclub_backend.modules.eventing_v2.presentation.server_events_http import (
    create_v2_server_events_router,
)
from gameclub_backend.modules.notifications.presentation.http import (
    create_router as create_notification_rules_router,
)
from gameclub_backend.modules.offline.presentation.http import (
    create_router as create_offline_router,
)
from gameclub_backend.modules.payment_methods.presentation.http import (
    create_router as create_payment_methods_router,
)
from gameclub_backend.modules.reservations.presentation.http import (
    create_router as create_reservations_router,
)
from gameclub_backend.modules.sales.presentation.http import create_router as create_sales_router
from gameclub_backend.modules.sessions.presentation.http import (
    create_router as create_sessions_router,
)
from gameclub_backend.modules.sessions.presentation.transfer_http import (
    create_router as create_session_transfer_router,
)
from gameclub_backend.modules.workstations.presentation.groups import (
    create_router as create_workstation_groups_router,
)
from gameclub_backend.modules.workstations.presentation.http import (
    create_router as create_workstations_router,
)
from gameclub_backend.modules.workstations.presentation.v2_http import (
    create_router as create_workstation_commands_router,
)
from gameclub_backend.presentation.http.audit import create_router as create_audit_router
from gameclub_backend.presentation.http.auth import router as auth_router

logger = logging.getLogger(__name__)


def _start_pyroscope(settings: Settings) -> typing.Callable[[], None] | None:
    if not settings.pyroscope_server_address:
        return None

    try:
        import pyroscope

        pyroscope.configure(
            application_name=settings.pyroscope_application_name,
            server_address=settings.pyroscope_server_address,
            sample_rate=settings.pyroscope_sample_rate,
            tags={"environment": settings.environment, "service": "backend-http"},
        )
    except Exception:
        logger.exception("Failed to start Pyroscope profiler; continuing without profiles")
        return None

    logger.info(
        "Pyroscope profiler started for %s",
        settings.pyroscope_application_name,
    )
    return pyroscope.shutdown


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or get_settings()
    resources = create_resources(current_settings)
    services: ApplicationServices = build_application_services(current_settings, resources)
    v2_client_fact_ingress = (
        V2ClientFactIngress(
            KafkaBroker(
                current_settings.kafka_bootstrap_servers,
                client_id="gameclub-v2-http-ingress",
            )
        )
        if current_settings.kafka_bootstrap_servers
        else None
    )
    v2_server_events = None
    if resources.engine is not None:
        v2_engine = resources.engine
        v2_server_events = V2ServerOutboxService(
            PostgresV2ServerOutboxRepository(lambda: v2_engine)
        )
    refresh_tokens = (
        RedisRefreshTokenRepository(lambda: resources.redis)
        if resources.redis is not None
        else InMemoryRefreshTokenRepository()
    )

    @contextlib.asynccontextmanager
    async def lifespan(application: FastAPI) -> typing.AsyncIterator[None]:
        stop_pyroscope = _start_pyroscope(current_settings)
        application.state.settings = current_settings
        application.state.jwt_service = (
            JwtTokenService(current_settings) if current_settings.jwt_secret else None
        )
        application.state.resources = resources
        try:
            await services.workstation_groups.restore_per_minute_tariffs()
            await services.xbox.expire()
            yield
        finally:
            if stop_pyroscope is not None:
                try:
                    stop_pyroscope()
                except Exception:
                    logger.exception("Failed to stop Pyroscope profiler cleanly")
            if v2_client_fact_ingress is not None:
                await v2_client_fact_ingress.close()
            await resources.close()

    application = FastAPI(
        title="GameClub backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = current_settings
    application.state.resources = resources
    application.state.jwt_service = (
        JwtTokenService(current_settings) if current_settings.jwt_secret else None
    )
    application.state.workstations = services.workstations
    application.state.workstation_groups = services.workstation_groups
    application.state.clients = services.clients
    application.state.v2_deposit_credits = services.v2_deposit_credits
    application.state.client_groups = services.client_groups
    application.state.notifications = services.notifications
    application.state.guests = services.guests
    application.state.catalog = services.catalog
    application.state.entitlements = services.entitlements
    application.state.offline = services.offline
    application.state.xbox = services.xbox
    application.state.guest_payments = services.guest_payments
    application.state.reservations = services.reservations
    application.state.sessions = services.sessions
    application.state.v2_client_fact_ingress = v2_client_fact_ingress
    application.state.v2_server_events = v2_server_events
    application.state.billing = services.billing
    application.state.billing_reconciliation = services.billing_reconciliation
    application.state.cash_shifts = services.cash_shifts
    application.state.sales = services.sales
    application.state.payment_methods = services.payment_methods
    application.state.analytics = services.analytics
    application.state.finance_analytics = services.finance_analytics
    application.state.analytics_read_v2 = services.analytics_read_v2
    application.state.analytics_projection = services.analytics_projection
    application.state.report_jobs = services.report_jobs
    application.state.session_transfers = services.session_transfers
    application.state.audit_repository = services.audit_repository
    application.state.refresh_tokens = refresh_tokens

    application.include_router(auth_router)
    application.include_router(create_audit_router(services.audit_repository))
    application.include_router(
        create_workstations_router(
            services.workstations,
            services.command_service,
            services.sessions,
            services.xbox.pending_relay_workstations,
        )
    )
    application.include_router(create_workstation_commands_router(services.command_service))
    application.include_router(create_v2_client_facts_router())
    application.include_router(create_v2_server_events_router())
    application.include_router(create_workstation_groups_router(services.workstation_groups))
    application.include_router(create_clients_router(services.clients, services.v2_deposit_credits))
    application.include_router(create_client_groups_router(services.client_groups))
    application.include_router(create_notification_rules_router(services.notifications))
    application.include_router(create_entitlements_router(services.entitlements))
    application.include_router(create_offline_router(services.offline))
    application.include_router(create_xbox_router(services.xbox))
    application.include_router(
        create_guest_payment_router(services.guest_payments, services.v2_guest_access)
    )
    application.include_router(create_guest_router(services.guests))
    application.include_router(create_catalog_router(services.catalog))
    application.include_router(create_reservations_router(services.reservations))
    application.include_router(create_sessions_router(services.sessions))
    application.include_router(create_session_transfer_router(services.session_transfers))
    application.include_router(create_billing_router(services.billing))
    application.include_router(create_cash_shifts_router(services.cash_shifts))
    application.include_router(create_sales_router(services.sales))
    application.include_router(create_payment_methods_router(services.payment_methods))
    application.include_router(create_analytics_router(services.analytics))
    application.include_router(create_analytics_v2_router(services.finance_analytics))
    application.include_router(create_analytics_read_v2_router(services.analytics_read_v2))
    application.include_router(
        create_reports_router(services.report_jobs, generate_analytics_report.send)
    )

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
            "/api/workstations",
            "/api/v1/workstation-groups",
            "/api/v1/clients",
            "/api/v1/clients/",
            "/api/v1/client-groups",
            "/api/v1/notification-rules",
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
