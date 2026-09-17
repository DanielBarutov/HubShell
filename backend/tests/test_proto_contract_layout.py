from pathlib import Path

import pytest

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


pytestmark = pytest.mark.contract


def test_proto_sources_have_generated_python_and_csharp_consumers() -> None:
    """
    Проверяет сценарий «test_proto_sources_have_generated_python_and_csharp_consumers» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    proto_root = PROJECT_ROOT / "backend" / "proto" / "gameclub" / "v1"
    generated_root = PROJECT_ROOT / "backend" / "src" / "gameclub" / "v1"
    csproj = (
        PROJECT_ROOT
        / "win-client"
        / "src"
        / "GameClub.Client.Transport.Grpc"
        / "GameClub.Client.Transport.Grpc.csproj"
    ).read_text()
    publish_script = (PROJECT_ROOT / "win-client" / "scripts" / "publish-windows.ps1").read_text()
    verify_script = (PROJECT_ROOT / "win-client" / "scripts" / "verify-windows.ps1").read_text()
    windows_project = (
        PROJECT_ROOT
        / "win-client"
        / "src"
        / "GameClub.Client.Windows"
        / "GameClub.Client.Windows.csproj"
    ).read_text()
    tray_source = (
        PROJECT_ROOT
        / "win-client"
        / "src"
        / "GameClub.Client"
        / "Infrastructure"
        / "NativeTrayIcon.cs"
    ).read_text()
    assert "<Protobuf_ProtoRoot>..\\..\\..\\backend\\proto</Protobuf_ProtoRoot>" in csproj
    assert "<UseWindowsForms>true</UseWindowsForms>" not in csproj
    assert "<UseWPF>true</UseWPF>" not in csproj
    assert "GameClub.Client.Windows.csproj" in publish_script
    assert "--runtime $runtime" in publish_script
    assert "-p:Platform=$Architecture" in publish_script
    assert "-p:GameClubEnvironment=$EnvironmentName" in publish_script
    assert "GameClub.Client.Windows.sln" in verify_script
    assert "test $linuxFirstSolutionPath.Path" in verify_script
    assert "<TargetFramework>net8.0</TargetFramework>" in windows_project
    assert "UseWPF" not in windows_project
    assert "UseWindowsForms" not in windows_project
    assert "NativeTrayIcon" in (
        PROJECT_ROOT
        / "win-client"
        / "src"
        / "GameClub.Client.Windows"
        / "WindowsClientWindowAdapter.cs"
    ).read_text()
    assert "Shell_NotifyIcon" in tray_source

    for proto_path in proto_root.glob("*.proto"):
        assert (generated_root / f"{proto_path.stem}_pb2.py").exists()
        assert (generated_root / f"{proto_path.stem}_pb2_grpc.py").exists()
        assert proto_path.name in csproj


def test_catalog_contract_contains_discount_and_lifecycle_methods() -> None:
    """
    Проверяет сценарий «test_catalog_contract_contains_discount_and_lifecycle_methods» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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


def test_tariff_contract_contains_time_windows_and_audience() -> None:
    """
    Проверяет, что HTTP/gRPC snapshot-контракты не теряют ограничения тарифа.
    """
    tariff_fields = catalog_pb2.Tariff.DESCRIPTOR.fields_by_name
    create_fields = catalog_pb2.CreateTariffRequest.DESCRIPTOR.fields_by_name
    quote_fields = catalog_pb2.QuoteRequest.DESCRIPTOR.fields_by_name
    portal_tariff_fields = clients_pb2.PortalTariff.DESCRIPTOR.fields_by_name
    portal_entitlement_fields = clients_pb2.PortalEntitlement.DESCRIPTOR.fields_by_name
    package_fields = sessions_pb2.PackageSnapshot.DESCRIPTOR.fields_by_name

    for fields in (
        tariff_fields,
        create_fields,
        portal_tariff_fields,
        portal_entitlement_fields,
    ):
        assert "time_restricted" in fields
        assert "sale_window_start_minute" in fields
        assert "sale_window_end_minute" in fields
        assert "usage_window_start_minute" in fields
        assert "usage_window_end_minute" in fields
        assert "window_timezone" in fields
        assert "audience" in fields
    assert "audience" in quote_fields
    assert "time_restricted" in package_fields
    assert "usage_window_start_minute" in package_fields
    assert "usage_window_end_minute" in package_fields
    assert "window_timezone" in package_fields
    assert "audience" in package_fields


def test_reservation_contract_contains_availability_and_lifecycle_methods() -> None:
    """
    Проверяет сценарий «test_reservation_contract_contains_availability_and_lifecycle_methods» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    service = reservations_pb2.DESCRIPTOR.services_by_name["ReservationService"]
    methods = service.methods_by_name

    assert {
        "CheckAvailability",
        "CheckEntry",
        "Create",
        "List",
        "Get",
        "Update",
        "Cancel",
        "Activate",
        "Complete",
        "MarkNoShow",
    }.issubset(methods)
    assert "reason" in reservations_pb2.CheckEntryResponse.DESCRIPTOR.fields_by_name
    assert "device_id" in reservations_pb2.CheckEntryRequest.DESCRIPTOR.fields_by_name
    assert "status" in reservations_pb2.Reservation.DESCRIPTOR.fields_by_name


def test_session_contract_contains_idempotent_lifecycle_methods() -> None:
    """
    Проверяет сценарий «test_session_contract_contains_idempotent_lifecycle_methods» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    service = sessions_pb2.DESCRIPTOR.services_by_name["SessionService"]
    assert {"Start", "Get", "GetSnapshot", "List", "Stop"}.issubset(service.methods_by_name)
    assert "idempotency_key" in sessions_pb2.Session.DESCRIPTOR.fields_by_name
    assert "idempotency_key" in sessions_pb2.StartSessionRequest.DESCRIPTOR.fields_by_name
    assert "device_id" in sessions_pb2.StartSessionRequest.DESCRIPTOR.fields_by_name
    assert "device_id" in sessions_pb2.StopSessionRequest.DESCRIPTOR.fields_by_name
    assert "guest_id" in sessions_pb2.Session.DESCRIPTOR.fields_by_name
    assert "guest_id" in sessions_pb2.StartSessionRequest.DESCRIPTOR.fields_by_name
    assert "tariff_id" in sessions_pb2.Session.DESCRIPTOR.fields_by_name
    assert "tariff_id" in sessions_pb2.StartSessionRequest.DESCRIPTOR.fields_by_name
    assert "schema_version" in sessions_pb2.SessionSnapshot.DESCRIPTOR.fields_by_name
    assert "package_minutes" in sessions_pb2.SessionMeterSnapshot.DESCRIPTOR.fields_by_name
    assert "active_tariff" in sessions_pb2.SessionSnapshot.DESCRIPTOR.fields_by_name
    assert "login_grant_remaining_minutes" in sessions_pb2.SessionSnapshot.DESCRIPTOR.fields_by_name
    assert "remaining_minutes" in sessions_pb2.SessionTariffSnapshot.DESCRIPTOR.fields_by_name


def test_billing_contract_contains_idempotent_session_charge_methods() -> None:
    """
    Проверяет сценарий «test_billing_contract_contains_idempotent_session_charge_methods» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    service = billing_pb2.DESCRIPTOR.services_by_name["BillingService"]
    assert {"ChargeSession", "GetSessionCharge", "GetRevenue"}.issubset(service.methods_by_name)
    assert "idempotency_key" in billing_pb2.ChargeSessionRequest.DESCRIPTOR.fields_by_name
    assert "balance_operation_id" in billing_pb2.SessionCharge.DESCRIPTOR.fields_by_name
    assert "amount_cents" in billing_pb2.RevenueSummary.DESCRIPTOR.fields_by_name


def test_analytics_contract_contains_versioned_read_methods_and_breakdowns() -> None:
    """
    Проверяет сценарий «test_analytics_contract_contains_versioned_read_methods_and_breakdowns»
    и подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    service = analytics_pb2.DESCRIPTOR.services_by_name["AnalyticsService"]
    assert {"GetOverview", "GetClient"}.issubset(service.methods_by_name)
    assert "start_at" in analytics_pb2.GetAnalyticsOverviewRequest.DESCRIPTOR.fields_by_name
    assert "client_id" in analytics_pb2.GetClientAnalyticsRequest.DESCRIPTOR.fields_by_name
    assert "zones" in analytics_pb2.AnalyticsOverview.DESCRIPTOR.fields_by_name
    assert "favorite_products" in analytics_pb2.ClientAnalytics.DESCRIPTOR.fields_by_name


def test_cash_shift_contract_contains_ledger_lifecycle_methods() -> None:
    """
    Проверяет сценарий «test_cash_shift_contract_contains_ledger_lifecycle_methods» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_cash_risk_controls_are_enforced_in_application_service» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_clients_contract_contains_balance_operation_history» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    portal_service = clients_pb2.DESCRIPTOR.services_by_name["ClientPortalService"]
    assert {"Register", "Login", "Get", "ActivateEntitlement", "PurchaseEntitlement"}.issubset(
        portal_service.methods_by_name
    )
    assert "device_id" in clients_pb2.RegisterPortalRequest.DESCRIPTOR.fields_by_name
    assert "password" in clients_pb2.RegisterPortalRequest.DESCRIPTOR.fields_by_name
    assert "password" in clients_pb2.LoginPortalRequest.DESCRIPTOR.fields_by_name
    assert "ChangePassword" in {method.name for method in portal_service.methods}
    assert "password_reset_required" in clients_pb2.ClientPortalSession.DESCRIPTOR.fields_by_name
    assert "tariff_name" in clients_pb2.PortalSession.DESCRIPTOR.fields_by_name
    assert "tariff_name" in clients_pb2.PortalCharge.DESCRIPTOR.fields_by_name
    assert "entitlements" in clients_pb2.ClientPortalSnapshot.DESCRIPTOR.fields_by_name
    assert "queue_position" in clients_pb2.PortalEntitlement.DESCRIPTOR.fields_by_name
    assert "tariffs" in clients_pb2.ClientPortalSnapshot.DESCRIPTOR.fields_by_name
    assert "reservations" in clients_pb2.ClientPortalSnapshot.DESCRIPTOR.fields_by_name


def test_guest_links_are_present_in_reservation_and_frontend_contracts() -> None:
    """
    Проверяет сценарий «test_guest_links_are_present_in_reservation_and_frontend_contracts» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    assert "guest_id" in reservations_pb2.Reservation.DESCRIPTOR.fields_by_name
    assert "guest_id" in reservations_pb2.CreateReservationRequest.DESCRIPTOR.fields_by_name
    assert "guest_id" in reservations_pb2.UpdateReservationRequest.DESCRIPTOR.fields_by_name
    api_source = (PROJECT_ROOT / "frontend" / "src" / "api" / "client.ts").read_text()
    assert "BackendGuest" in api_source
    assert "searchGuests" in api_source
    assert "createGuest" in api_source
    assert "guest_id" in api_source


def test_billing_reconciliation_has_migration_and_worker_boundary() -> None:
    """
    Проверяет сценарий «test_billing_reconciliation_has_migration_and_worker_boundary» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    """
    Проверяет сценарий «test_workstation_contract_contains_group_theme_configuration» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    service = workstations_pb2.DESCRIPTOR.services_by_name["WorkstationService"]
    assert {"ListGroups", "UpsertGroup"}.issubset(service.methods_by_name)
    assert "theme" in workstations_pb2.Workstation.DESCRIPTOR.fields_by_name
    assert "theme" in workstations_pb2.WorkstationGroup.DESCRIPTOR.fields_by_name
    assert "per_minute_price_cents" in workstations_pb2.WorkstationGroup.DESCRIPTOR.fields_by_name
    assert (
        "per_minute_price_cents"
        in workstations_pb2.UpsertWorkstationGroupRequest.DESCRIPTOR.fields_by_name
    )


def test_frontend_bff_mentions_current_auth_and_catalog_routes() -> None:
    """
    Проверяет сценарий «test_frontend_bff_mentions_current_auth_and_catalog_routes» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    api_source = (PROJECT_ROOT / "frontend" / "src" / "api" / "client.ts").read_text()

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
    """
    Проверяет сценарий «test_audit_read_model_has_http_and_frontend_boundaries» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    audit_route = (
        PROJECT_ROOT / "backend" / "src" / "gameclub_backend" / "presentation" / "http" / "audit.py"
    ).read_text()
    api_source = (PROJECT_ROOT / "frontend" / "src" / "api" / "client.ts").read_text()

    assert 'prefix="/api/v1/audit"' in audit_route
    assert 'require_permissions("audit.read")' in audit_route
    assert "listAuditEvents" in api_source


def test_windows_session_executor_uses_structured_backend_contract() -> None:
    """
    Проверяет сценарий «test_windows_session_executor_uses_structured_backend_contract» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    project_root = PROJECT_ROOT / "win-client" / "src" / "GameClub.Client"
    executor_source = (project_root / "Infrastructure" / "WindowsCommandExecutor.cs").read_text()
    grpc_source = (project_root / "Infrastructure" / "GrpcBackendClient.cs").read_text()
    window_source = (
        PROJECT_ROOT / "win-client" / "src" / "GameClub.Client.Avalonia" / "MainWindow.axaml.cs"
    ).read_text()
    xaml_source = (
        PROJECT_ROOT / "win-client" / "src" / "GameClub.Client.Avalonia" / "MainWindow.axaml"
    ).read_text()
    view_model_source = (project_root / "Presentation" / "MainViewModel.cs").read_text()
    host_source = (
        PROJECT_ROOT
        / "win-client"
        / "src"
        / "GameClub.Client.Windows"
        / "WindowsClientHost.cs"
    ).read_text()
    app_source = (
        PROJECT_ROOT
        / "win-client"
        / "src"
        / "GameClub.Client.Avalonia"
        / "App.axaml.cs"
    ).read_text()
    deployment_source = (
        project_root / "Infrastructure" / "DeploymentSettings.cs"
    ).read_text()
    endpoint_policy_source = (project_root / "Infrastructure" / "EndpointPolicy.cs").read_text()
    token_provider_source = (
        project_root / "Infrastructure" / "DeviceBootstrapTokenProvider.cs"
    ).read_text()

    assert 'case "session.start"' in executor_source
    assert 'case "session.stop"' in executor_source
    assert "CheckEntryAsync" in executor_source
    assert "if (!entry.Allowed)" in executor_source
    assert "response.StartsAt is not null" in grpc_source
    assert "response.EndsAt is not null" in grpc_source
    assert '"client_id"' in executor_source
    assert '"session_id"' in executor_source
    assert "SessionService.SessionServiceClient" in grpc_source
    assert "DeviceAuthenticationRequiredException" in grpc_source
    assert "StatusCode.Unauthenticated" in grpc_source
    window_adapter_source = (
        PROJECT_ROOT
        / "win-client"
        / "src"
        / "GameClub.Client.Windows"
        / "WindowsClientWindowAdapter.cs"
    ).read_text()
    assert "ApplyHostWindowMode" in window_source
    assert "WindowAdapter" in window_source
    assert "ApplyWindowMode" in window_adapter_source
    assert "WindowState.FullScreen" in window_adapter_source
    assert "WindowState.Normal" in window_adapter_source
    assert "HideToTray" in window_source
    assert "Topmost = true" in window_adapter_source
    assert "IsSecuredContentVisible" in xaml_source
    assert "IsSecuredContentVisible" in view_model_source
    assert "DeviceId = deviceId" in grpc_source
    assert "response.Theme" in grpc_source
    assert "ApplyTheme" in host_source
    assert "ApplyHeartbeatConnectionState" in host_source
    assert "ApplyWorkstationTheme" in app_source
    assert "IsExpanded" in view_model_source
    assert "WindowModeActionLabel" in view_model_source
    assert "EnsureEntryAllowedAsync" in view_model_source
    assert "StartPortalSessionAsync" in view_model_source
    assert "LogoutAsync" in view_model_source
    assert "LoginGrantRemainingMinutes" in view_model_source
    assert "deviceId: DeviceId" in view_model_source
    assert "DeviceId = deviceId" in grpc_source
    assert (
        "request.device_id"
        in (
            PROJECT_ROOT
            / "backend"
            / "src"
            / "gameclub_backend"
            / "presentation"
            / "grpc"
            / "services.py"
        ).read_text()
    )
    assert "_clientPortal.Logout()" in view_model_source
    assert "FindUpcomingBooking" in view_model_source
    assert "ClientPortalBookingSelector" in view_model_source
    assert "PurchasePortalTariffAsync" in view_model_source
    assert "NextBooking" not in view_model_source
    assert "PurchaseEntitlementAsync" in grpc_source
    assert "PortalPassword" in view_model_source
    assert "PortalPhoneChanged" in window_source
    assert "Screens.ScreenFromWindow" in window_adapter_source
    assert 'Name="WindowContentSurface"' in xaml_source
    assert "ApplyWorkstationTheme" in app_source
    assert '"vip" => "VIP-зона"' in view_model_source
    assert "GAMECLUB_ENVIRONMENT" in deployment_source
    assert "EndpointPolicy.Validate" in deployment_source
    assert "HTTPS outside a private local network" in endpoint_policy_source
    assert "EndpointPolicy.Validate" in token_provider_source


def test_windows_support_check_is_reproducible_and_platform_explicit() -> None:
    """
    Проверяет сценарий «test_windows_support_check_is_reproducible_and_platform_explicit» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    script = (PROJECT_ROOT / "win-client" / "scripts" / "verify-windows.ps1").read_text()
    kiosk_script = (
        PROJECT_ROOT / "win-client" / "scripts" / "configure-windows-kiosk.ps1"
    ).read_text()

    assert "dotnet restore" in script
    assert "dotnet build" in script
    assert "RuntimeInformation" in script
    assert "обычным пользователем" in script
    assert "Перезапустить клиент" in script
    assert "стартует Locked" in script
    assert "manager password" in script
    assert "Assigned Access" in script
    resolved_executable_assignment = (
        "$resolvedExecutablePath = [System.IO.Path]::GetFullPath($ExecutablePath)"
    )
    assert resolved_executable_assignment in kiosk_script
    assert kiosk_script.index(resolved_executable_assignment) < kiosk_script.index(
        "if (-not $Apply)"
    )


def test_windows_access_gate_has_locked_start_and_manager_boundary() -> None:
    """
    Проверяет сценарий «test_windows_access_gate_has_locked_start_and_manager_boundary» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    project_root = PROJECT_ROOT / "win-client" / "src" / "GameClub.Client"
    coordinator = (project_root / "Application" / "AccessGateCoordinator.cs").read_text()
    view_model = (project_root / "Presentation" / "MainViewModel.cs").read_text()
    credentials = (
        project_root / "Infrastructure" / "EnvironmentAccessCredentialVerifier.cs"
    ).read_text()
    verifier = (project_root / "Infrastructure" / "PasswordHashVerifier.cs").read_text()
    coordinator_source = (project_root / "Application" / "AccessGateCoordinator.cs").read_text()
    window = (
        PROJECT_ROOT / "win-client" / "src" / "GameClub.Client.Avalonia" / "MainWindow.axaml"
    ).read_text()
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
    assert 'IsVisible="{Binding IsAccessGateVisible}"' in window
    assert "Assigned Access" in docs


def test_grpc_tls_configuration_remains_available_for_private_deployments() -> None:
    """
    Проверяет сценарий «test_grpc_tls_configuration_remains_available_for_private_deployments» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
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
    threat_model = (PROJECT_ROOT / "plans" / "04-auth-security" / "THREAT-MODEL.md").read_text()

    assert "grpc_tls_cert_file" in config_source
    assert "grpc_tls_key_file" in config_source
    assert "create_grpc_server_credentials" in server_source
    assert "A closed-club deployment may keep the backend on a private LAN" in server_source
    assert "`sub`" in threat_model
