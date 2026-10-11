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
        var gateway = new V2Gateway(CreateLedger());
        var v2Login = new V2OfflineLoginCoordinator(gateway, ledger);
        var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: "device-01",
            clock: () => DateTimeOffset.Parse("2026-09-28T10:00:20Z"),
            v2OfflineLogin: v2Login,
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier(),
            v2OfflineSession: gateway);
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
        Assert.Equal(
            [("device-01", "00000000-0000-0000-0000-000000000002", "00000000-0000-0000-0000-000000000001")],
            gateway.StoppedSessions);
    }

    [Fact]
    public async Task V2LoginRetriesServerStopForPreviouslyStoppedLocalLedger()
    {
        var previous = V2LocalLedgerEngine.StopEarly(
            CreateLedger(),
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        await ledger.InitializeAsync(previous.Ledger);
        await store.WriteAsync(new V2LocalLedgerStorageSnapshot(
            previous.Ledger,
            previous.OutboxFacts,
            Array.Empty<V2ClientInboxEntry>()));
        var next = CreateLedger() with
        {
            SnapshotId = Guid.NewGuid(),
            SessionId = Guid.NewGuid(),
        };
        var gateway = new V2Gateway(next, stopFailuresRemaining: 1);
        var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: "device-01",
            v2OfflineLogin: new V2OfflineLoginCoordinator(gateway, ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier(),
            v2OfflineSession: gateway);
        await using var disposable = viewModel;
        viewModel.ApplyHeartbeatConnectionState(ClientConnectionState.Online);
        viewModel.PortalIdentifier = "NightFox";
        viewModel.PortalPassword = "safe-password";

        Assert.True(await viewModel.LoginPortalAsync());

        Assert.Equal(2, gateway.StoppedSessions.Count);
        Assert.Equal(next.SessionId, (await ledger.ReadLedgerAsync()).SessionId);
        Assert.Equal(previous.OutboxFacts, await ledger.ReadPendingOutboxAsync());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AccountLoginAfterStoppedGuestUsesGuestStopAndPreservesServerDenial(bool denyStop)
    {
        var previous = V2LocalLedgerEngine.StopEarly(
            CreateLedger() with { ClientId = Guid.Empty, GuestName = "Гость", GuestPaymentId = Guid.NewGuid() },
            Guid.NewGuid(), DateTimeOffset.UtcNow);
        var ledger = new V2LocalLedgerCoordinator(new InMemoryLedgerStore());
        await ledger.InitializeAsync(previous.Ledger);
        var next = CreateLedger() with { SessionId = Guid.NewGuid(), SnapshotId = Guid.NewGuid() };
        var account = new V2Gateway(next);
        var guest = new GuestStopGateway(denyStop);
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()), new Credentials(), deviceId: "device-01",
            v2OfflineLogin: new V2OfflineLoginCoordinator(account, ledger), v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger), v2SignatureVerifier: new AcceptingVerifier(),
            v2OfflineSession: account, v2GuestSession: guest);
        viewModel.ApplyHeartbeatConnectionState(ClientConnectionState.Online);
        viewModel.PortalIdentifier = "NightFox";
        viewModel.PortalPassword = "safe-password";

        Assert.Equal(!denyStop, await viewModel.LoginPortalAsync());
        Assert.Empty(account.StoppedSessions);
        Assert.Equal(("device-01", previous.Ledger.SessionId.ToString(), previous.Ledger.GuestPaymentId!.Value.ToString()), guest.Stopped);
        Assert.Equal(denyStop ? previous.Ledger.SessionId : next.SessionId, (await ledger.ReadLedgerAsync()).SessionId);
    }

    private sealed class GuestStopGateway(bool denyStop) : IV2GuestSessionGateway
    {
        public (string DeviceId, string SessionId, string PaymentId)? Stopped { get; private set; }
        public Task<V2LocalSessionLedger?> RedeemPendingGuestAccessAsync(
            string deviceId, IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default, V2LocalSessionLedger? activeGuestLedger = null)
            => Task.FromResult<V2LocalSessionLedger?>(null);
        public Task StopGuestSessionAsync(string deviceId, string sessionId, string paymentId,
            CancellationToken cancellationToken = default)
        {
            Stopped = (deviceId, sessionId, paymentId);
            if (denyStop)
                throw new RpcException(new Status(StatusCode.PermissionDenied, "guest stop denied"));
            return Task.CompletedTask;
        }
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
    public async Task GuestRecoveryAndRefreshDoNotUseTheAccountPortal()
    {
        // Проверяет восстановление гостевого ledger без кабинета и клиентского счёта.
        var saved = CreateLedger() with
        {
            ClientId = Guid.Empty,
            GuestName = "Гость",
            GuestPaymentId = Guid.Parse("00000000-0000-0000-0000-000000000004"),
        };
        var ledger = new V2LocalLedgerCoordinator(new InMemoryLedgerStore());
        await ledger.InitializeAsync(saved);
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: saved.DeviceId,
            v2OfflineLogin: new V2OfflineLoginCoordinator(new V2Gateway(saved), ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier(),
            v2ClientPortal: new CompletedSessionPortal(saved));

        await viewModel.RecoverV2SessionAsync(new V2LocalLedgerRecoveryCoordinator(ledger));
        await viewModel.RefreshPortalAsync();

        Assert.False(viewModel.IsAccessLocked);
        Assert.True(viewModel.IsActiveSessionVisible);
        Assert.Equal(saved, await ledger.ReadLedgerAsync());
    }

    [Fact]
    public async Task V2CurrentPackageSummaryShowsTariffNameInsteadOfTariffId()
    {
        const string tariffId = "9064b0b0-dac8-49dd-aaf6-d06a7a21e2b4";
        var ledgerSnapshot = CreateLedger(
            loginGrantMinutes: 0,
            packages:
            [
                new V2LocalPackage(
                    "package-1",
                    tariffId,
                    null,
                    3,
                    V2LocalPackageStatus.Active),
            ],
            tariffs:
            [
                new V2LocalTariff(tariffId, "Ночной тест", null, 660, 30_000, 0, true),
            ]);
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: "device-01",
            v2OfflineLogin: new V2OfflineLoginCoordinator(
                new V2Gateway(ledgerSnapshot),
                ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier());
        await using var disposable = viewModel;
        viewModel.ApplyHeartbeatConnectionState(ClientConnectionState.Online);
        viewModel.PortalIdentifier = "NightFox";
        viewModel.PortalPassword = "safe-password";

        Assert.True(await viewModel.LoginPortalAsync());

        Assert.Contains("Ночной тест", viewModel.CurrentSessionTariffSummary);
        Assert.DoesNotContain(tariffId, viewModel.CurrentSessionTariffSummary);
    }

    [Fact]
    public async Task FailedServerStopPersistenceKeepsLedgerForRetryAndStopsMinuteBilling()
    {
        var saved = CreateLedger();
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        await ledger.InitializeAsync(saved);
        store.FailNextWrite = true;
        var portal = new CompletedSessionPortal(saved);
        var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: saved.DeviceId,
            v2OfflineLogin: new V2OfflineLoginCoordinator(new V2Gateway(saved), ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier(),
            v2ClientPortal: portal);
        await using var disposable = viewModel;

        await viewModel.RecoverV2SessionAsync(new V2LocalLedgerRecoveryCoordinator(ledger));
        Assert.True(viewModel.IsSessionLocked);
        Assert.True(viewModel.IsActiveSessionVisible);
        Assert.Equal(V2LocalSessionStatus.Active, (await ledger.ReadLedgerAsync()).Status);

        await viewModel.RefreshPortalAsync();

        Assert.True(viewModel.IsSessionLocked);
        Assert.False(viewModel.IsActiveSessionVisible);
        Assert.Equal(V2LocalSessionStatus.Stopped, (await ledger.ReadLedgerAsync()).Status);
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

    private static V2LocalSessionLedger CreateLedger(
        int loginGrantMinutes = 5,
        IReadOnlyList<V2LocalPackage>? packages = null,
        IReadOnlyList<V2LocalTariff>? tariffs = null) =>
        V2LocalSessionLedger.Create(
            snapshotVersion: 1,
            clientId: Guid.Parse("00000000-0000-0000-0000-000000000001"),
            sessionId: Guid.Parse("00000000-0000-0000-0000-000000000002"),
            deviceId: "device-01",
            zoneId: null,
            balanceCents: 1_000,
            debtLimitCents: 0,
            loginGrantRemainingMinutes: loginGrantMinutes,
            packages: packages ?? Array.Empty<V2LocalPackage>(),
            tariffs: tariffs ?? Array.Empty<V2LocalTariff>(),
            snapshotId: Guid.Parse("00000000-0000-0000-0000-000000000003"),
            activatedAtUtc: DateTimeOffset.Parse("2026-09-28T10:00:20Z"));

    private sealed class V2Gateway(
        V2LocalSessionLedger ledger,
        int stopFailuresRemaining = 0) : IV2OfflineSessionGateway
    {
        private int _stopFailuresRemaining = stopFailuresRemaining;

        public List<(string DeviceId, string SessionId, string ClientId)> StoppedSessions { get; } = [];

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

        public Task StopSessionAsync(
            string deviceId,
            string sessionId,
            string clientId,
            CancellationToken cancellationToken = default)
        {
            StoppedSessions.Add((deviceId, sessionId, clientId));
            if (_stopFailuresRemaining-- > 0)
            {
                throw new RpcException(new Status(StatusCode.Unavailable, "temporarily unavailable"));
            }
            return Task.CompletedTask;
        }
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

        public Task StopSessionAsync(
            string deviceId,
            string sessionId,
            string clientId,
            CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class InMemoryLedgerStore : IV2LocalLedgerStore
    {
        private V2LocalLedgerStorageSnapshot? _snapshot;
        public bool FailNextWrite { get; set; }

        public Task<V2LocalLedgerStorageSnapshot?> ReadAsync(
            CancellationToken cancellationToken = default) => Task.FromResult(_snapshot);

        public Task WriteAsync(
            V2LocalLedgerStorageSnapshot snapshot,
            CancellationToken cancellationToken = default)
        {
            if (FailNextWrite)
            {
                FailNextWrite = false;
                throw new IOException("Simulated ledger write failure");
            }
            _snapshot = snapshot;
            return Task.CompletedTask;
        }
    }

    private sealed class CompletedSessionPortal(V2LocalSessionLedger ledger) : IV2ClientPortalGateway
    {
        private ClientPortalSnapshot CreateSnapshot() => new(
            ledger.ClientId.ToString(),
            "NightFox",
            "79990000000",
            ledger.BalanceCents,
            0,
            0,
            Array.Empty<ClientPortalBalanceOperation>(),
            [
                new ClientPortalSession(
                    ledger.SessionId.ToString(),
                    "workstation-01",
                    "completed",
                    "2026-09-28T09:00:00Z",
                    "2026-09-28T09:15:00Z",
                    null,
                    null,
                    1),
            ],
            Array.Empty<ClientPortalCharge>(),
            Array.Empty<ClientPortalPurchase>(),
            Array.Empty<ClientPortalEntitlement>(),
            Array.Empty<ClientPortalTariff>(),
            Array.Empty<ClientPortalReservation>());

        public Task<ClientPortalSnapshot> ResumePortalAsync(
            string deviceId,
            string sessionId,
            string clientId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(CreateSnapshot());

        public Task<ClientPortalSnapshot> RefreshAsync(
            string deviceId,
            int limit = 50,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(CreateSnapshot());

        public Task<ClientPortalSnapshot> ActivateEntitlementAsync(
            string deviceId,
            string entitlementId,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<ClientPortalSnapshot> PurchaseEntitlementAsync(
            string deviceId,
            string tariffId,
            string idempotencyKey,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();
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
