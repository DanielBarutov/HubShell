using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Application;

/// <summary>
/// Сериализует локальные V2-действия и сохраняет изменение состояния с outbox
/// до того, как кто-либо попытается отправить событие в Kafka.
/// </summary>
public sealed class V2LocalLedgerCoordinator
{
    private readonly IV2LocalLedgerStore _store;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public V2LocalLedgerCoordinator(IV2LocalLedgerStore store) => _store = store;

    public async Task InitializeAsync(
        V2LocalSessionLedger ledger,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            if (await _store.ReadAsync(cancellationToken) is not null)
            {
                throw new InvalidOperationException("V2 local ledger is already initialized");
            }
            await _store.WriteAsync(
                new V2LocalLedgerStorageSnapshot(
                    ledger,
                    Array.Empty<V2LocalFact>(),
                    Array.Empty<V2ClientInboxEntry>()),
                cancellationToken);
        }
        finally
        {
            _gate.Release();
        }
    }

    /// <summary>
    /// Начинает следующую signed V2-сессию на том же ПК. Активный ledger нельзя
    /// перезаписать: сначала он должен завершиться локальным фактом.
    /// </summary>
    public async Task InitializeNextSessionAsync(
        V2LocalSessionLedger ledger,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var existing = await _store.ReadAsync(cancellationToken);
            if (existing is null)
            {
                await _store.WriteAsync(
                    new V2LocalLedgerStorageSnapshot(
                        ledger,
                        Array.Empty<V2LocalFact>(),
                        Array.Empty<V2ClientInboxEntry>()),
                    cancellationToken);
                return;
            }
            if (existing.Ledger.Status == V2LocalSessionStatus.Active)
            {
                throw new InvalidOperationException("An active V2 local ledger cannot be replaced");
            }
            if (existing.PendingOutbox.Count != 0)
            {
                throw new InvalidOperationException("V2 local facts must be delivered before the next session");
            }
            if (!string.Equals(existing.Ledger.DeviceId, ledger.DeviceId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("V2 local ledger belongs to another device");
            }
            await _store.WriteAsync(
                new V2LocalLedgerStorageSnapshot(
                    ledger,
                    Array.Empty<V2LocalFact>(),
                    Array.Empty<V2ClientInboxEntry>()),
                cancellationToken);
        }
        finally
        {
            _gate.Release();
        }
    }

    public Task<V2LocalLedgerTransition> ConsumeOneMinuteAsync(
        Guid actionId,
        DateTimeOffset occurredAt,
        CancellationToken cancellationToken = default) =>
        ApplyClientActionAsync(
            ledger => V2LocalLedgerEngine.ConsumeOneMinute(ledger, actionId, occurredAt),
            cancellationToken);

    public Task<V2LocalLedgerTransition> ConsumeMinuteBoundaryAsync(
        Guid actionId,
        DateTimeOffset minuteBoundaryUtc,
        CancellationToken cancellationToken = default) =>
        ApplyClientActionAsync(
            ledger => V2LocalLedgerEngine.ConsumeMinuteBoundary(
                ledger,
                actionId,
                minuteBoundaryUtc),
            cancellationToken);

    public Task<V2LocalLedgerTransition> PurchasePackageAsync(
        Guid actionId,
        string tariffId,
        DateTimeOffset occurredAt,
        CancellationToken cancellationToken = default) =>
        ApplyClientActionAsync(
            ledger => V2LocalLedgerEngine.PurchasePackage(ledger, actionId, tariffId, occurredAt),
            cancellationToken);

    public Task<V2LocalLedgerTransition> StopEarlyAsync(
        Guid actionId,
        DateTimeOffset occurredAt,
        CancellationToken cancellationToken = default) =>
        ApplyClientActionAsync(
            ledger => V2LocalLedgerEngine.StopEarly(ledger, actionId, occurredAt),
            cancellationToken);

    public async Task<V2LocalLedgerTransition> ApplyBalanceCreditAsync(
        Guid eventId,
        Guid depositOperationId,
        long amountCents,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            var accepted = current.ClientInbox.SingleOrDefault(item =>
                item.OperationId == depositOperationId);
            if (accepted is not null)
            {
                if (accepted.EventId != eventId)
                {
                    throw new InvalidOperationException("Server operation id is already used by another event");
                }
                return new(
                    current.Ledger,
                    Array.Empty<V2LocalFact>(),
                    current.Ledger.Status is V2LocalSessionStatus.Exhausted or V2LocalSessionStatus.Stopped,
                    IsDuplicate: true);
            }
            var transition = V2LocalLedgerEngine.ApplyBalanceCredit(
                current.Ledger,
                depositOperationId,
                amountCents);
            if (!transition.IsDuplicate)
            {
                await _store.WriteAsync(
                    current with
                    {
                        Ledger = transition.Ledger,
                        ClientInbox = current.ClientInbox.Append(new V2ClientInboxEntry(
                            eventId,
                            depositOperationId,
                            "balance_credit_applied",
                            DateTimeOffset.UtcNow)).ToArray(),
                    },
                    cancellationToken);
            }
            return transition;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task RecordServerEventIssueAsync(
        string eventId,
        string operationId,
        string reasonCode,
        string message,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            var now = DateTimeOffset.UtcNow;
            var issues = current.ServerEventIssues ?? Array.Empty<V2ServerEventIssue>();
            var existing = issues.FirstOrDefault(item =>
                string.Equals(item.EventId, eventId, StringComparison.Ordinal)
                && string.Equals(item.OperationId, operationId, StringComparison.Ordinal));
            var updated = existing is null
                ? new V2ServerEventIssue(
                    eventId,
                    operationId,
                    reasonCode,
                    message,
                    now,
                    now,
                    1)
                : existing with
                {
                    ReasonCode = reasonCode,
                    Message = message,
                    LastSeenAtUtc = now,
                    Attempts = existing.Attempts + 1,
                };
            await _store.WriteAsync(
                current with
                {
                    ServerEventIssues = existing is null
                        ? issues.Append(updated).ToArray()
                        : issues.Select(item => item == existing ? updated : item).ToArray(),
                },
                cancellationToken);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<IReadOnlyList<V2LocalFact>> ReadPendingOutboxAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            return (await _store.ReadAsync(cancellationToken))?.PendingOutbox
                ?? Array.Empty<V2LocalFact>();
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<V2LocalLedgerStorageSnapshot?> ReadSnapshotAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            return await _store.ReadAsync(cancellationToken);
        }
        finally
        {
            _gate.Release();
        }
    }

    /// <summary>
    /// Вернуть неизменяемый снимок локальной сессии для проверки адресного
    /// server event до изменения ClientInbox. Метод не раскрывает хранилище.
    /// </summary>
    public async Task<V2LocalSessionLedger> ReadLedgerAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            return (await RequireSnapshotAsync(cancellationToken)).Ledger;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task AcknowledgeOutboxAsync(
        IReadOnlyCollection<Guid> eventIds,
        CancellationToken cancellationToken = default)
    {
        if (eventIds.Count == 0)
        {
            return;
        }
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            var acknowledged = eventIds.ToHashSet();
            await _store.WriteAsync(
                current with
                {
                    PendingOutbox = current.PendingOutbox
                        .Where(item => !acknowledged.Contains(item.EventId))
                        .ToArray(),
                },
                cancellationToken);
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task<V2LocalLedgerTransition> ApplyClientActionAsync(
        Func<V2LocalSessionLedger, V2LocalLedgerTransition> action,
        CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            var transition = action(current.Ledger);
            if (!transition.IsDuplicate)
            {
                await _store.WriteAsync(
                    current with
                    {
                        Ledger = transition.Ledger,
                        PendingOutbox = current.PendingOutbox.Concat(transition.OutboxFacts).ToArray(),
                    },
                    cancellationToken);
            }
            return transition;
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task<V2LocalLedgerStorageSnapshot> RequireSnapshotAsync(
        CancellationToken cancellationToken) =>
        await _store.ReadAsync(cancellationToken)
        ?? throw new InvalidOperationException("V2 local ledger is not initialized");
}
