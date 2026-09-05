import grpc
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.audit_memory import InMemoryAuditRepository
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.presentation.grpc.interceptors import GrpcAuditInterceptor
from gameclub_backend.presentation.grpc.server import create_grpc_server_credentials


class FakeContext:
    def __init__(self, metadata: tuple[tuple[str, str], ...], code: grpc.StatusCode) -> None:
        self._metadata = metadata
        self._code = code

    def invocation_metadata(self) -> tuple[tuple[str, str], ...]:
        return self._metadata

    def code(self) -> grpc.StatusCode:
        return self._code


def test_grpc_tls_is_optional_for_private_deployments_and_requires_a_certificate_pair() -> None:
    assert create_grpc_server_credentials(Settings(environment="dev")) is None
    assert create_grpc_server_credentials(Settings(environment="production")) is None

    with pytest.raises(ValueError, match="configured together"):
        create_grpc_server_credentials(Settings(grpc_tls_cert_file="server.crt", environment="dev"))


async def test_grpc_audit_interceptor_records_actor_and_request_id() -> None:
    settings = Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    token, _ = JwtTokenService(settings).issue_access_token(
        Principal(
            subject_id="operator-01",
            subject_type=SubjectType.OPERATOR,
            roles=frozenset({"operator"}),
            permissions=frozenset({"clients.manage"}),
        )
    )
    repository = InMemoryAuditRepository()
    interceptor = GrpcAuditInterceptor(repository, JwtTokenService(settings))

    async def continuation(_details):
        async def behavior(request, _context):
            return request

        return grpc.unary_unary_rpc_method_handler(behavior)

    handler = await interceptor.intercept_service(
        continuation,
        type("Details", (), {"method": "/gameclub.v1.ClientService/AcknowledgeCommand"})(),
    )
    result = await handler.unary_unary(
        "payload-is-not-recorded",
        FakeContext(
            (
                ("authorization", f"Bearer {token}"),
                ("x-request-id", "grpc-request-01"),
            ),
            grpc.StatusCode.OK,
        ),
    )

    assert result == "payload-is-not-recorded"
    assert len(repository.events) == 1
    assert repository.events[0].actor_id == "operator-01"
    assert repository.events[0].action == "AcknowledgeCommand"
    assert repository.events[0].status_code == 0
    assert repository.events[0].request_id == "grpc-request-01"


async def test_grpc_audit_interceptor_records_failed_mutation_without_payload() -> None:
    repository = InMemoryAuditRepository()
    interceptor = GrpcAuditInterceptor(repository, None)

    async def continuation(_details):
        async def behavior(_request, _context):
            raise RuntimeError("handler failure")

        return grpc.unary_unary_rpc_method_handler(behavior)

    handler = await interceptor.intercept_service(
        continuation,
        type("Details", (), {"method": "/gameclub.v1.ClientService/TopUp"})(),
    )
    context = FakeContext((("x-request-id", "grpc-failure-01"),), grpc.StatusCode.INTERNAL)

    try:
        await handler.unary_unary("sensitive payload", context)
    except RuntimeError:
        pass

    assert len(repository.events) == 1
    assert repository.events[0].outcome == "failure"
    assert repository.events[0].status_code == 13
    assert repository.events[0].request_id == "grpc-failure-01"
