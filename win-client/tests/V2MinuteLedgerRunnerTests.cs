using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class V2MinuteLedgerRunnerTests
{
    [Fact]
    public async Task ConsumesEveryDueBoundaryOnceAndDoesNotRepeatAfterRestart()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger("2026-09-28T10:00:20Z"));
        var runner = new V2MinuteLedgerRunner(coordinator, () => Guid.NewGuid());

        var firstRun = await runner.ConsumeDueMinutesAsync(
            DateTimeOffset.Parse("2026-09-28T10:02:05Z"));
        var afterRestart = new V2MinuteLedgerRunner(coordinator, () => Guid.NewGuid());
        var repeated = await afterRestart.ConsumeDueMinutesAsync(
            DateTimeOffset.Parse("2026-09-28T10:02:50Z"));
        var persisted = await coordinator.ReadLedgerAsync();

        Assert.Equal(2, firstRun.Count);
        Assert.Empty(repeated);
        Assert.Equal(3, persisted.LoginGrantRemainingMinutes);
        Assert.Equal(DateTimeOffset.Parse("2026-09-28T10:02:00Z"), persisted.LastConsumedMinuteUtc);
        Assert.Equal(2, (await coordinator.ReadPendingOutboxAsync()).Count);
    }

    [Fact]
    public async Task DoesNotDebitAgainWhenTheWallClockMovesBackward()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger("2026-09-28T10:00:20Z"));
        var runner = new V2MinuteLedgerRunner(coordinator, () => Guid.NewGuid());

        await runner.ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-28T10:02:05Z"));
        var afterRollback = await runner.ConsumeDueMinutesAsync(
            DateTimeOffset.Parse("2026-09-28T10:01:05Z"));

        Assert.Empty(afterRollback);
        Assert.Equal(3, (await coordinator.ReadLedgerAsync()).LoginGrantRemainingMinutes);
    }

    private static V2LocalSessionLedger CreateLedger(string activatedAtUtc) =>
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
            activatedAtUtc: DateTimeOffset.Parse(activatedAtUtc));

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
}
