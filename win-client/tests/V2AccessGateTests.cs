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
    public async Task MinuteBonusToggleCancelsLostEnableAndRefreshNeverReenablesIt()
    {
        var saved = CreateLedger(loginGrantMinutes: 0,
            tariffs: [new("minute", "Minute", null, 0, 0, 100, false, true)]) with { BalanceCents = 1000 };
        var coordinator = new V2LocalLedgerCoordinator(new InMemoryLedgerStore());
        await coordinator.InitializeAsync(saved);
        var portal = new MinuteBonusPortal(saved);
        await using var vm = new MainViewModel(new ClientSessionCoordinator(CreateBackend()), new Credentials(), deviceId: saved.DeviceId,
            v2OfflineLogin: new V2OfflineLoginCoordinator(new V2Gateway(saved), coordinator), v2Ledger: coordinator,
            v2MinuteRunner: new V2MinuteLedgerRunner(coordinator),
            v2SignatureVerifier: new AcceptingVerifier(), v2ClientPortal: portal);
        await vm.RecoverV2SessionAsync(new V2LocalLedgerRecoveryCoordinator(coordinator));
        Assert.True(vm.IsMinuteBonusVisible);
        Assert.False(vm.IsMinuteBonusSelected);
        Assert.Equal(100, (await vm.QuoteMinuteBonusAsync())!.PriceCents);
        Assert.Equal(0, portal.EnableCalls);
        await vm.SetMinuteBonusAsync(true);
        Assert.True(vm.IsMinuteBonusSelected);
        Assert.Contains("ожидает", vm.MinuteBonusStatus);
        Assert.Null((await coordinator.ReadLedgerAsync())!.MinuteBonus);
        await vm.SetMinuteBonusAsync(false);
        Assert.False(vm.IsMinuteBonusSelected);
        Assert.True((await coordinator.ReadPendingMinuteBonusAsync()).CancellationPending);
        await vm.RefreshPortalAsync();
        Assert.Null((await coordinator.ReadPendingMinuteBonusAsync()).Request);
        Assert.Equal(1, portal.EnableCalls);
        Assert.False(vm.IsMinuteBonusSelected);
        await vm.SetMinuteBonusAsync(true);
        Assert.True((await coordinator.ReadLedgerAsync())!.MinuteBonus!.Enabled);
        await vm.SetMinuteBonusAsync(false);
        Assert.False(vm.IsMinuteBonusSelected);
    }

    [Fact]
    public async Task PortalRefreshIncreasesReserveOnlyWhileBonusPaymentIsEnabled()
    {
        var saved = CreateLedger(loginGrantMinutes: 0,
            tariffs: [new("minute", "Minute", null, 0, 0, 100, false, true)]) with { BalanceCents = 1000 };
        var coordinator = new V2LocalLedgerCoordinator(new InMemoryLedgerStore());
        await coordinator.InitializeAsync(saved);
        var portal = new MinuteBonusPortal(saved) { LoseFirstResponse = false };
        await using var vm = new MainViewModel(new ClientSessionCoordinator(CreateBackend()), new Credentials(), deviceId: saved.DeviceId,
            v2OfflineLogin: new V2OfflineLoginCoordinator(new V2Gateway(saved), coordinator), v2Ledger: coordinator,
            v2MinuteRunner: new V2MinuteLedgerRunner(coordinator),
            v2SignatureVerifier: new AcceptingVerifier(), v2ClientPortal: portal);
        await vm.RecoverV2SessionAsync(new V2LocalLedgerRecoveryCoordinator(coordinator));
        portal.AvailableBonusCents = 100;
        await vm.RefreshPortalAsync();
        Assert.Equal(0, portal.EnableCalls);
        await vm.SetMinuteBonusAsync(true);
        Assert.Equal(1, portal.EnableCalls);
        await vm.RefreshPortalAsync();
        Assert.Equal(2, portal.EnableCalls);
        Assert.True(vm.IsMinuteBonusSelected);
        portal.AvailableBonusCents = 0;
        await vm.RefreshPortalAsync();
        Assert.Equal(2, portal.EnableCalls);
        await vm.SetMinuteBonusAsync(false);
        portal.AvailableBonusCents = 100;
        await vm.RefreshPortalAsync();
        Assert.Equal(2, portal.EnableCalls);
        Assert.False(vm.IsMinuteBonusSelected);
    }

    private sealed class MinuteBonusPortal(V2LocalSessionLedger ledger) : IV2ClientPortalGateway
    {
        public int EnableCalls { get; private set; }
        public long AvailableBonusCents { get; set; }
        public bool LoseFirstResponse { get; set; } = true;
        private int _cancelCalls;
        private ClientPortalSnapshot Snapshot() => new(ledger.ClientId.ToString(), "Test", "", ledger.BalanceCents,
            0, 0, [], [], [], [], [], [], [], BonusWallet: new(AvailableBonusCents, AvailableBonusCents, 0, 0));
        public Task<ClientPortalSnapshot> ResumePortalAsync(string deviceId, string sessionId, string clientId, CancellationToken cancellationToken = default) => Task.FromResult(Snapshot());
        public Task<ClientPortalSnapshot> RefreshAsync(string deviceId, int limit = 50, CancellationToken cancellationToken = default) => Task.FromResult(Snapshot());
        public Task<ClientPortalSnapshot> ActivateEntitlementAsync(string deviceId, string entitlementId, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<ClientPortalSnapshot> PurchaseEntitlementAsync(string deviceId, string tariffId, string idempotencyKey, IOfflineSnapshotSignatureVerifier signatureVerifier, CancellationToken cancellationToken = default, BonusPurchaseConfirmation? bonusConfirmation = null) => throw new NotSupportedException();
        public Task<BonusGameQuote> QuoteEntitlementAsync(string deviceId, string tariffId, bool useBonus, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<BonusGameQuote> QuoteMinuteBonusAsync(V2MinuteBonusRequest request, CancellationToken cancellationToken = default) => Task.FromResult(new BonusGameQuote(100, 20, 80, 4, 500, 2000, 1000, 0, true, true));
        public Task<V2MinuteBonusGrant> EnableMinuteBonusAsync(V2MinuteBonusRequest request, IOfflineSnapshotSignatureVerifier signatureVerifier, CancellationToken cancellationToken = default)
        {
            EnableCalls++;
            return LoseFirstResponse && EnableCalls == 1 ? Task.FromException<V2MinuteBonusGrant>(new RpcException(new Status(StatusCode.Unavailable, "lost")))
                : Task.FromResult(new V2MinuteBonusGrant(Guid.NewGuid(), EnableCalls, request, 1000, 2000));
        }
        public Task CancelMinuteBonusAsync(V2MinuteBonusRequest request, CancellationToken cancellationToken = default) =>
            ++_cancelCalls == 1 ? Task.FromException(new RpcException(new Status(StatusCode.Unavailable, "offline"))) : Task.CompletedTask;
    }

    [Fact]
    public async Task OfflineMinuteUpdatesDisplayedNegativeBalanceFromLocalLedger()
    {
        var now = DateTimeOffset.Parse("2026-10-12T12:00:00Z");
        var saved = CreateLedger(loginGrantMinutes: 0,
            tariffs: [new("minute", "Minute", null, 0, 0, 100, false)]) with
        {
            BalanceCents = -500, DebtLimitCents = 1_000, ActivatedAtUtc = now,
        };
        var coordinator = new V2LocalLedgerCoordinator(new InMemoryLedgerStore());
        await coordinator.InitializeAsync(saved);
        var viewModel = new MainViewModel(new ClientSessionCoordinator(CreateBackend()),
            new Credentials(), deviceId: saved.DeviceId, clock: () => now,
            v2OfflineLogin: new V2OfflineLoginCoordinator(new V2Gateway(saved), coordinator),
            v2Ledger: coordinator, v2MinuteRunner: new V2MinuteLedgerRunner(coordinator),
            v2SignatureVerifier: new AcceptingVerifier());
        await viewModel.RecoverV2SessionAsync(new V2LocalLedgerRecoveryCoordinator(coordinator));
        Assert.Equal("-5,00 ₽", viewModel.PortalBalanceAmountSummary);
        var changes = new List<string?>();
        var balanceUpdated = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        viewModel.PropertyChanged += (_, args) =>
        {
            changes.Add(args.PropertyName);
            if (args.PropertyName == nameof(viewModel.PortalBalanceAmountSummary)
                && viewModel.PortalBalanceAmountSummary == "-6,00 ₽")
            {
                balanceUpdated.TrySetResult();
            }
        };
        now = now.AddMinutes(1);
        var countdown = viewModel.RunSessionCountdownLoopAsync();
        try
        {
            await balanceUpdated.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(-600, (await coordinator.ReadLedgerAsync()).BalanceCents);
            Assert.Equal("-6,00 ₽", viewModel.PortalBalanceAmountSummary);
            Assert.Contains(nameof(viewModel.PortalBalanceAmountSummary), changes);
            Assert.False(viewModel.HasPortalBalance);
        }
        finally
        {
            await viewModel.DisposeAsync();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => countdown);
        }
    }

    [Fact]
    public async Task MinuteWriteFailureKeepsSessionAvailableForExplicitStop()
    {
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        var gateway = new V2Gateway(CreateLedger());
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()), new Credentials(), deviceId: "device-01",
            clock: () => DateTimeOffset.Parse("2026-09-28T10:01:20Z"),
            v2OfflineLogin: new V2OfflineLoginCoordinator(gateway, ledger), v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier(), v2OfflineSession: gateway);
        viewModel.ApplyHeartbeatConnectionState(ClientConnectionState.Online);
        viewModel.PortalIdentifier = "NightFox";
        viewModel.PortalPassword = "safe-password";
        Assert.True(await viewModel.LoginPortalAsync());
        store.FailNextWrite = true;

        var consume = typeof(MainViewModel).GetMethod("ConsumeV2DueMinutesAsync", BindingFlags.Instance | BindingFlags.NonPublic)!;
        await (Task)consume.Invoke(viewModel, [])!;

        Assert.True(viewModel.IsSessionLocked);
        Assert.True(viewModel.IsActiveSessionVisible);
        Assert.True(viewModel.CanStopActiveSession);
        Assert.Equal(V2LocalSessionStatus.Active, (await ledger.ReadLedgerAsync()).Status);
        await (Task)consume.Invoke(viewModel, [])!;
        Assert.Equal(CreateLedger().LoginGrantRemainingMinutes, (await ledger.ReadLedgerAsync()).LoginGrantRemainingMinutes);
        Assert.Empty(await ledger.ReadPendingOutboxAsync());
        Assert.True(await viewModel.StopActiveSessionAsync());
        Assert.Equal(V2LocalSessionStatus.Stopped, (await ledger.ReadLedgerAsync()).Status);
    }

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
        public V2LocalSessionLedger? PendingLedger { get; set; }
        public RpcException? PollError { get; set; }
        public Task<V2LocalSessionLedger?> RedeemPendingGuestAccessAsync(
            string deviceId, IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default, V2LocalSessionLedger? activeGuestLedger = null)
            => PollError is null ? Task.FromResult(PendingLedger)
                : Task.FromException<V2LocalSessionLedger?>(PollError);
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

    [Theory]
    [InlineData(StatusCode.AlreadyExists, "Guest session is no longer active", false, true)]
    [InlineData(StatusCode.AlreadyExists, "Guest session is no longer active", true, true)]
    [InlineData(StatusCode.AlreadyExists, "Other conflict", false, false)]
    [InlineData(StatusCode.Unavailable, "Guest session is no longer active", false, false)]
    public async Task GuestPollLocksOnlyAfterServerCompletion(
        StatusCode status, string detail, bool failWrite, bool shouldStop)
    {
        var saved = CreateLedger(loginGrantMinutes: 0,
            packages: [new("guest-package", "guest", null, 3, V2LocalPackageStatus.Active),
                new("queued-package", "guest", null, 2, V2LocalPackageStatus.Queued)]) with
        {
            ClientId = Guid.Empty, GuestName = "Guest", GuestPaymentId = Guid.NewGuid(),
        };
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        await ledger.InitializeAsync(saved);
        var gateway = new GuestStopGateway(false)
        {
            PollError = new RpcException(new Status(status, detail)),
        };
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()), new Credentials(), deviceId: saved.DeviceId,
            v2OfflineLogin: new V2OfflineLoginCoordinator(new V2Gateway(saved), ledger),
            v2Ledger: ledger, v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier(), v2GuestSession: gateway);
        await viewModel.RecoverV2SessionAsync(new V2LocalLedgerRecoveryCoordinator(ledger));
        store.FailNextWrite = failWrite;
        var poll = typeof(MainViewModel).GetMethod("PollGuestAccessAsync", BindingFlags.Instance | BindingFlags.NonPublic)!;
        await (Task)poll.Invoke(viewModel, [])!;
        Assert.Equal(shouldStop, viewModel.IsAccessLocked);
        if (failWrite)
        {
            Assert.Equal(saved, await ledger.ReadLedgerAsync());
            await (Task)poll.Invoke(viewModel, [])!;
        }
        var persisted = await ledger.ReadLedgerAsync();
        if (shouldStop)
        {
            Assert.Equal(V2LocalSessionStatus.Stopped, persisted!.Status);
            Assert.All(persisted.Packages, package => Assert.Equal(V2LocalPackageStatus.Burned, package.Status));
            Assert.False(viewModel.IsActiveSessionVisible);
        }
        else
            Assert.Equal(saved, persisted);
    }

    [Fact]
    public async Task GuestRecoveryAndRefreshDoNotUseTheAccountPortal()
    {
        // Проверяет восстановление гостевого ledger без кабинета и клиентского счёта.
        var saved = CreateLedger(loginGrantMinutes: 0,
            packages:
            [
                new("active-guest", "t-guest", null, 2, V2LocalPackageStatus.Active),
                new("queued-guest", "t-guest", null, 3, V2LocalPackageStatus.Queued),
                new("exhausted-guest", "t-guest", null, 0, V2LocalPackageStatus.Exhausted),
                new("burned-guest", "t-guest", null, 0, V2LocalPackageStatus.Burned),
            ],
            tariffs: [new("t-guest", "Тест", null, 3, 0, 0, false)]) with
        {
            ClientId = Guid.Empty,
            GuestName = "Гость",
            GuestPaymentId = Guid.Parse("00000000-0000-0000-0000-000000000004"),
        };
        var ledger = new V2LocalLedgerCoordinator(new InMemoryLedgerStore());
        await ledger.InitializeAsync(saved);
        var guestGateway = new GuestStopGateway(false);
        await using var viewModel = new MainViewModel(
            new ClientSessionCoordinator(CreateBackend()),
            new Credentials(),
            deviceId: saved.DeviceId,
            v2OfflineLogin: new V2OfflineLoginCoordinator(new V2Gateway(saved), ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: new AcceptingVerifier(),
            v2ClientPortal: new CompletedSessionPortal(saved),
            v2GuestSession: guestGateway);

        var cachedProfile = new ClientPortalSnapshot("old-client", "Previous player", "79990000000", 90000, 10, 60,
            [], [], [], [], [], [new("old-tariff", "Old tariff", null, 60, 10000, false, null, null, null, null, null, "registered")], []);
        typeof(MainViewModel).GetMethod("SetPortalSnapshot", BindingFlags.Instance | BindingFlags.NonPublic)!
            .Invoke(viewModel, [cachedProfile]);
        await viewModel.RecoverV2SessionAsync(new V2LocalLedgerRecoveryCoordinator(ledger));
        await viewModel.RefreshPortalAsync();

        Assert.False(viewModel.IsAccessLocked);
        Assert.True(viewModel.IsActiveSessionVisible);
        Assert.Equal(saved, await ledger.ReadLedgerAsync());
        Assert.True(viewModel.IsGuestWidgetVisible);
        Assert.True(viewModel.IsWidgetContentVisible);
        Assert.False(viewModel.IsSecuredContentVisible);
        Assert.False(viewModel.IsPortalContentVisible);
        Assert.False(viewModel.IsAccountWidgetReadyVisible);
        Assert.False(viewModel.IsTariffsVisible);
        Assert.False(viewModel.CanCreateTransferOffer);
        Assert.Equal("Гость", viewModel.WidgetAccountSummary);
        Assert.Equal("00:05", viewModel.WidgetTimerSummary);
        Assert.Equal(
            new[]
            {
                new PortalEntitlementRow("Тест", "Активен", "2 мин", true),
                new PortalEntitlementRow("Тест", "В очереди", "3 мин", false),
            }, viewModel.WidgetEntitlementRows);
        var changes = new List<string?>();
        viewModel.PropertyChanged += (_, args) => changes.Add(args.PropertyName);
        var grantId = Guid.NewGuid();
        guestGateway.PendingLedger = saved with
        {
            SnapshotId = grantId,
            Packages = [new(grantId.ToString(), "t-guest", null, 3, V2LocalPackageStatus.Active)],
        };
        var poll = typeof(MainViewModel).GetMethod("PollGuestAccessAsync", BindingFlags.Instance | BindingFlags.NonPublic)!;
        await (Task)poll.Invoke(viewModel, [])!;
        Assert.Equal(3, viewModel.WidgetEntitlementRows.Count);
        Assert.Equal("00:08", viewModel.WidgetTimerSummary);
        Assert.Contains(nameof(MainViewModel.WidgetTimerSummary), changes);
        Assert.Equal(new PortalEntitlementRow("Тест", "В очереди", "3 мин", false), viewModel.WidgetEntitlementRows[^1]);
        Assert.Contains(nameof(MainViewModel.WidgetEntitlementRows), changes);
        Assert.False(viewModel.HasV2DeliveryWarning);
        viewModel.ApplyV2ServerEventTransportFailure(new IOException("connection unavailable"));
        Assert.True(viewModel.HasV2DeliveryWarning);
        viewModel.ApplyV2ServerEventPollResult(0);
        Assert.False(viewModel.HasV2DeliveryWarning);
        Assert.True(await viewModel.StopActiveSessionAsync());
        Assert.False(viewModel.IsWidgetContentVisible);
        Assert.False(viewModel.IsGuestWidgetVisible);
        Assert.Contains(nameof(MainViewModel.WidgetEntitlementRows), changes);
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
        public Task CancelMinuteBonusAsync(V2MinuteBonusRequest request, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<BonusGameQuote> QuoteMinuteBonusAsync(V2MinuteBonusRequest request, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public Task<V2MinuteBonusGrant> EnableMinuteBonusAsync(V2MinuteBonusRequest request,
            IOfflineSnapshotSignatureVerifier signatureVerifier, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();
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
            IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default,
            BonusPurchaseConfirmation? bonusConfirmation = null) =>
            throw new NotSupportedException();

        public Task<BonusGameQuote> QuoteEntitlementAsync(
            string deviceId, string tariffId, bool useBonus,
            CancellationToken cancellationToken = default) => throw new NotSupportedException();
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
