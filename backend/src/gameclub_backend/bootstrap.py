from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from gameclub_backend.application.audit import AuditRepository
from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.audit_memory import InMemoryAuditRepository
from gameclub_backend.infrastructure.audit_postgres import PostgresAuditRepository
from gameclub_backend.infrastructure.database import EngineProvider
from gameclub_backend.infrastructure.resources import InfrastructureResources
from gameclub_backend.modules.analytics.application.ports import AnalyticsRepository
from gameclub_backend.modules.analytics.application.service import AnalyticsService
from gameclub_backend.modules.analytics.infrastructure.memory import InMemoryAnalyticsRepository
from gameclub_backend.modules.analytics.infrastructure.postgres import PostgresAnalyticsRepository
from gameclub_backend.modules.billing.application.ports import (
    ChargeReconciliationRepository,
    ChargeRepository,
    MeterRepository,
)
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
from gameclub_backend.modules.cash_shifts.application.ports import (
    CashApprovalRepository,
    CashShiftRepository,
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
from gameclub_backend.modules.catalog.application.ports import CatalogRepository
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.modules.catalog.infrastructure.postgres import PostgresCatalogRepository
from gameclub_backend.modules.client_groups.application.ports import ClientGroupRepository
from gameclub_backend.modules.client_groups.application.service import ClientGroupService
from gameclub_backend.modules.client_groups.infrastructure.memory import (
    InMemoryClientGroupRepository,
)
from gameclub_backend.modules.client_groups.infrastructure.postgres import (
    PostgresClientGroupRepository,
)
from gameclub_backend.modules.clients.application.guests import GuestService
from gameclub_backend.modules.clients.application.portal import ClientPortalService
from gameclub_backend.modules.clients.application.ports import ClientRepository, GuestRepository
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.infrastructure.guests_memory import InMemoryGuestRepository
from gameclub_backend.modules.clients.infrastructure.memory import InMemoryClientRepository
from gameclub_backend.modules.clients.infrastructure.postgres import (
    PostgresClientRepository,
    PostgresGuestRepository,
)
from gameclub_backend.modules.direct_payments.application.ports import GuestSessionPaymentRepository
from gameclub_backend.modules.direct_payments.application.service import GuestSessionPaymentService
from gameclub_backend.modules.direct_payments.infrastructure.cash import (
    CashShiftGuestPaymentSettlement,
)
from gameclub_backend.modules.direct_payments.infrastructure.memory import (
    InMemoryGuestSessionPaymentRepository,
)
from gameclub_backend.modules.direct_payments.infrastructure.postgres import (
    PostgresGuestSessionPaymentRepository,
)
from gameclub_backend.modules.entitlements.application.ports import EntitlementRepository
from gameclub_backend.modules.entitlements.application.service import EntitlementService
from gameclub_backend.modules.entitlements.infrastructure.cash import CashShiftEntitlementSettlement
from gameclub_backend.modules.entitlements.infrastructure.memory import (
    InMemoryEntitlementRepository,
)
from gameclub_backend.modules.entitlements.infrastructure.postgres import (
    PostgresEntitlementRepository,
)
from gameclub_backend.modules.notifications.application.ports import NotificationRuleRepository
from gameclub_backend.modules.notifications.application.service import NotificationRuleService
from gameclub_backend.modules.notifications.infrastructure.memory import (
    InMemoryNotificationRuleRepository,
)
from gameclub_backend.modules.notifications.infrastructure.postgres import (
    PostgresNotificationRuleRepository,
)
from gameclub_backend.modules.notifications.infrastructure.session import (
    SessionTimeNotificationLookup,
)
from gameclub_backend.modules.offline.application.ports import OfflineReplayRepository
from gameclub_backend.modules.offline.application.service import OfflineReplayService
from gameclub_backend.modules.offline.infrastructure.memory import InMemoryOfflineReplayRepository
from gameclub_backend.modules.offline.infrastructure.postgres import PostgresOfflineReplayRepository
from gameclub_backend.modules.payment_methods.application.ports import PaymentMethodRepository
from gameclub_backend.modules.payment_methods.application.service import PaymentMethodService
from gameclub_backend.modules.payment_methods.infrastructure.memory import (
    InMemoryPaymentMethodRepository,
)
from gameclub_backend.modules.payment_methods.infrastructure.postgres import (
    PostgresPaymentMethodRepository,
)
from gameclub_backend.modules.reservations.application.ports import ReservationRepository
from gameclub_backend.modules.reservations.application.service import ReservationService
from gameclub_backend.modules.reservations.infrastructure.memory import (
    InMemoryReservationRepository,
)
from gameclub_backend.modules.reservations.infrastructure.postgres import (
    PostgresReservationRepository,
)
from gameclub_backend.modules.sales.application.ports import ProductSaleRepository
from gameclub_backend.modules.sales.application.service import ProductSaleService
from gameclub_backend.modules.sales.infrastructure.cash import CashShiftSaleSettlement
from gameclub_backend.modules.sales.infrastructure.memory import InMemoryProductSaleRepository
from gameclub_backend.modules.sales.infrastructure.postgres import PostgresProductSaleRepository
from gameclub_backend.modules.sessions.application.ports import (
    SessionRepository,
    SessionTransferRepository,
)
from gameclub_backend.modules.sessions.application.service import SessionService
from gameclub_backend.modules.sessions.application.transfer import SessionTransferService
from gameclub_backend.modules.sessions.infrastructure.memory import InMemorySessionRepository
from gameclub_backend.modules.sessions.infrastructure.postgres import PostgresSessionRepository
from gameclub_backend.modules.sessions.infrastructure.transfers_memory import (
    InMemorySessionTransferRepository,
)
from gameclub_backend.modules.sessions.infrastructure.transfers_postgres import (
    PostgresSessionTransferRepository,
)
from gameclub_backend.modules.workstations.application.commands import WorkstationCommandService
from gameclub_backend.modules.workstations.application.groups import WorkstationGroupService
from gameclub_backend.modules.workstations.application.ports import (
    WorkstationCommandRepository,
    WorkstationGroupRepository,
    WorkstationRepository,
)
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
from gameclub_backend.modules.workstations.infrastructure.commands_redis import RedisCommandNotifier
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


@dataclass(slots=True)
class ApplicationServices:
    workstations: WorkstationService
    workstation_groups: WorkstationGroupService
    clients: ClientService
    client_groups: ClientGroupService
    notifications: NotificationRuleService
    guests: GuestService
    catalog: CatalogService
    entitlements: EntitlementService
    offline: OfflineReplayService
    guest_payments: GuestSessionPaymentService
    reservations: ReservationService
    sessions: SessionService
    billing: BillingService
    billing_reconciliation: ChargeReconciliationRepository
    cash_shifts: CashShiftService
    sales: ProductSaleService
    payment_methods: PaymentMethodService
    analytics: AnalyticsService
    session_transfers: SessionTransferService
    client_portal: ClientPortalService
    command_service: WorkstationCommandService
    audit_repository: AuditRepository


def build_application_services(
    settings: Settings,
    resources: InfrastructureResources,
) -> ApplicationServices:
    def engine_provider() -> AsyncEngine | None:
        return resources.engine

    postgres_engine_provider: EngineProvider = engine_provider
    if settings.postgres_dsn:
        workstation_repository: WorkstationRepository = PostgresWorkstationRepository(
            postgres_engine_provider
        )
        workstation_group_repository: WorkstationGroupRepository = (
            PostgresWorkstationGroupRepository(postgres_engine_provider)
        )
        client_repository: ClientRepository = PostgresClientRepository(postgres_engine_provider)
        client_group_repository: ClientGroupRepository = PostgresClientGroupRepository(
            postgres_engine_provider
        )
        notification_repository: NotificationRuleRepository = PostgresNotificationRuleRepository(
            postgres_engine_provider
        )
        guest_repository: GuestRepository = PostgresGuestRepository(postgres_engine_provider)
        catalog_repository: CatalogRepository = PostgresCatalogRepository(postgres_engine_provider)
        reservation_repository: ReservationRepository = PostgresReservationRepository(
            postgres_engine_provider
        )
        command_repository: WorkstationCommandRepository = PostgresWorkstationCommandRepository(
            postgres_engine_provider
        )
        session_repository: SessionRepository = PostgresSessionRepository(postgres_engine_provider)
        billing_repository: ChargeRepository = PostgresChargeRepository(postgres_engine_provider)
        billing_reconciliation_repository: ChargeReconciliationRepository = (
            PostgresChargeReconciliationRepository(postgres_engine_provider)
        )
        meter_repository: MeterRepository = PostgresMeterRepository(postgres_engine_provider)
        cash_shift_repository: CashShiftRepository = PostgresCashShiftRepository(
            postgres_engine_provider
        )
        cash_approval_repository: CashApprovalRepository = PostgresCashApprovalRepository(
            postgres_engine_provider
        )
        sales_repository: ProductSaleRepository = PostgresProductSaleRepository(
            postgres_engine_provider
        )
        payment_method_repository: PaymentMethodRepository = PostgresPaymentMethodRepository(
            postgres_engine_provider
        )
        entitlement_repository: EntitlementRepository = PostgresEntitlementRepository(
            postgres_engine_provider
        )
        guest_payment_repository: GuestSessionPaymentRepository = (
            PostgresGuestSessionPaymentRepository(postgres_engine_provider)
        )
        transfer_repository: SessionTransferRepository = PostgresSessionTransferRepository(
            postgres_engine_provider
        )
        offline_repository: OfflineReplayRepository = PostgresOfflineReplayRepository(
            postgres_engine_provider
        )
        analytics_repository: AnalyticsRepository = PostgresAnalyticsRepository(
            postgres_engine_provider
        )
        audit_repository: AuditRepository = PostgresAuditRepository(postgres_engine_provider)
    else:
        workstation_repository = InMemoryWorkstationRepository()
        workstation_group_repository = InMemoryWorkstationGroupRepository()
        client_repository = InMemoryClientRepository()
        client_group_repository = InMemoryClientGroupRepository()
        notification_repository = InMemoryNotificationRuleRepository()
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
        analytics_repository = InMemoryAnalyticsRepository()
        audit_repository = InMemoryAuditRepository()

    workstation_cache = (
        RedisWorkstationSnapshotCache(lambda: resources.redis)
        if resources.redis is not None
        else None
    )
    notifier = (
        RedisCommandNotifier(lambda: resources.redis)
        if resources.redis is not None
        else InMemoryCommandNotifier()
    )
    workstations = WorkstationService(
        workstation_repository,
        stale_after_seconds=settings.workstation_stale_after_seconds,
        offline_after_seconds=settings.workstation_offline_after_seconds,
        groups=workstation_group_repository,
        cache=workstation_cache,
        cache_ttl_seconds=20,
    )
    client_groups = ClientGroupService(client_group_repository, audit=audit_repository)
    notifications = NotificationRuleService(notification_repository)
    session_notifications = SessionTimeNotificationLookup(notifications)
    clients = ClientService(client_repository, groups=client_group_repository)
    guests = GuestService(guest_repository)
    catalog = CatalogService(catalog_repository, zones=workstation_group_repository)
    cash_shifts = CashShiftService(cash_shift_repository, approvals=cash_approval_repository)
    workstation_groups = WorkstationGroupService(
        workstation_group_repository,
        zone_rate_synchronizer=catalog,
    )
    entitlements = EntitlementService(
        entitlement_repository,
        tariffs=catalog,
        clients=clients,
        active_sessions=session_repository,
        workstations=workstation_repository,
        cash=CashShiftEntitlementSettlement(cash_shifts),
    )
    reservations = ReservationService(
        reservation_repository,
        workstations=workstation_repository,
        clients=client_repository,
        guests=guest_repository,
        grace_period_minutes=settings.reservation_grace_period_minutes,
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
    guest_payments = GuestSessionPaymentService(
        guest_payment_repository,
        tariffs=catalog,
        cash=CashShiftGuestPaymentSettlement(cash_shifts),
        audit=audit_repository,
        workstations=workstation_repository,
        active_sessions=session_repository,
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
        tariffs=catalog,
        notifications=session_notifications,
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
        notifier=notifier,
        command_ttl_seconds=settings.workstation_command_ttl_seconds,
    )
    session_transfers = SessionTransferService(
        transfer_repository,
        sessions=session_repository,
        workstations=workstation_repository,
        reservations=reservations,
        entitlements=entitlements,
        commands=command_service,
    )

    client_portal = ClientPortalService(
        clients=clients,
        sessions=sessions,
        charges=billing,
        sales=sales,
        tariffs=catalog,
        entitlements=entitlements,
        workstations=workstation_repository,
        payment_methods=payment_methods,
        reservations=reservation_repository,
    )
    return ApplicationServices(
        workstations=workstations,
        workstation_groups=workstation_groups,
        clients=clients,
        client_groups=client_groups,
        notifications=notifications,
        guests=guests,
        catalog=catalog,
        entitlements=entitlements,
        offline=offline,
        guest_payments=guest_payments,
        reservations=reservations,
        sessions=sessions,
        billing=billing,
        billing_reconciliation=billing_reconciliation_repository,
        cash_shifts=cash_shifts,
        sales=sales,
        payment_methods=payment_methods,
        analytics=analytics,
        session_transfers=session_transfers,
        client_portal=client_portal,
        command_service=command_service,
        audit_repository=audit_repository,
    )
