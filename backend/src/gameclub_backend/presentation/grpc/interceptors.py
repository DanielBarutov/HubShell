import datetime
import logging
import typing
import uuid

import grpc

from gameclub_backend.application.audit import AuditEvent, AuditRepository
from gameclub_backend.modules.auth.infrastructure.jwt import InvalidTokenError, JwtTokenService

logger = logging.getLogger(__name__)

_AUDITED_OPERATIONS = frozenset(
    {
        "Register",
        "Heartbeat",
        "Disable",
        "DispatchCommand",
        "AcknowledgeCommand",
        "Create",
        "TopUp",
        "CreateProduct",
        "CreateTariff",
        "CreateDiscountRule",
        "Update",
        "Cancel",
        "Activate",
        "Complete",
        "MarkNoShow",
        "ChargeSession",
        "Open",
        "RecordMovement",
        "Close",
    }
)


class GrpcAuditInterceptor(grpc.aio.ServerInterceptor):
    def __init__(
        self,
        repository: AuditRepository,
        token_service: JwtTokenService | None,
    ) -> None:
        self._repository = repository
        self._token_service = token_service

    async def intercept_service(
        self,
        continuation: typing.Callable[
            [grpc.HandlerCallDetails], typing.Awaitable[grpc.RpcMethodHandler | None]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        operation = handler_call_details.method.rsplit("/", maxsplit=1)[-1]
        handler = await continuation(handler_call_details)
        if handler is None or operation not in _AUDITED_OPERATIONS:
            return handler
        if handler.unary_unary is None:
            return handler

        async def audited_unary_unary(
            request: typing.Any,
            context: grpc.aio.ServicerContext,
        ) -> typing.Any:
            status_code = grpc.StatusCode.OK
            try:
                return await handler.unary_unary(request, context)
            except Exception:
                status_code = context.code() or grpc.StatusCode.UNKNOWN
                raise
            finally:
                await self._record(
                    method=handler_call_details.method,
                    operation=operation,
                    context=context,
                    status_code=status_code,
                )

        return grpc.unary_unary_rpc_method_handler(
            audited_unary_unary,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )

    async def _record(
        self,
        method: str,
        operation: str,
        context: grpc.aio.ServicerContext,
        status_code: grpc.StatusCode,
    ) -> None:
        metadata = dict(context.invocation_metadata())
        actor_id = self._actor_id(metadata.get("authorization", ""))
        request_id = metadata.get("x-request-id") or metadata.get("request-id")
        numeric_status = int(status_code.value[0])
        event = AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=operation[:64],
            resource_path=method[:512],
            outcome="success" if status_code is grpc.StatusCode.OK else "failure",
            status_code=numeric_status,
            request_id=request_id[:128] if request_id else None,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        try:
            await self._repository.record(event)
        except Exception:
            logger.warning(
                "grpc_audit_event_write_failed action=%s status_code=%s",
                event.action,
                event.status_code,
            )

    def _actor_id(self, authorization: str) -> str | None:
        if self._token_service is None:
            return None
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        try:
            return self._token_service.validate_access_token(token).subject_id
        except InvalidTokenError:
            return None
