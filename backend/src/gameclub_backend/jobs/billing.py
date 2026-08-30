import datetime
import json
import logging

import dramatiq

from gameclub_backend.application.errors import ApplicationError
from gameclub_backend.config import get_settings
from gameclub_backend.infrastructure.broker import configure_broker
from gameclub_backend.infrastructure.resources import create_resources
from gameclub_backend.modules.billing.application.service import BillingService
from gameclub_backend.modules.billing.infrastructure.postgres import (
    PostgresChargeReconciliationRepository,
    PostgresChargeRepository,
    PostgresMeterRepository,
)
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.postgres import PostgresClientRepository
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.infrastructure.postgres import PostgresSessionRepository
from gameclub_backend.modules.workstations.application.commands import WorkstationCommandService
from gameclub_backend.modules.workstations.infrastructure.commands_memory import (
    InMemoryCommandNotifier,
)
from gameclub_backend.modules.workstations.infrastructure.commands_postgres import (
    PostgresWorkstationCommandRepository,
)
from gameclub_backend.modules.workstations.infrastructure.postgres import (
    PostgresWorkstationRepository,
)

logger = logging.getLogger(__name__)
broker = configure_broker(get_settings())


def _parse_sweep_time(value: str | None) -> datetime.datetime:
    if value is None:
        return datetime.datetime.now(datetime.UTC)
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Reconciliation time must include timezone")
    return parsed


def _engine_provider_or_raise(resources):
    engine = resources.engine
    if engine is None:
        raise RuntimeError("PostgreSQL resources are not configured")
    return engine


@dramatiq.actor(queue_name="billing", max_retries=3)
async def reconcile_billing_charges(
    now_iso: str | None = None,
    limit: int = 100,
) -> None:
    """Retry charge records left between the ledger debit and charge save."""
    settings = get_settings()
    if not settings.postgres_dsn:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for billing workers")
    resources = create_resources(settings)
    try:
        engine = _engine_provider_or_raise(resources)

        def engine_provider():
            return engine

        reconciliation = PostgresChargeReconciliationRepository(engine_provider)
        sessions = PostgresSessionRepository(engine_provider)
        workstations = PostgresWorkstationRepository(engine_provider)
        clients = ClientService(PostgresClientRepository(engine_provider))
        catalog = CatalogService(PostgresCatalogRepository(engine_provider))
        billing = BillingService(
            PostgresChargeRepository(engine_provider),
            sessions=sessions,
            workstations=workstations,
            clients=clients,
            catalog=catalog,
            reconciliation=reconciliation,
            meter_repository=PostgresMeterRepository(engine_provider),
        )
        items = await reconciliation.list_due(_parse_sweep_time(now_iso), limit)
        completed = 0
        for item in items:
            try:
                await billing.charge_session(
                    session_id=item.session_id,
                    charged_by=item.charged_by,
                    idempotency_key=item.idempotency_key,
                )
            except ApplicationError as error:
                logger.warning(
                    "billing_reconciliation_failed session_id=%s code=%s message=%s",
                    item.session_id,
                    error.code.value,
                    error.message,
                )
            except Exception:
                logger.exception(
                    "billing_reconciliation_unexpected_failure session_id=%s",
                    item.session_id,
                )
            else:
                completed += 1
        logger.info("billing_reconciliation_completed completed_count=%s", completed)
    finally:
        await resources.close()


@dramatiq.actor(queue_name="billing", max_retries=3)
async def meter_active_sessions() -> None:
    """Charge minute deltas and stop devices whose spendable balance is exhausted."""
    settings = get_settings()
    if not settings.postgres_dsn:
        raise RuntimeError("GAMECLUB_POSTGRES_DSN is required for billing workers")
    resources = create_resources(settings)
    try:
        engine = _engine_provider_or_raise(resources)

        def engine_provider():
            return engine

        session_repository = PostgresSessionRepository(engine_provider)
        workstation_repository = PostgresWorkstationRepository(engine_provider)
        client_repository = PostgresClientRepository(engine_provider)
        clients = ClientService(client_repository)
        catalog = CatalogService(PostgresCatalogRepository(engine_provider))
        sessions = SessionService(
            session_repository,
            workstations=workstation_repository,
            clients=client_repository,
        )
        commands = WorkstationCommandService(
            PostgresWorkstationCommandRepository(engine_provider),
            workstations=workstation_repository,
            notifier=InMemoryCommandNotifier(),
            command_ttl_seconds=settings.workstation_command_ttl_seconds,
        )
        billing = BillingService(
            PostgresChargeRepository(engine_provider),
            sessions=session_repository,
            workstations=workstation_repository,
            clients=clients,
            catalog=catalog,
            meter_repository=PostgresMeterRepository(engine_provider),
        )
        stopped = 0
        for session in await session_repository.list(active_only=True):
            try:
                await billing.meter_session(session.id)
            except ApplicationError as error:
                if error.message != "Insufficient balance":
                    logger.warning(
                        "session_meter_failed session_id=%s code=%s message=%s",
                        session.id,
                        error.code.value,
                        error.message,
                    )
                    continue
                await sessions.stop(session.id)
                payload = json.dumps({"session_id": str(session.id), "reason": "balance_exhausted"})
                for command_type in ("session.stop", "display.lock"):
                    try:
                        await commands.dispatch(
                            session.workstation_id,
                            command_type,
                            payload,
                            f"auto-meter:{session.id}:{command_type}",
                        )
                    except ApplicationError as command_error:
                        logger.warning(
                            "session_meter_command_failed session_id=%s command=%s code=%s",
                            session.id,
                            command_type,
                            command_error.code.value,
                        )
                stopped += 1
        logger.info("session_meter_completed stopped_count=%s", stopped)
    finally:
        await resources.close()
