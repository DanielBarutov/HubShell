using System.Reflection;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using GameClub.Client.Presentation;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class MainViewModelVisibilityTests
{
    [Fact]
    public async Task AccessGateStateIsPortableBooleanState()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        Assert.True(viewModel.IsAccessGateVisible);
        Assert.False(viewModel.IsSecuredContentVisible);
        Assert.True(viewModel.IsUserLoginVisible);
        Assert.False(viewModel.IsPortalRegistrationVisible);

        viewModel.ShowPortalRegistration();

        Assert.False(viewModel.IsUserLoginVisible);
        Assert.True(viewModel.IsPortalRegistrationVisible);
    }

    [Fact]
    public void EverySharedVisibilityPropertyIsBoolean()
    {
        var names = new[]
        {
            nameof(MainViewModel.IsAccessGateVisible),
            nameof(MainViewModel.IsSecuredContentVisible),
            nameof(MainViewModel.IsUserLoginVisible),
            nameof(MainViewModel.IsPortalRegistrationVisible),
            nameof(MainViewModel.IsManagerLoginVisible),
            nameof(MainViewModel.IsMaintenanceVisible),
            nameof(MainViewModel.IsManagerEntryVisible),
            nameof(MainViewModel.IsPortalContentVisible),
            nameof(MainViewModel.IsPortalPasswordSetupVisible),
            nameof(MainViewModel.IsPortalReadyVisible),
            nameof(MainViewModel.IsAccessFeedbackVisible),
            nameof(MainViewModel.IsTariffsVisible),
            nameof(MainViewModel.IsPortalBalanceTimeVisible),
            nameof(MainViewModel.IsUpcomingBookingVisible),
            nameof(MainViewModel.IsTransferPanelVisible),
            nameof(MainViewModel.IsTransferWaiting),
            nameof(MainViewModel.IsActiveSessionVisible),
            nameof(MainViewModel.IsTransferMessageVisible),
            nameof(MainViewModel.IsPortalNotificationVisible),
        };

        foreach (var name in names)
        {
            Assert.Equal(typeof(bool), typeof(MainViewModel).GetProperty(name)?.PropertyType);
        }
    }

    [Fact]
    public async Task ManagerMaintenanceStateHasNoUserPortalSideEffect()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        viewModel.ShowManagerLogin();

        Assert.True(viewModel.IsManagerLoginVisible);
        Assert.False(viewModel.IsMaintenanceVisible);
        Assert.False(viewModel.IsPortalContentVisible);

        viewModel.ManagerPassword = "manager-secret";

        Assert.True(viewModel.TryEnterMaintenance());
        Assert.True(viewModel.IsMaintenanceVisible);
        Assert.False(viewModel.IsPortalContentVisible);
    }

    [Fact]
    public async Task ManagerShortcutOpensPasswordPromptOnlyFromLockedGate()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        Assert.True(viewModel.TryOpenManagerLoginShortcut(true, true, true));
        Assert.True(viewModel.IsAccessLocked);
        Assert.True(viewModel.IsManagerLoginVisible);
        Assert.False(viewModel.IsMaintenanceVisible);

        viewModel.ManagerPassword = "partial-input";
        Assert.True(viewModel.TryOpenManagerLoginShortcut(true, true, true));
        Assert.Equal("partial-input", viewModel.ManagerPassword);

        viewModel.ManagerPassword = "manager-secret";

        Assert.True(viewModel.TryEnterMaintenance());
        Assert.True(viewModel.IsMaintenanceVisible);
        Assert.False(viewModel.IsPortalContentVisible);
    }

    [Fact]
    public async Task ManagerShortcutDoesNotOpenForOtherKeysOrAuthenticatedUser()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        Assert.False(viewModel.TryOpenManagerLoginShortcut(true, true, false));
        Assert.False(viewModel.IsManagerLoginVisible);

        viewModel.UserAccessCode = "4826";
        Assert.True(viewModel.TryUnlockUser());

        Assert.False(viewModel.TryOpenManagerLoginShortcut(true, true, true));
        Assert.False(viewModel.IsManagerLoginVisible);
        Assert.False(viewModel.IsMaintenanceVisible);
    }

    [Fact]
    public async Task ManagerShortcutDoesNotOpenBeforeWorkstationAssignment()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        viewModel.ApplyHeartbeatConnectionState(ClientConnectionState.WaitingForAssignment);

        Assert.False(viewModel.TryOpenManagerLoginShortcut(true, true, true));
        Assert.False(viewModel.IsManagerLoginVisible);
        Assert.True(viewModel.IsAccessLocked);
    }

    [Fact]
    public async Task LockedSystemShortcutsAreSuppressedOnlyAtTheAccessGate()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        Assert.True(viewModel.TrySuppressLockedSystemShortcut(true, true, false, false));
        Assert.True(viewModel.TrySuppressLockedSystemShortcut(false, false, true, true));

        viewModel.UserAccessCode = "4826";
        Assert.True(viewModel.TryUnlockUser());

        Assert.False(viewModel.TrySuppressLockedSystemShortcut(true, true, false, false));
        Assert.False(viewModel.TrySuppressLockedSystemShortcut(false, false, true, true));
    }

    [Fact]
    public async Task PortalLoginFailureShowsAccessFeedbackInsteadOfRawTransportDetails()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        viewModel.PortalIdentifier = "player_01";
        viewModel.PortalPassword = "password";

        var loggedIn = await viewModel.LoginPortalAsync();

        Assert.False(loggedIn);
        Assert.True(viewModel.IsAccessFeedbackVisible);
        Assert.Equal("Нет связи с сервером. Вход временно недоступен", viewModel.AccessMessage);
    }

    [Fact]
    public async Task SessionSummariesPrioritizeFreeGrantAndDoNotTreatPackageMeterAsPerMinute()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        viewModel.RegisterSessionStarted(new SessionSnapshot(
            "session-1",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            LoginGrantRemainingMinutes: 5,
            ActivePackage: new SessionPackageSnapshot(
                "package-1",
                "tariff-1",
                null,
                60,
                60,
                1,
                "active",
                0,
                0,
                null),
            Meter: new SessionMeterSnapshot(
                "session-1",
                0,
                0,
                0,
                null,
                "running",
                "2026-01-01T12:00:00Z")));

        Assert.Equal("Бесплатное время входа", viewModel.CurrentSessionModeSummary);
        Assert.Equal("Осталось 5 мин", viewModel.ActiveTimeSummary);

        viewModel.RegisterSessionStarted(new SessionSnapshot(
            "session-2",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            ActiveTariff: new SessionTariffSnapshot(
                "tariff-2",
                "Поминутный тариф",
                "per_minute",
                1,
                1,
                0,
                0,
                150,
                5),
            BalanceRemainingMinutes: 150));

        Assert.Equal("Поминутная игра", viewModel.CurrentSessionModeSummary);
        Assert.Contains("1,50 ₽/мин", viewModel.CurrentSessionTariffSummary);
        Assert.Contains("первые 5 мин бесплатно", viewModel.CurrentSessionTariffSummary);
        Assert.Equal("Осталось 2 ч 30 мин", viewModel.ActiveTimeSummary);

        viewModel.RegisterSessionStarted(new SessionSnapshot(
            "session-3",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            ActivePackage: new SessionPackageSnapshot(
                "package-2",
                "tariff-package",
                null,
                60,
                30,
                1,
                "active",
                0,
                0,
                null),
            BalanceRemainingMinutes: 120));

        Assert.Equal("Пакет времени", viewModel.CurrentSessionModeSummary);
        Assert.Equal("Осталось 30 мин", viewModel.ActiveTimeSummary);
    }

    [Fact]
    /// <summary>
    /// Проверяет, что ответ сервера на границе бесплатных минут показывает
    /// полный активный пакет, а следующий ответ — первую израсходованную минуту.
    /// </summary>
    public async Task PackageSnapshotsAfterFreeGrantShowPackageTimeInsteadOfMeteredTariffTime()
    {
        var clock = new DateTimeOffset(2026, 1, 1, 12, 5, 0, TimeSpan.Zero);
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials(),
            clock: () => clock);

        viewModel.RegisterSessionStarted(new SessionSnapshot(
            "session-1",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            LoginGrantRemainingMinutes: 0,
            ActivePackage: new SessionPackageSnapshot(
                "package-1",
                "tariff-package",
                "vip",
                300,
                300,
                1,
                "active",
                0,
                0,
                null),
            Meter: new SessionMeterSnapshot(
                "session-1",
                0,
                0,
                0,
                "package-1",
                "running",
                "2026-01-01T12:05:00Z"),
            ActiveTariff: new SessionTariffSnapshot(
                "tariff-package",
                "VIP package",
                "block",
                300,
                1,
                5,
                295)));

        Assert.Equal("Пакет времени", viewModel.CurrentSessionModeSummary);
        Assert.Equal("Осталось 5 ч 0 мин", viewModel.ActiveTimeSummary);
        Assert.Contains("300 мин", viewModel.CurrentSessionTariffSummary);

        clock = clock.AddMinutes(1);
        viewModel.RegisterSessionStarted(new SessionSnapshot(
            "session-1",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            LoginGrantRemainingMinutes: 0,
            ActivePackage: new SessionPackageSnapshot(
                "package-1",
                "tariff-package",
                "vip",
                300,
                299,
                1,
                "active",
                0,
                0,
                null),
            Meter: new SessionMeterSnapshot(
                "session-1",
                0,
                0,
                1,
                "package-1",
                "running",
                "2026-01-01T12:06:00Z"),
            ActiveTariff: new SessionTariffSnapshot(
                "tariff-package",
                "VIP package",
                "block",
                300,
                1,
                6,
                294)));

        Assert.Equal("Пакет времени", viewModel.CurrentSessionModeSummary);
        Assert.Equal("Осталось 4 ч 59 мин", viewModel.ActiveTimeSummary);
        Assert.Contains("299 мин", viewModel.CurrentSessionTariffSummary);
    }

    [Fact]
    /// <summary>
    /// Проверяет, что после пяти бесплатных минут Windows-клиент локально
    /// уменьшает трёхминутный пакет, даже когда heartbeat ещё передаёт старый остаток.
    /// </summary>
    public async Task LocalTimerCountsThreeMinutePackageAfterFreeGrantBetweenHeartbeats()
    {
        var clock = new DateTimeOffset(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials(),
            clock: () => clock);

        var freeGrant = SnapshotWithPackage(loginGrantMinutes: 5, packageMinutes: 3);
        viewModel.RegisterSessionStarted(freeGrant);
        Assert.Equal("Осталось 5 мин", viewModel.ActiveTimeSummary);

        clock = clock.AddMinutes(5);
        viewModel.ApplySessionSnapshotFromHeartbeat(
            SnapshotWithPackage(loginGrantMinutes: 0, packageMinutes: 3));
        Assert.Equal("Осталось 3 мин", viewModel.ActiveTimeSummary);

        clock = clock.AddMinutes(1);
        viewModel.ApplySessionSnapshotFromHeartbeat(
            SnapshotWithPackage(loginGrantMinutes: 0, packageMinutes: 3));
        Assert.Equal("Осталось 2 мин", viewModel.ActiveTimeSummary);

        clock = clock.AddMinutes(1);
        viewModel.ApplySessionSnapshotFromHeartbeat(
            SnapshotWithPackage(loginGrantMinutes: 0, packageMinutes: 3));
        Assert.Equal("Осталось 1 мин", viewModel.ActiveTimeSummary);

        clock = clock.AddMinutes(1);
        viewModel.ApplySessionSnapshotFromHeartbeat(
            SnapshotWithPackage(loginGrantMinutes: 0, packageMinutes: 2));
        Assert.Equal("Осталось 0 мин", viewModel.ActiveTimeSummary);
    }

    [Fact]
    /// <summary>
    /// Проверяет, что клиент показывает только активные и queued-пакеты,
    /// локализует их статусы и не предлагает ручную активацию при активном пакете.
    /// </summary>
    public async Task PortalEntitlementQueueHidesTerminalStatusesAndLocalizesVisibleStatuses()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials(),
            deviceId: "device-1");

        viewModel.SetDeviceIdentity("device-1", "workstation-1", "Main-01");
        var snapshot = new ClientPortalSnapshot(
            "client-1",
            "PackageFox",
            "+7 999 000-00-00",
            1_000,
            0,
            40,
            Array.Empty<ClientPortalBalanceOperation>(),
            Array.Empty<ClientPortalSession>(),
            Array.Empty<ClientPortalCharge>(),
            Array.Empty<ClientPortalPurchase>(),
            new[]
            {
                PortalEntitlement("active-1", "active", 1, "Дневной пакет", 20),
                PortalEntitlement("queued-1", "queued", 2, "Ночной пакет", 60),
                PortalEntitlement("exhausted-1", "exhausted", 3, "Старый пакет", 0),
                PortalEntitlement("burned-1", "burned", 4, "Сожжённый пакет", 0),
            },
            Array.Empty<ClientPortalTariff>(),
            Array.Empty<ClientPortalReservation>());
        var setter = typeof(MainViewModel).GetMethod(
            "SetPortalSnapshot",
            BindingFlags.Instance | BindingFlags.NonPublic);
        setter!.Invoke(viewModel, new object?[] { snapshot });

        Assert.Equal(
            new[]
            {
                "Дневной пакет · Активен · 20 из 60 мин",
                "Ночной пакет · В очереди · 60 из 60 мин",
            },
            viewModel.PortalEntitlementQueue);
        Assert.False(viewModel.CanActivatePortalEntitlement);
        Assert.False(viewModel.IsPortalBalanceTimeVisible);
    }

    [Fact]
    /// <summary>
    /// Проверяет, что выход сначала получает подтверждение остановки сессии
    /// от backend, а затем блокирует клиент и планирует перезапуск ПК.
    /// </summary>
    public async Task LogoutWaitsForServerStopBeforeApplyingRestartPolicy()
    {
        var events = new List<string>();
        var backend = DispatchProxy.Create<IBackendClient, StopRecordingBackendProxy>();
        var backendProxy = (StopRecordingBackendProxy)(object)backend;
        backendProxy.Events = events;
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(backend),
            new StubCredentials(),
            deviceId: "device-1",
            powerController: new RecordingPowerController(() => events.Add("restart")),
            sessionStoppedObserver: _ => events.Add("steam.release"));

        viewModel.ApplyLockdownPolicy(new WorkstationLockdownPolicySnapshot(
            "app_gate",
            ShellEnabled: true,
            UserSelfLoginEnabled: true,
            LockAfterSession: true,
            RestartAfterSession: true,
            HiddenDrives: Array.Empty<string>(),
            BlockExternalStorage: false,
            DisableStartMenu: false,
            DisableDesktopSwitching: false,
            BlockedWindowRules: Array.Empty<string>(),
            AllowedApplicationIds: Array.Empty<string>(),
            Version: 1));
        viewModel.RegisterSessionStarted(new SessionSnapshot(
            "session-1",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            DeviceId: "device-1"));

        Assert.True(await viewModel.LogoutAsync());
        Assert.Equal(1, backendProxy.StopCalls);
        Assert.Equal(1, events.Count(item => item == "restart"));
        Assert.Equal(1, events.Count(item => item == "steam.release"));
        Assert.True(viewModel.IsAccessLocked);
        Assert.True(events.IndexOf("backend.stop") < events.IndexOf("restart"));
        Assert.True(events.IndexOf("backend.stop") < events.IndexOf("steam.release"));
    }

    [Fact]
    /// <summary>
    /// Проверяет, что ошибка остановки сохраняет активную сессию и не запускает перезапуск ПК.
    /// </summary>
    public async Task StopFailureKeepsSessionAndDoesNotRestart()
    {
        var events = new List<string>();
        var backend = DispatchProxy.Create<IBackendClient, FailingStopBackendProxy>();
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(backend),
            new StubCredentials(),
            deviceId: "device-1",
            powerController: new RecordingPowerController(() => events.Add("restart")));

        viewModel.UserAccessCode = "4826";
        Assert.True(viewModel.TryUnlockUser());
        viewModel.RegisterSessionStarted(new SessionSnapshot(
            "session-1",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            DeviceId: "device-1"));

        Assert.False(await viewModel.StopActiveSessionAsync());
        Assert.True(viewModel.IsActiveSessionVisible);
        Assert.Equal("Не удалось завершить сессию. Проверьте связь и повторите выход.", viewModel.AccessMessage);
        Assert.Empty(events);
    }

    [Fact]
    public async Task WorkstationLabelUsesServerProvidedNameInsteadOfTechnicalIdentifier()
    {
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new StubCredentials());

        viewModel.SetDeviceIdentity("device-1", "b39315dd-eaf8-4ce5-966c-ffb8ab8b8d41");

        Assert.Equal("Игровое место", viewModel.CurrentWorkstationLabel);

        viewModel.SetDeviceIdentity(
            "device-1",
            "b39315dd-eaf8-4ce5-966c-ffb8ab8b8d41",
            "VIP-01");

        Assert.Equal("VIP-01", viewModel.CurrentWorkstationLabel);

        viewModel.ApplyWorkstationName("VIP-02");

        Assert.Equal("VIP-02", viewModel.CurrentWorkstationLabel);
    }

    private static IBackendClient CreateBackend() =>
        DispatchProxy.Create<IBackendClient, UnconfiguredBackendProxy>();

    private static SessionSnapshot SnapshotWithPackage(int loginGrantMinutes, int packageMinutes) =>
        new(
            "session-countdown",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            LoginGrantRemainingMinutes: loginGrantMinutes,
            ActivePackage: new SessionPackageSnapshot(
                "package-three-minutes",
                "tariff-three-minutes",
                null,
                3,
                packageMinutes,
                1,
                "active",
                0,
                0,
                null));

    private static ClientPortalEntitlement PortalEntitlement(
        string id,
        string status,
        int queuePosition,
        string tariffName,
        int remainingMinutes) =>
        new(
            id,
            $"tariff-{id}",
            "main",
            status,
            60,
            remainingMinutes,
            1_000,
            queuePosition,
            tariffName,
            "2026-01-01T12:00:00Z",
            status == "active" ? "2026-01-01T12:01:00Z" : null,
            false,
            null,
            null,
            null,
            null,
            null,
            "all");

    private class UnconfiguredBackendProxy : DispatchProxy
    {
        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod?.ReturnType == typeof(ValueTask))
            {
                return ValueTask.CompletedTask;
            }

            throw new NotSupportedException($"Unexpected backend call: {targetMethod?.Name}");
        }
    }

    private sealed class StubCredentials : IAccessCredentialVerifier
    {
        public bool IsUserAccessConfigured => true;

        public bool IsManagerAccessConfigured => true;

        public bool VerifyUserAccess(string accessCode) => accessCode == "4826";

        public bool VerifyManagerPassword(string password) => password == "manager-secret";

        public void UpdateManagerPasswordVerifier(string verifier)
        {
        }
    }

    private sealed class RecordingPowerController : IWorkstationPowerController
    {
        private readonly Action _onRestart;

        public RecordingPowerController(Action onRestart) => _onRestart = onRestart;

        public CommandExecutionResult ScheduleRestart()
        {
            _onRestart();
            return new CommandExecutionResult(true, "restart scheduled");
        }
    }

    private class StopRecordingBackendProxy : DispatchProxy
    {
        public List<string> Events { get; set; } = [];

        public int StopCalls { get; private set; }

        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod?.Name == nameof(IWorkstationSessionGateway.StopSessionAsync))
            {
                StopCalls++;
                Events.Add("backend.stop");
                return Task.FromResult(new SessionSnapshot(
                    "session-1",
                    "workstation-1",
                    null,
                    null,
                    "completed",
                    "2026-01-01T12:00:00Z",
                    "2026-01-01T12:02:00Z",
                    "device",
                    string.Empty,
                    DeviceId: "device-1"));
            }

            if (targetMethod?.Name == nameof(IClientPortalGateway.Logout))
            {
                return null;
            }

            if (targetMethod?.ReturnType == typeof(ValueTask))
            {
                return ValueTask.CompletedTask;
            }

            throw new NotSupportedException($"Unexpected backend call: {targetMethod?.Name}");
        }
    }

    private class FailingStopBackendProxy : DispatchProxy
    {
        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod?.Name == nameof(IWorkstationSessionGateway.StopSessionAsync))
            {
                return Task.FromException<SessionSnapshot>(new InvalidOperationException("backend unavailable"));
            }

            if (targetMethod?.Name == nameof(IClientPortalGateway.Logout))
            {
                return null;
            }

            if (targetMethod?.ReturnType == typeof(ValueTask))
            {
                return ValueTask.CompletedTask;
            }

            throw new NotSupportedException($"Unexpected backend call: {targetMethod?.Name}");
        }
    }
}
