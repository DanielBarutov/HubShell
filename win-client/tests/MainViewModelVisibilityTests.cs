using System.Reflection;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
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
            nameof(MainViewModel.IsTariffsVisible),
            nameof(MainViewModel.IsUpcomingBookingVisible),
            nameof(MainViewModel.IsTransferPanelVisible),
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
