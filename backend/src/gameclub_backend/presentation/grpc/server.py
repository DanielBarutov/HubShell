import pathlib

import grpc

from gameclub.v1 import (
    analytics_pb2_grpc,
    billing_pb2_grpc,
    cash_shifts_pb2_grpc,
    catalog_pb2_grpc,
    clients_pb2_grpc,
    reservations_pb2_grpc,
    sessions_pb2_grpc,
    system_pb2,
    system_pb2_grpc,
    workstations_pb2_grpc,
)
from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.audit_memory import InMemoryAuditRepository
from gameclub_backend.infrastructure.audit_postgres import PostgresAuditRepository
from gameclub_backend.infrastructure.resources import InfrastructureResources
from gameclub_backend.modules.analytics.application.service import AnalyticsService
from gameclub_backend.modules.analytics.infrastructure.memory import InMemoryAnalyticsRepository
from gameclub_backend.modules.analytics.infrastructure.postgres import PostgresAnalyticsRepository
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
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
from gameclub_backend.modules.cash_shifts.application.service import CashShiftService
from gameclub_backend.modules.cash_shifts.infrastructure.memory import (
    InMemoryCashApprovalRepository,
    InMemoryCashShiftRepository,
)
from gameclub_backend.modules.cash_shifts.infrastructure.postgres import (
    PostgresCashApprovalRepository,
    PostgresCashShiftRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.clients.application.guests import GuestService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.guests_memory import InMemoryGuestRepository
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.clients.infrastructure.postgres import (
    PostgresClientRepository,
    PostgresGuestRepository,
)
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.infrastructure.memory import (
    InMemoryReservationRepository,
)
from gameclub_backend.modules.reservations.infrastructure.postgres import (
    PostgresReservationRepository,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.sessions.infrastructure.postgres import PostgresSessionRepository
from gameclub_backend.modules.workstations.application.commands import (
    WorkstationCommandService,
)
from gameclub_backend.modules.workstations.application.groups import WorkstationGroupService
from gameclub_backend.modules.workstations.application.service import WorkstationService
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
from gameclub_backend.presentation.grpc.interceptors import GrpcAuditInterceptor
from gameclub_backend.presentation.grpc.services import (
    AnalyticsGrpcService,
    BillingGrpcService,
    CashShiftGrpcService,
    CatalogGrpcService,
    ClientGrpcService,
    ReservationGrpcService,
    SessionGrpcService,
    WorkstationGrpcService,
)


class SystemService(system_pb2_grpc.SystemServiceServicer):
    async def GetHealth(
        self,
        request: system_pb2.HealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> system_pb2.HealthResponse:
        del request, context
        return system_pb2.HealthResponse(
            service="gameclub-backend",
            status="ok",
            version="0.1.0",
        )


def create_grpc_server_credentials(settings: Settings) -> grpc.ServerCredentials | None:
    cert_file = settings.grpc_tls_cert_file
    key_file = settings.grpc_tls_key_file
    environment = settings.environment.strip().lower()
    if not cert_file and not key_file:
        if environment in {"prod", "production"}:
            raise ValueError("gRPC TLS certificate and key are required in production")
        return None
    if not cert_file or not key_file:
        raise ValueError("gRPC TLS certificate and key must be configured together")
    if settings.grpc_tls_require_client_certificate and not settings.grpc_tls_client_ca_file:
        raise ValueError("gRPC client CA is required when mTLS is enabled")

    try:
        certificate_chain = pathlib.Path(cert_file).read_bytes()
        private_key = pathlib.Path(key_file).read_bytes()
        client_ca = (
            pathlib.Path(settings.grpc_tls_client_ca_file).read_bytes()
            if settings.grpc_tls_client_ca_file
            else None
        )
    except OSError as error:
        raise ValueError("Unable to read configured gRPC TLS files") from error

    return grpc.ssl_server_credentials(
        ((private_key, certificate_chain),),
        root_certificates=client_ca,
        require_client_auth=settings.grpc_tls_require_client_certificate,
    )


def create_server(
    settings: Settings,
    resources: InfrastructureResources | None = None,
) -> grpc.aio.Server:
    if resources is None:
        resources = InfrastructureResources(checks={})

    def engine_provider():
        return resources.engine

    if settings.postgres_dsn:
        audit_repository = PostgresAuditRepository(engine_provider)
    else:
        audit_repository = InMemoryAuditRepository()
    token_service = JwtTokenService(settings) if settings.jwt_secret else None
    server = grpc.aio.server(interceptors=[GrpcAuditInterceptor(audit_repository, token_service)])
    system_pb2_grpc.add_SystemServiceServicer_to_server(SystemService(), server)

    if settings.postgres_dsn:
        workstation_repository = PostgresWorkstationRepository(engine_provider)
        workstation_group_repository = PostgresWorkstationGroupRepository(engine_provider)
        command_repository = PostgresWorkstationCommandRepository(engine_provider)
        client_repository = PostgresClientRepository(engine_provider)
        guest_repository = PostgresGuestRepository(engine_provider)
        catalog_repository = PostgresCatalogRepository(engine_provider)
        reservation_repository = PostgresReservationRepository(engine_provider)
        session_repository = PostgresSessionRepository(engine_provider)
        billing_repository = PostgresChargeRepository(engine_provider)
        billing_reconciliation_repository = PostgresChargeReconciliationRepository(engine_provider)
        meter_repository = PostgresMeterRepository(engine_provider)
        cash_shift_repository = PostgresCashShiftRepository(engine_provider)
        cash_approval_repository = PostgresCashApprovalRepository(engine_provider)
        analytics_repository = PostgresAnalyticsRepository(engine_provider)
    else:
        workstation_repository = InMemoryWorkstationRepository()
        workstation_group_repository = InMemoryWorkstationGroupRepository()
        command_repository = InMemoryWorkstationCommandRepository()
        client_repository = InMemoryClientRepository()
        guest_repository = InMemoryGuestRepository()
        catalog_repository = InMemoryCatalogRepository()
        reservation_repository = InMemoryReservationRepository()
        session_repository = InMemorySessionRepository()
        billing_repository = InMemoryChargeRepository()
        billing_reconciliation_repository = InMemoryChargeReconciliationRepository()
        meter_repository = InMemoryMeterRepository()
        cash_shift_repository = InMemoryCashShiftRepository()
        cash_approval_repository = InMemoryCashApprovalRepository()
        analytics_repository = InMemoryAnalyticsRepository()
    workstation_service = WorkstationService(
        workstation_repository,
        stale_after_seconds=settings.workstation_stale_after_seconds,
        offline_after_seconds=settings.workstation_offline_after_seconds,
        groups=workstation_group_repository,
    )
    workstation_group_service = WorkstationGroupService(workstation_group_repository)
    client_service = ClientService(client_repository)
    guest_service = GuestService(guest_repository)
    catalog_service = CatalogService(catalog_repository)
    reservation_service = ReservationService(
        reservation_repository,
        workstations=workstation_repository,
        clients=client_repository,
        guests=guest_repository,
        grace_period_minutes=settings.reservation_grace_period_minutes,
    )
    session_service = SessionService(
        session_repository,
        workstations=workstation_repository,
        clients=client_repository,
        reservations=reservation_service,
        guests=guest_repository,
    )
    billing_service = BillingService(
        billing_repository,
        sessions=session_repository,
        workstations=workstation_repository,
        clients=client_service,
        catalog=catalog_service,
        reconciliation=billing_reconciliation_repository,
        meter_repository=meter_repository,
    )
    cash_shift_service = CashShiftService(
        cash_shift_repository,
        approvals=cash_approval_repository,
    )
    analytics_service = AnalyticsService(analytics_repository)
    command_service = WorkstationCommandService(
        command_repository,
        workstations=workstation_repository,
        notifier=InMemoryCommandNotifier(),
        command_ttl_seconds=settings.workstation_command_ttl_seconds,
    )
    workstations_pb2_grpc.add_WorkstationServiceServicer_to_server(
        WorkstationGrpcService(
            workstation_service,
            token_service,
            command_service,
            workstation_group_service,
        ),
        server,
    )
    clients_pb2_grpc.add_ClientServiceServicer_to_server(
        ClientGrpcService(client_service, token_service, guest_service),
        server,
    )
    catalog_pb2_grpc.add_CatalogServiceServicer_to_server(
        CatalogGrpcService(catalog_service, token_service),
        server,
    )
    reservations_pb2_grpc.add_ReservationServiceServicer_to_server(
        ReservationGrpcService(reservation_service, token_service),
        server,
    )
    sessions_pb2_grpc.add_SessionServiceServicer_to_server(
        SessionGrpcService(session_service, token_service),
        server,
    )
    billing_pb2_grpc.add_BillingServiceServicer_to_server(
        BillingGrpcService(billing_service, token_service),
        server,
    )
    cash_shifts_pb2_grpc.add_CashShiftServiceServicer_to_server(
        CashShiftGrpcService(cash_shift_service, token_service),
        server,
    )
    analytics_pb2_grpc.add_AnalyticsServiceServicer_to_server(
        AnalyticsGrpcService(analytics_service, token_service),
        server,
    )
    address = f"{settings.grpc_host}:{settings.grpc_port}"
    credentials = create_grpc_server_credentials(settings)
    if credentials is None:
        server.add_insecure_port(address)
    else:
        server.add_secure_port(address, credentials)
    return server
