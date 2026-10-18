from __future__ import annotations

import pathlib

import grpc

from gameclub.v1 import (
    clients_pb2_grpc,
    system_pb2,
    system_pb2_grpc,
)
from gameclub.v2 import device_control_service_pb2_grpc, offline_session_service_pb2_grpc
from gameclub_backend.bootstrap import ApplicationServices, build_application_services
from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.resources import InfrastructureResources
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.presentation.grpc.interceptors import GrpcAuditInterceptor
from gameclub_backend.presentation.grpc.services import (
    ClientPortalGrpcService,
    DeviceControlGrpcService,
    OfflineSessionGrpcService,
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
    if not cert_file and not key_file:
        # В закрытом клубе backend может работать в private LAN без TLS.
        # При выходе за пределы доверенной сети остаётся доступен TLS.
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
    services: ApplicationServices | None = None,
) -> grpc.aio.Server:
    current_resources = resources or InfrastructureResources(checks={})
    current_services = services or build_application_services(settings, current_resources)
    token_service = JwtTokenService(settings) if settings.jwt_secret else None
    server = grpc.aio.server(
        interceptors=[GrpcAuditInterceptor(current_services.audit_repository, token_service)]
    )

    # gRPC служит границей для устройств и нативного клиента. Операторский CRUD
    # остаётся в HTTP BFF; protobuf-сообщения сохраняются для совместимости и
    # при необходимости могут быть опубликованы отдельным защищённым сервером.
    system_pb2_grpc.add_SystemServiceServicer_to_server(SystemService(), server)
    # Для устройств предусмотрены только бизнес-сервисы DeviceControl и OfflineSession.
    # Старые RPC Workstation/Session V1 не регистрируются в поставляемом сервере.
    clients_pb2_grpc.add_ClientPortalServiceServicer_to_server(
        ClientPortalGrpcService(current_services.client_portal, token_service),
        server,
    )
    offline_session_service_pb2_grpc.add_OfflineSessionServiceServicer_to_server(
        OfflineSessionGrpcService(
            current_services.v2_offline_login,
            token_service,
            current_services.v2_guest_access,
        ),
        server,
    )
    device_control_service_pb2_grpc.add_DeviceControlServiceServicer_to_server(
        DeviceControlGrpcService(
            current_services.workstations,
            token_service,
            current_services.command_service,
        ),
        server,
    )

    address = f"{settings.grpc_host}:{settings.grpc_port}"
    credentials = create_grpc_server_credentials(settings)
    if credentials is None:
        server.add_insecure_port(address)
    else:
        server.add_secure_port(address, credentials)
    return server
