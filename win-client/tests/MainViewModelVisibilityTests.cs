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
                5)));

        Assert.Equal("Поминутная игра", viewModel.CurrentSessionModeSummary);
        Assert.Contains("1,50 ₽/мин", viewModel.CurrentSessionTariffSummary);
        Assert.Contains("первые 5 мин бесплатно", viewModel.CurrentSessionTariffSummary);
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
}
