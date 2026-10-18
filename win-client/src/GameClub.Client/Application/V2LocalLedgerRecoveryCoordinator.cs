using GameClub.Client.Domain;

namespace GameClub.Client.Application;

/// <summary>
/// Проверяет durable V2 ledger после запуска процесса. Чтение происходит одним
/// снимком, поэтому UI не видит ledger без его inbox/outbox и не открывает
/// доступ для другого устройства.
/// </summary>
public sealed class V2LocalLedgerRecoveryCoordinator
{
    private readonly V2LocalLedgerCoordinator _ledger;

    public V2LocalLedgerRecoveryCoordinator(V2LocalLedgerCoordinator ledger) => _ledger = ledger;

    public async Task<V2LedgerRecoveryResult> RecoverAsync(
        string deviceId,
        CancellationToken cancellationToken = default)
    {
        var resolvedIssues = await _ledger.ResolveNonClientServerEventIssuesAsync(cancellationToken);
        if (resolvedIssues > 0)
        {
            ClientLog.Info(
                "v2.recovery",
                $"resolved_non_client_server_event_issues={resolvedIssues}");
        }
        var snapshot = await _ledger.ReadSnapshotAsync(cancellationToken);
        if (snapshot is null)
        {
            return V2LedgerRecoveryResult.Empty;
        }
        if (!string.Equals(snapshot.Ledger.DeviceId, deviceId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("V2 local ledger belongs to another device");
        }

        var state = snapshot.Ledger.Status == V2LocalSessionStatus.Active
            ? V2LedgerRecoveryState.Active
            : snapshot.PendingOutbox.Count == 0
                ? V2LedgerRecoveryState.Completed
                : V2LedgerRecoveryState.CompletedPendingDelivery;
        return new(
            state,
            snapshot.Ledger,
            snapshot.PendingOutbox.Count,
            snapshot.ServerEventIssues?.Count ?? 0);
    }
}

public enum V2LedgerRecoveryState
{
    Empty,
    Active,
    Completed,
    CompletedPendingDelivery,
}

public sealed record V2LedgerRecoveryResult(
    V2LedgerRecoveryState State,
    V2LocalSessionLedger? Ledger,
    int PendingOutboxCount,
    int ServerEventIssueCount)
{
    public static V2LedgerRecoveryResult Empty { get; } = new(
        V2LedgerRecoveryState.Empty,
        null,
        0,
        0);
}
