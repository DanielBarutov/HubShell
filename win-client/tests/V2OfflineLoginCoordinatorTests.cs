using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class V2OfflineLoginCoordinatorTests
{
    [Fact]
    public async Task LoginPersistsOnlyTheVerifiedV2LedgerBeforeAccessCanOpen()
    {
        var verifiedLedger = CreateLedger("device-01");
        var store = new RecordingStore();
        var coordinator = new V2OfflineLoginCoordinator(
            new SnapshotGateway(verifiedLedger),
            new V2LocalLedgerCoordinator(store));

        var result = await coordinator.LoginAndInitializeAsync(
            "NightFox",
            "safe-password",
            "device-01",
            "v2-login-001",
            new AcceptingVerifier());

        Assert.Equal(verifiedLedger, result);
        Assert.NotNull(store.Snapshot);
        Assert.Equal(verifiedLedger, store.Snapshot!.Ledger);
        Assert.Empty(store.Snapshot.PendingOutbox);
        Assert.Empty(store.Snapshot.ClientInbox);
    }

    [Fact]
    public async Task PasswordResetChallengeIsKeptOutOfTheLedgerUntilCompleted()
    {
        var store = new RecordingStore();
        var gateway = new ResetGateway();
        var coordinator = new V2OfflineLoginCoordinator(
            gateway,
            new V2LocalLedgerCoordinator(store));

        var result = await coordinator.LoginAndInitializeResultAsync(
            "NightFox",
            string.Empty,
            "device-01",
            "v2-login-reset-001",
            new AcceptingVerifier());

        Assert.True(result.PasswordResetRequired);
        Assert.Null(result.Ledger);
        Assert.True(coordinator.PasswordResetRequired);
        Assert.Null(store.Snapshot);

        await coordinator.ChangePasswordAsync("new-password", "device-01");

        Assert.Equal("new-password", gateway.NewPassword);
        Assert.False(coordinator.PasswordResetRequired);
        Assert.Null(store.Snapshot);
    }

    [Fact]
    public async Task LoginRejectsSnapshotForAnotherDeviceWithoutWritingLedger()
    {
        var store = new RecordingStore();
        var coordinator = new V2OfflineLoginCoordinator(
            new SnapshotGateway(CreateLedger("another-device")),
            new V2LocalLedgerCoordinator(store));

        await Assert.ThrowsAsync<InvalidOperationException>(() => coordinator.LoginAndInitializeAsync(
            "NightFox",
            "safe-password",
            "device-01",
            "v2-login-001",
            new AcceptingVerifier()));

        Assert.Null(store.Snapshot);
    }

    [Fact]
    public async Task LoginReplacesOnlyACompletedLedgerForTheSameDevice()
    {
        var store = new RecordingStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        var completed = V2LocalLedgerEngine.StopEarly(
            CreateLedger("device-01"),
            Guid.NewGuid(),
            DateTimeOffset.UtcNow).Ledger;
        await ledger.InitializeAsync(completed);
        var next = CreateLedger("device-01") with
        {
            SessionId = Guid.Parse("00000000-0000-0000-0000-000000000099"),
        };
        var coordinator = new V2OfflineLoginCoordinator(new SnapshotGateway(next), ledger);

        await coordinator.LoginAndInitializeAsync(
            "NightFox",
            "safe-password",
            "device-01",
            "v2-login-002",
            new AcceptingVerifier());

        Assert.Equal(next.SessionId, store.Snapshot!.Ledger.SessionId);
        Assert.Empty(store.Snapshot.PendingOutbox);
    }

    [Fact]
    public async Task LoginNeverReplacesAnActiveLedger()
    {
        var store = new RecordingStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        await ledger.InitializeAsync(CreateLedger("device-01"));
        var coordinator = new V2OfflineLoginCoordinator(
            new SnapshotGateway(CreateLedger("device-01")),
            ledger);

        await Assert.ThrowsAsync<InvalidOperationException>(() => coordinator.LoginAndInitializeAsync(
            "NightFox",
            "safe-password",
            "device-01",
            "v2-login-002",
            new AcceptingVerifier()));

        Assert.Equal(V2LocalSessionStatus.Active, store.Snapshot!.Ledger.Status);
    }

    [Fact]
    public async Task LoginNeverDiscardsPendingFactsFromACompletedLedger()
    {
        var store = new RecordingStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        var stopped = V2LocalLedgerEngine.StopEarly(
            CreateLedger("device-01"),
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);
        await ledger.InitializeAsync(stopped.Ledger);
        await store.WriteAsync(new V2LocalLedgerStorageSnapshot(
            stopped.Ledger,
            stopped.OutboxFacts,
            Array.Empty<V2ClientInboxEntry>()));
        var coordinator = new V2OfflineLoginCoordinator(
            new SnapshotGateway(CreateLedger("device-01")),
            ledger);

        await Assert.ThrowsAsync<InvalidOperationException>(() => coordinator.LoginAndInitializeAsync(
            "NightFox",
            "safe-password",
            "device-01",
            "v2-login-002",
            new AcceptingVerifier()));

        Assert.Equal(stopped.OutboxFacts, store.Snapshot!.PendingOutbox);
    }

    private static V2LocalSessionLedger CreateLedger(string deviceId) =>
        V2LocalSessionLedger.Create(
            snapshotVersion: 1,
            clientId: Guid.Parse("00000000-0000-0000-0000-000000000001"),
            sessionId: Guid.Parse("00000000-0000-0000-0000-000000000002"),
            deviceId: deviceId,
            zoneId: null,
            balanceCents: 1_000,
            debtLimitCents: 0,
            loginGrantRemainingMinutes: 5,
            packages: Array.Empty<V2LocalPackage>(),
            tariffs: Array.Empty<V2LocalTariff>(),
            snapshotId: Guid.Parse("00000000-0000-0000-0000-000000000003"));

    private sealed class SnapshotGateway(V2LocalSessionLedger ledger) : IV2OfflineSessionGateway
    {
        public Task<V2OfflineLoginResult> RegisterAsync(
            string nickname,
            string phone,
            string password,
            string deviceId,
            string idempotencyKey,
            IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default) => Task.FromResult(
                new V2OfflineLoginResult(ledger, false, null));

        public Task<V2OfflineLoginResult> LoginAsync(
            string identifier,
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

    private sealed class ResetGateway : IV2OfflineSessionGateway
    {
        public string? NewPassword { get; private set; }

        public Task<V2OfflineLoginResult> RegisterAsync(
            string nickname,
            string phone,
            string password,
            string deviceId,
            string idempotencyKey,
            IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<V2OfflineLoginResult> LoginAsync(
            string identifier,
            string password,
            string deviceId,
            string idempotencyKey,
            IOfflineSnapshotSignatureVerifier signatureVerifier,
            CancellationToken cancellationToken = default) => Task.FromResult(
                new V2OfflineLoginResult(null, true, "reset-token"));

        public Task ChangePasswordAsync(
            string newPassword,
            string deviceId,
            string resetToken,
            CancellationToken cancellationToken = default)
        {
            NewPassword = newPassword;
            return Task.CompletedTask;
        }
    }

    private sealed class RecordingStore : IV2LocalLedgerStore
    {
        public V2LocalLedgerStorageSnapshot? Snapshot { get; private set; }

        public Task<V2LocalLedgerStorageSnapshot?> ReadAsync(
            CancellationToken cancellationToken = default) => Task.FromResult(Snapshot);

        public Task WriteAsync(
            V2LocalLedgerStorageSnapshot snapshot,
            CancellationToken cancellationToken = default)
        {
            Snapshot = snapshot;
            return Task.CompletedTask;
        }
    }

    private sealed class AcceptingVerifier : IOfflineSnapshotSignatureVerifier
    {
        public bool Verify(
            string signingKeyId,
            ReadOnlyMemory<byte> payload,
            ReadOnlyMemory<byte> signature) => true;
    }
}
