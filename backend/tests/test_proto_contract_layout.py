from pathlib import Path

from gameclub.v1 import (
    analytics_pb2,
    billing_pb2,
    cash_shifts_pb2,
    catalog_pb2,
    clients_pb2,
    reservations_pb2,
    sessions_pb2,
    workstations_pb2,
)

PROJECT_ROOT = Path(__file__).parents[1].parent


def test_proto_sources_have_generated_python_and_csharp_consumers() -> None:
    proto_root = PROJECT_ROOT / "backend" / "proto" / "gameclub" / "v1"
    generated_root = PROJECT_ROOT / "backend" / "src" / "gameclub" / "v1"
    csproj = (
        PROJECT_ROOT / "win-client" / "src" / "GameClub.Client" / "GameClub.Client.csproj"
    ).read_text()

    for proto_path in proto_root.glob("*.proto"):
        assert (generated_root / f"{proto_path.stem}_pb2.py").exists()
        assert (generated_root / f"{proto_path.stem}_pb2_grpc.py").exists()
        assert proto_path.name in csproj


def test_catalog_contract_contains_discount_and_lifecycle_methods() -> None:
    service = catalog_pb2.DESCRIPTOR.services_by_name["CatalogService"]
    methods = service.methods_by_name

    assert {
        "CreateDiscountRule",
        "ListDiscountRules",
        "PublishTariff",
        "ArchiveTariff",
        "GetCatalogSnapshot",
        "Quote",
    }.issubset(methods)


def test_reservation_contract_contains_availability_and_lifecycle_methods() -> None:
    service = reservations_pb2.DESCRIPTOR.services_by_name["ReservationService"]
    methods = service.methods_by_name

    assert {
        "CheckAvailability",
        "Create",
        "List",
        "Get",
        "Update",
        "Cancel",
        "Activate",
        "Complete",
        "MarkNoShow",
    }.issubset(methods)
    assert "status" in reservations_pb2.Reservation.DESCRIPTOR.fields_by_name


def test_session_contract_contains_idempotent_lifecycle_methods() -> None:
    service = sessions_pb2.DESCRIPTOR.services_by_name["SessionService"]
    assert {"Start", "Get", "List", "Stop"}.issubset(service.methods_by_name)
    assert "idempotency_key" in sessions_pb2.Session.DESCRIPTOR.fields_by_name
    assert "idempotency_key" in sessions_pb2.StartSessionRequest.DESCRIPTOR.fields_by_name
    assert "device_id" in sessions_pb2.StartSessionRequest.DESCRIPTOR.fields_by_name
    assert "device_id" in sessions_pb2.StopSessionRequest.DESCRIPTOR.fields_by_name
    assert "guest_id" in sessions_pb2.Session.DESCRIPTOR.fields_by_name
    assert "guest_id" in sessions_pb2.StartSessionRequest.DESCRIPTOR.fields_by_name
    assert "tariff_id" in sessions_pb2.Session.DESCRIPTOR.fields_by_name
    assert "tariff_id" in sessions_pb2.StartSessionRequest.DESCRIPTOR.fields_by_name


def test_billing_contract_contains_idempotent_session_charge_methods() -> None:
    service = billing_pb2.DESCRIPTOR.services_by_name["BillingService"]
    assert {"ChargeSession", "GetSessionCharge", "GetRevenue"}.issubset(service.methods_by_name)
    assert "idempotency_key" in billing_pb2.ChargeSessionRequest.DESCRIPTOR.fields_by_name
    assert "balance_operation_id" in billing_pb2.SessionCharge.DESCRIPTOR.fields_by_name
    assert "amount_cents" in billing_pb2.RevenueSummary.DESCRIPTOR.fields_by_name


def test_analytics_contract_contains_versioned_read_methods_and_breakdowns() -> None:
    service = analytics_pb2.DESCRIPTOR.services_by_name["AnalyticsService"]
    assert {"GetOverview", "GetClient"}.issubset(service.methods_by_name)
    assert "start_at" in analytics_pb2.GetAnalyticsOverviewRequest.DESCRIPTOR.fields_by_name
    assert "client_id" in analytics_pb2.GetClientAnalyticsRequest.DESCRIPTOR.fields_by_name
    assert "zones" in analytics_pb2.AnalyticsOverview.DESCRIPTOR.fields_by_name
    assert "favorite_products" in analytics_pb2.ClientAnalytics.DESCRIPTOR.fields_by_name


def test_cash_shift_contract_contains_ledger_lifecycle_methods() -> None:
    service = cash_shifts_pb2.DESCRIPTOR.services_by_name["CashShiftService"]
    assert {
        "Open",
        "Get",
        "List",
        "ListMovements",
        "RecordMovement",
        "Close",
        "Approve",
    }.issubset(service.methods_by_name)
    assert "expected_close_cents" in cash_shifts_pb2.CashShift.DESCRIPTOR.fields_by_name
    assert "idempotency_key" in cash_shifts_pb2.RecordCashMovementRequest.DESCRIPTOR.fields_by_name
    assert "approval_id" in cash_shifts_pb2.RecordCashMovementRequest.DESCRIPTOR.fields_by_name
    assert "approval_id" in cash_shifts_pb2.CloseCashShiftRequest.DESCRIPTOR.fields_by_name
    assert "reason" in cash_shifts_pb2.CashApproval.DESCRIPTOR.fields_by_name


def test_cash_risk_controls_are_enforced_in_application_service() -> None:
    service_source = (
        PROJECT_ROOT
        / "backend"
        / "src"
        / "gameclub_backend"
        / "modules"
        / "cash_shifts"
        / "application"
        / "service.py"
    ).read_text()
    ports_source = (
        PROJECT_ROOT
        / "backend"
        / "src"
        / "gameclub_backend"
        / "modules"
        / "cash_shifts"
        / "application"
        / "ports.py"
    ).read_text()

    assert "CashApprovalKind.CORRECTION.value" in service_source
    assert "CashApprovalKind.CLOSE_DIFFERENCE.value" in service_source
    assert "approval_id" in service_source
    assert "allow_correction" not in service_source
    assert "expected_close_cents" in ports_source


def test_clients_contract_contains_balance_operation_history() -> None:
    service = clients_pb2.DESCRIPTOR.services_by_name["ClientService"]
    assert "ListBalanceOperations" in service.methods_by_name
    assert "created_at" in clients_pb2.BalanceOperation.DESCRIPTOR.fields_by_name
    assert "limit" in clients_pb2.ListBalanceOperationsRequest.DESCRIPTOR.fields_by_name
    assert {
        "CreateGuest",
        "SearchGuests",
        "GetGuest",
        "ListGuests",
    }.issubset(service.methods_by_name)
    assert "discount_category" in clients_pb2.Guest.DESCRIPTOR.fields_by_name


def test_guest_links_are_present_in_reservation_and_frontend_contracts() -> None:
    assert "guest_id" in reservations_pb2.Reservation.DESCRIPTOR.fields_by_name
    assert "guest_id" in reservations_pb2.CreateReservationRequest.DESCRIPTOR.fields_by_name
    assert "guest_id" in reservations_pb2.UpdateReservationRequest.DESCRIPTOR.fields_by_name
    api_source = (PROJECT_ROOT / "frontend" / "src" / "api.ts").read_text()
    assert "BackendGuest" in api_source
    assert "searchGuests" in api_source
    assert "createGuest" in api_source
    assert "guest_id" in api_source


def test_billing_reconciliation_has_migration_and_worker_boundary() -> None:
    migration = (
        PROJECT_ROOT
        / "backend"
        / "alembic"
        / "versions"
        / "20260827_0013_billing_reconciliation.py"
    ).read_text()
    worker = (
        PROJECT_ROOT / "backend" / "src" / "gameclub_backend" / "jobs" / "billing.py"
    ).read_text()

    assert "billing_reconciliations" in migration
    assert "reconcile_billing_charges" in worker
    assert "PostgresChargeReconciliationRepository" in worker


def test_workstation_contract_contains_group_theme_configuration() -> None:
    service = workstations_pb2.DESCRIPTOR.services_by_name["WorkstationService"]
    assert {"ListGroups", "UpsertGroup"}.issubset(service.methods_by_name)
    assert "theme" in workstations_pb2.Workstation.DESCRIPTOR.fields_by_name
    assert "theme" in workstations_pb2.WorkstationGroup.DESCRIPTOR.fields_by_name


def test_frontend_bff_mentions_current_auth_and_catalog_routes() -> None:
    api_source = (PROJECT_ROOT / "frontend" / "src" / "api.ts").read_text()

    assert "/auth/refresh" in api_source
    assert "/catalog/discount-rules" in api_source
    assert "/catalog/snapshot" in api_source
    assert "/catalog/quote" in api_source
    assert "/billing/sessions/" in api_source
    assert "createTariff" in api_source
    assert "createProduct" in api_source
    assert "createDiscountRule" in api_source
    assert "registerWorkstation" in api_source
    assert "listWorkstationGroups" in api_source
    assert "saveWorkstationGroup" in api_source
    assert "getRevenue" in api_source


def test_audit_read_model_has_http_and_frontend_boundaries() -> None:
    audit_route = (
        PROJECT_ROOT / "backend" / "src" / "gameclub_backend" / "presentation" / "http" / "audit.py"
    ).read_text()
    api_source = (PROJECT_ROOT / "frontend" / "src" / "api.ts").read_text()

    assert 'prefix="/api/v1/audit"' in audit_route
    assert 'require_permissions("audit.read")' in audit_route
    assert "listAuditEvents" in api_source


def test_windows_session_executor_uses_structured_backend_contract() -> None:
    project_root = PROJECT_ROOT / "win-client" / "src" / "GameClub.Client"
    executor_source = (project_root / "Infrastructure" / "WindowsCommandExecutor.cs").read_text()
    grpc_source = (project_root / "Infrastructure" / "GrpcBackendClient.cs").read_text()
    window_source = (project_root / "MainWindow.xaml.cs").read_text()
    xaml_source = (project_root / "MainWindow.xaml").read_text()
    view_model_source = (project_root / "Presentation" / "MainViewModel.cs").read_text()
    endpoint_policy_source = (project_root / "Infrastructure" / "EndpointPolicy.cs").read_text()
    token_provider_source = (
        project_root / "Infrastructure" / "DeviceBootstrapTokenProvider.cs"
    ).read_text()

    assert 'case "session.start"' in executor_source
    assert 'case "session.stop"' in executor_source
    assert '"client_id"' in executor_source
    assert '"session_id"' in executor_source
    assert "SessionService.SessionServiceClient" in grpc_source
    assert "DeviceAuthenticationRequiredException" in grpc_source
    assert "StatusCode.Unauthenticated" in grpc_source
    assert "MainWindowActivated" in window_source
    assert "WindowActivationState.Deactivated" in window_source
    assert "SecuredContentVisibility" in xaml_source
    assert "SecuredContentVisibility" in view_model_source
    assert "DeviceId = deviceId" in grpc_source
    assert "response.Theme" in grpc_source
    assert "ApplyThemeFromHeartbeat" in window_source
    assert "ApplyWorkstationTheme" in window_source
    assert "_viewModel.IsExpanded = isCompact" in window_source
    assert "WindowModeActionLabel" in view_model_source
    assert '"vip" => "VIP-зона"' in view_model_source
    assert "GAMECLUB_ENVIRONMENT" in window_source
    assert "EndpointPolicy.GetEnvironmentEndpoint" in window_source
    assert "HTTPS outside dev loopback" in endpoint_policy_source
    assert "EndpointPolicy.Validate" in token_provider_source


def test_windows_support_check_is_reproducible_and_platform_explicit() -> None:
    script = (PROJECT_ROOT / "win-client" / "scripts" / "verify-windows.ps1").read_text()

    assert "dotnet restore" in script
    assert "dotnet build" in script
    assert "RuntimeInformation" in script
    assert "обычным пользователем" in script
    assert "Перезапустить клиент" in script
    assert "стартует Locked" in script
    assert "manager password" in script
    assert "Assigned Access" in script


def test_windows_access_gate_has_locked_start_and_manager_boundary() -> None:
    project_root = PROJECT_ROOT / "win-client" / "src" / "GameClub.Client"
    coordinator = (project_root / "Application" / "AccessGateCoordinator.cs").read_text()
    view_model = (project_root / "Presentation" / "MainViewModel.cs").read_text()
    credentials = (
        project_root / "Infrastructure" / "EnvironmentAccessCredentialVerifier.cs"
    ).read_text()
    verifier = (project_root / "Infrastructure" / "PasswordHashVerifier.cs").read_text()
    coordinator_source = (project_root / "Application" / "AccessGateCoordinator.cs").read_text()
    window = (project_root / "MainWindow.xaml").read_text()
    hash_script = (PROJECT_ROOT / "win-client" / "scripts" / "new-access-hash.ps1").read_text()
    docs = (PROJECT_ROOT / "win-client" / "docs" / "ACCESS-GATE.md").read_text()

    assert "AccessMode.Locked" in coordinator
    assert (
        "AuthenticationRequired"
        in (project_root / "Domain" / "ClientConnectionState.cs").read_text()
    )
    assert (
        "DeviceAuthenticationRequiredException"
        in (project_root / "Application" / "ClientSessionCoordinator.cs").read_text()
    )
    assert "TryUnlockUser" in coordinator
    assert "TryEnterMaintenance" in coordinator
    assert "LockIfIdle" in coordinator
    assert (
        "GAMECLUB_MANAGER_PASSWORD_HASH" in view_model
        or "GAMECLUB_MANAGER_PASSWORD_HASH" in credentials
    )
    assert "FixedTimeEquals" in verifier
    assert "MaxFailedAttempts" in coordinator_source
    assert "ZeroFreeBSTR" in hash_script
    assert 'Visibility="{Binding AccessGateVisibility}"' in window
    assert "Assigned Access" in docs


def test_grpc_production_requires_explicit_tls_configuration() -> None:
    config_source = (
        PROJECT_ROOT / "backend" / "src" / "gameclub_backend" / "config.py"
    ).read_text()
    server_source = (
        PROJECT_ROOT
        / "backend"
        / "src"
        / "gameclub_backend"
        / "presentation"
        / "grpc"
        / "server.py"
    ).read_text()
    threat_model = (
        PROJECT_ROOT / "plans" / "04-auth-security" / "THREAT-MODEL.md"
    ).read_text()

    assert "grpc_tls_cert_file" in config_source
    assert "grpc_tls_key_file" in config_source
    assert "create_grpc_server_credentials" in server_source
    assert 'environment in {"prod", "production"}' in server_source
    assert "`sub`" in threat_model
