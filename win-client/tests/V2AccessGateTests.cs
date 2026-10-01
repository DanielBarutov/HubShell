using System.Reflection;
using Grpc.Core;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using GameClub.Client.Presentation;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class V2AccessGateTests
{
    [Fact]
    public async Task V2LoginAndStopUseOnlyLocalLedgerInsteadOfV1SessionGateway()
    {
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        var v2Login = new V2OfflineLoginCoordinator(
            new V2Gateway(CreateLedger()),
            ledger);
        var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: "device-01",
            clock: () => DateTimeOffset.Parse("2026-09-28T10:00:20Z"),
            v2OfflineLogin: v2Login,
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier());
        await using var disposable = viewModel;
        viewModel.ApplyHeartbeatConnectionState(ClientConnectionState.Online);
        viewModel.PortalIdentifier = "NightFox";
        viewModel.PortalPassword = "safe-password";

        Assert.True(await viewModel.LoginPortalAsync());
        Assert.True(viewModel.IsActiveSessionVisible);
        Assert.False(viewModel.IsAccessLocked);
        Assert.Equal("Бесплатное время входа", viewModel.CurrentSessionModeSummary);

        Assert.True(await viewModel.StopActiveSessionAsync());

        Assert.True(viewModel.IsSessionLocked);
        Assert.False(viewModel.IsActiveSessionVisible);
        Assert.Equal(V2LocalSessionStatus.Stopped, (await ledger.ReadLedgerAsync()).Status);
        Assert.NotEmpty(await ledger.ReadPendingOutboxAsync());
    }

    [Fact]
    public async Task V2HostRecoveryReopensOnlyTheDurableActiveLedgerForThisDevice()
    {
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        var saved = CreateLedger();
        await ledger.InitializeAsync(saved);
        var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: saved.DeviceId,
            v2OfflineLogin: new V2OfflineLoginCoordinator(new V2Gateway(saved), ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier());
        await using var disposable = viewModel;
        var recovery = new V2LocalLedgerRecoveryCoordinator(ledger);

        await viewModel.RecoverV2SessionAsync(recovery);

        Assert.False(viewModel.IsAccessLocked);
        Assert.True(viewModel.IsActiveSessionVisible);
        Assert.Equal("Бесплатное время входа", viewModel.CurrentSessionModeSummary);
    }

    [Fact]
    public async Task V2PasswordResetShowsValidationAndOpensSessionAfterSuccessfulChange()
    {
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        var gateway = new ResetV2Gateway(CreateLedger());
        var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: "device-01",
            v2OfflineLogin: new V2OfflineLoginCoordinator(gateway, ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier());
        await using var disposable = viewModel;
        viewModel.ApplyHeartbeatConnectionState(ClientConnectionState.Online);
        viewModel.PortalIdentifier = "NightFox";
        viewModel.PortalPassword = string.Empty;

        Assert.True(await viewModel.LoginPortalAsync());
        Assert.True(viewModel.IsPortalPasswordResetRequired);

        viewModel.PortalPasswordSetup = "new-password";
        viewModel.PortalPasswordSetupConfirmation = "different-password";
        Assert.False(await viewModel.SetPortalPasswordAsync());
        Assert.Contains("Пароли не совпадают", viewModel.AccessMessage);
        Assert.Null(gateway.NewPassword);

        viewModel.PortalPasswordSetupConfirmation = "new-password";
        Assert.True(await viewModel.SetPortalPasswordAsync());
        Assert.Equal("new-password", gateway.NewPassword);
        Assert.False(viewModel.IsPortalPasswordResetRequired);
        Assert.True(viewModel.IsActiveSessionVisible);
    }

    [Fact]
    public async Task V2PasswordResetReturnsToLoginWhenAutomaticLoginFails()
    {
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        var gateway = new ResetV2Gateway(CreateLedger(), failAfterReset: true);
        var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: "device-01",
            v2OfflineLogin: new V2OfflineLoginCoordinator(gateway, ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier());
        await using var disposable = viewModel;
        viewModel.ApplyHeartbeatConnectionState(ClientConnectionState.Online);
        viewModel.PortalIdentifier = "NightFox";
        viewModel.PortalPassword = string.Empty;

        Assert.True(await viewModel.LoginPortalAsync());
        viewModel.PortalPasswordSetup = "new-password";
        viewModel.PortalPasswordSetupConfirmation = "new-password";

        Assert.False(await viewModel.SetPortalPasswordAsync());
        Assert.False(viewModel.IsPortalPasswordResetRequired);
        Assert.True(viewModel.IsAccessLocked);
        Assert.Contains("Пароль сохранён", viewModel.AccessMessage);
    }

    private static IBackendClient CreateBackend() =>
        DispatchProxy.Create<IBackendClient, V1MustNotBeCalledBackend>();

    private static V2LocalSessionLedger CreateLedger() =>
        V2LocalSessionLedger.Create(
            snapshotVersion: 1,
            clientId: Guid.Parse("00000000-0000-0000-0000-000000000001"),
            sessionId: Guid.Parse("00000000-0000-0000-0000-000000000002"),
            deviceId: "device-01",
            zoneId: null,
            balanceCents: 1_000,
            debtLimitCents: 0,
            loginGrantRemainingMinutes: 5,
            packages: Array.Empty<V2LocalPackage>(),
            tariffs: Array.Empty<V2LocalTariff>(),
            snapshotId: Guid.Parse("00000000-0000-0000-0000-000000000003"),
            activatedAtUtc: DateTimeOffset.Parse("2026-09-28T10:00:20Z"));

    private sealed class V2Gateway(V2LocalSessionLedger ledger) : IV2OfflineSessionGateway
    {
        public Task<V2OfflineLoginResult> LoginAsync(
            string identifier,
            string password,
            string deviceId,
            string idempotencyKey,
            IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default) => Task.FromResult(
                new V2OfflineLoginResult(ledger, false, null));

        public Task<V2OfflineLoginResult> RegisterAsync(
            string nickname,
            string phone,
            string password,
            string deviceId,
            string idempotencyKey,
            IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default) => Task.FromResult(
                new V2OfflineLoginResult(ledger, false, null));

        public Task ChangePasswordAsync(
            string newPassword,
            string deviceId,
            string resetToken,
            CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class ResetV2Gateway(
        V2LocalSessionLedger ledger,
        bool failAfterReset = false) : IV2OfflineSessionGateway
    {
        private int _loginCount;

        public string? NewPassword { get; private set; }

        public Task<V2OfflineLoginResult> LoginAsync(
            string identifier,
            string password,
            string deviceId,
            string idempotencyKey,
            IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default)
        {
            _ = identifier;
            _ = password;
            _ = deviceId;
            _ = idempotencyKey;
            _ = signatureVerifier;
            _ = cancellationToken;
            if (_loginCount++ == 0)
            {
                return Task.FromResult(new V2OfflineLoginResult(null, true, "reset-token"));
            }
            if (failAfterReset)
            {
                throw new RpcException(new Status(StatusCode.Unauthenticated, "Invalid credentials"));
            }
            return Task.FromResult(new V2OfflineLoginResult(ledger, false, null));
        }

        public Task<V2OfflineLoginResult> RegisterAsync(
            string nickname,
            string phone,
            string password,
            string deviceId,
            string idempotencyKey,
            IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new V2OfflineLoginResult(ledger, false, null));

        public Task ChangePasswordAsync(
            string newPassword,
            string deviceId,
            string resetToken,
            CancellationToken cancellationToken = default)
        {
            Assert.Equal("device-01", deviceId);
            Assert.Equal("reset-token", resetToken);
            NewPassword = newPassword;
            return Task.CompletedTask;
        }
    }

    private sealed class InMemoryLedgerStore : IV2LocalLedgerStore
    {
        private V2LocalLedgerStorageSnapshot? _snapshot;

        public Task<V2LocalLedgerStorageSnapshot?> ReadAsync(
            CancellationToken cancellationToken = default) => Task.FromResult(_snapshot);

        public Task WriteAsync(
            V2LocalLedgerStorageSnapshot snapshot,
            CancellationToken cancellationToken = default)
        {
            _snapshot = snapshot;
            return Task.CompletedTask;
        }
    }

    private sealed class AcceptingVerifier : IOfflineSnapshotSignatureVerifier
    {
        public bool Verify(string signingKeyId, ReadOnlyMemory<byte> payload, ReadOnlyMemory<byte> signature) => true;
    }

    private sealed class Credentials : IAccessCredentialVerifier
    {
        public bool IsUserAccessConfigured => true;
        public bool IsManagerAccessConfigured => true;
        public bool VerifyUserAccess(string accessCode) => true;
        public bool VerifyManagerPassword(string password) => true;
        public void UpdateManagerPasswordVerifier(string verifier) { }
    }

    private class V1MustNotBeCalledBackend : DispatchProxy
    {
        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod?.ReturnType == typeof(ValueTask))
            {
                return ValueTask.CompletedTask;
            }
            throw new InvalidOperationException($"V1 backend must not be called: {targetMethod?.Name}");
        }
    }
}
