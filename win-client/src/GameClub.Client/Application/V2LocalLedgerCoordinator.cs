using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Application;

/// <summary>
/// Сериализует локальные V2-действия и сохраняет изменение состояния с outbox
/// до того, как кто-либо попытается отправить событие в Kafka.
/// </summary>
public sealed class V2LocalLedgerCoordinator
{
    private const string NonClientServerEventMessage =
        "Для локального баланса разрешён только BalanceCreditApplied.";

    private readonly IV2LocalLedgerStore _store;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public V2LocalLedgerCoordinator(IV2LocalLedgerStore store) => _store = store;

    public async Task<V2LocalSessionLedger> EnableMinuteBonusAsync(
        Func<V2MinuteBonusRequest, CancellationToken, Task<V2MinuteBonusGrant>> issue,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            if (current.MinuteBonusCancellationPending)
                throw new InvalidOperationException("Minute bonus cancellation must synchronize first");
            var ledger = current.Ledger;
            if (ledger.IsGuest || ledger.Status != V2LocalSessionStatus.Active)
                throw new InvalidOperationException("Minute bonus requires an active registered session");
            var request = current.PendingMinuteBonusRequest;
            if (request is null || request.LastSequence != ledger.NextSequence - 1
                || request.LastPayloadHash != ledger.PreviousPayloadHash)
            {
                request = new(ledger.ClientId, ledger.SessionId, ledger.DeviceId, ledger.SnapshotId,
                    ledger.SnapshotVersion, ledger.NextSequence - 1, ledger.PreviousPayloadHash,
                    $"minute-bonus-{Guid.NewGuid():N}");
                current = current with { PendingMinuteBonusRequest = request };
                await _store.WriteAsync(current, cancellationToken);
            }
            var grant = await issue(request, cancellationToken);
            if (grant.Request != request) throw new InvalidOperationException("Minute bonus response differs from the durable request");
            ledger = V2LocalLedgerEngine.ApplyMinuteBonusGrant(ledger, grant);
            await _store.WriteAsync(current with { Ledger = ledger, PendingMinuteBonusRequest = null }, cancellationToken);
            return ledger;
        }
        finally { _gate.Release(); }
    }

    public async Task<V2LocalLedgerTransition> DisableMinuteBonusAsync(Guid actionId, DateTimeOffset occurredAt,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            var transition = V2LocalLedgerEngine.DisableMinuteBonus(current.Ledger, actionId, occurredAt);
            await _store.WriteAsync(current with { Ledger = transition.Ledger,
                PendingOutbox = current.PendingOutbox.Concat(transition.OutboxFacts).ToArray(),
                MinuteBonusCancellationPending = current.MinuteBonusCancellationPending || current.PendingMinuteBonusRequest is not null }, cancellationToken);
            return transition;
        }
        finally { _gate.Release(); }
    }

    public async Task<(V2MinuteBonusRequest? Request, bool CancellationPending)> ReadPendingMinuteBonusAsync(CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try {
            var current = await RequireSnapshotAsync(cancellationToken);
            return (current.PendingMinuteBonusRequest, current.MinuteBonusCancellationPending);
        }
        finally { _gate.Release(); }
    }

    public async Task<V2LocalSessionLedger> SynchronizeMinuteBonusCancellationAsync(
        Func<V2MinuteBonusRequest, CancellationToken, Task> cancel, CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            if (!current.MinuteBonusCancellationPending || current.PendingMinuteBonusRequest is not { } pending) return current.Ledger;
            var request = pending with { LastSequence = current.Ledger.NextSequence - 1, LastPayloadHash = current.Ledger.PreviousPayloadHash };
            await cancel(request, cancellationToken);
            await _store.WriteAsync(current with { PendingMinuteBonusRequest = null, MinuteBonusCancellationPending = false }, cancellationToken);
            return current.Ledger;
        }
        finally { _gate.Release(); }
    }

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
    /// перезаписать; незавершённые outbox-факты и dedupe-состояние сохраняются
    /// для последующей доставки и защиты от повторного применения.
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
            if (!string.Equals(existing.Ledger.DeviceId, ledger.DeviceId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("V2 local ledger belongs to another device");
            }
            await _store.WriteAsync(
                new V2LocalLedgerStorageSnapshot(
                    ledger,
                    existing.PendingOutbox,
                    existing.ClientInbox,
                    existing.ServerEventIssues),
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

    public async Task<V2PendingPortalPackagePurchase> BeginPortalPackagePurchaseAsync(
        string tariffId,
        CancellationToken cancellationToken = default,
        BonusPurchaseConfirmation? bonusConfirmation = null)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            if (current.PendingPortalPackagePurchase is { } pending)
            {
                if (!string.Equals(pending.TariffId, tariffId, StringComparison.Ordinal))
                {
                    throw new InvalidOperationException(
                        "A previous portal package purchase must be resolved before starting another");
                }
                if (bonusConfirmation is not null && pending.BonusConfirmation != bonusConfirmation)
                {
                    throw new InvalidOperationException("Pending package payment cannot be changed");
                }
                return pending;
            }

            if (current.Ledger.Status != V2LocalSessionStatus.Active || string.IsNullOrWhiteSpace(tariffId))
            {
                throw new InvalidOperationException("Package purchase requires an active V2 session and tariff");
            }
            var purchase = new V2PendingPortalPackagePurchase(
                Guid.NewGuid(),
                $"win-portal-tariff-{Guid.NewGuid():N}",
                tariffId,
                bonusConfirmation);
            await _store.WriteAsync(
                current with { PendingPortalPackagePurchase = purchase },
                cancellationToken);
            return purchase;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<V2LocalLedgerTransition> CompletePortalPackagePurchaseAsync(
        string tariffId,
        DateTimeOffset occurredAt,
        CancellationToken cancellationToken = default,
        V2LocalSessionLedger? purchasedPackage = null)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            var pending = current.PendingPortalPackagePurchase
                ?? throw new InvalidOperationException("No portal package purchase is pending");
            if (!string.Equals(pending.TariffId, tariffId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Portal package purchase tariff does not match");
            }

            var purchaseLedger = current.Ledger;
            if (pending.BonusConfirmation is not null && purchasedPackage is null)
            {
                throw new InvalidOperationException("Bonus purchase requires a signed payment receipt");
            }
            string? packageId = null;
            if (purchasedPackage is not null)
            {
                var package = purchasedPackage.Packages.Single();
                var tariff = purchasedPackage.Tariffs.Single();
                if (purchasedPackage.ClientId != purchaseLedger.ClientId
                    || purchasedPackage.SessionId != purchaseLedger.SessionId
                    || purchasedPackage.DeviceId != purchaseLedger.DeviceId
                    || purchasedPackage.ZoneId != purchaseLedger.ZoneId
                    || package.TariffId != tariffId || tariff.Id != tariffId
                    || package.RemainingMinutes != tariff.PackageMinutes
                    || package.ZoneId != tariff.ZoneId)
                {
                    throw new InvalidOperationException("Signed package purchase belongs to another session or tariff");
                }
                packageId = package.Id;
                if (pending.BonusConfirmation is { } confirmed
                    && (purchasedPackage.PurchasePayment is not { } paid
                        || paid.MoneyCents != confirmed.MoneyCents
                        || paid.BonusCents != confirmed.BonusCents
                        || tariff.PackagePriceCents != confirmed.PriceCents))
                {
                    throw new InvalidOperationException("Signed payment differs from the confirmed quote");
                }
                purchaseLedger = purchaseLedger with
                {
                    Tariffs = purchaseLedger.Tariffs.Where(item => item.Id != tariffId).Append(tariff).ToArray(),
                };
            }
            var transition = V2LocalLedgerEngine.PurchasePackage(
                purchaseLedger,
                pending.ActionId,
                pending.TariffId,
                occurredAt,
                serverConfirmed: true,
                packageId: packageId,
                purchaseIdempotencyKey: pending.IdempotencyKey,
                payment: purchasedPackage?.PurchasePayment);
            if (purchasedPackage?.Packages.Single().Status == V2LocalPackageStatus.Active)
            {
                transition = transition with
                {
                    Ledger = V2LocalLedgerEngine.ApplyActivePackage(transition.Ledger, purchasedPackage).Ledger,
                };
            }
            await _store.WriteAsync(
                current with
                {
                    Ledger = transition.Ledger,
                    PendingOutbox = current.PendingOutbox.Concat(transition.OutboxFacts).ToArray(),
                    PendingPortalPackagePurchase = null,
                },
                cancellationToken);
            return transition;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task AbandonPendingPortalPackagePurchaseAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await RequireSnapshotAsync(cancellationToken);
            if (current.PendingPortalPackagePurchase is not null)
            {
                await _store.WriteAsync(
                    current with { PendingPortalPackagePurchase = null },
                    cancellationToken);
            }
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<V2PendingPortalPackagePurchase?> ReadPendingPortalPackagePurchaseAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            return (await RequireSnapshotAsync(cancellationToken)).PendingPortalPackagePurchase;
        }
        finally
        {
            _gate.Release();
        }
    }

    public Task<V2LocalLedgerTransition> StopEarlyAsync(
        Guid actionId,
        DateTimeOffset occurredAt,
        CancellationToken cancellationToken = default) =>
        ApplyClientActionAsync(
            ledger => V2LocalLedgerEngine.StopEarly(ledger, actionId, occurredAt),
            cancellationToken);

    public Task<V2LocalLedgerTransition> ApplyActivePackageAsync(
        V2LocalSessionLedger signedPackage, CancellationToken cancellationToken = default) =>
        ApplyClientActionAsync(ledger => V2LocalLedgerEngine.ApplyActivePackage(ledger, signedPackage), cancellationToken);

    public Task<V2LocalLedgerTransition> ApplyGuestPackageAsync(
        V2LocalSessionLedger signedPackage,
        CancellationToken cancellationToken = default) =>
        ApplyClientActionAsync(
            ledger => V2LocalLedgerEngine.ApplyGuestPackage(ledger, signedPackage),
            cancellationToken);

    public Task<V2LocalLedgerTransition> ApplyServerStopAsync(
        CancellationToken cancellationToken = default) =>
        ApplyClientActionAsync(
            V2LocalLedgerEngine.ApplyServerStop,
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

    public async Task<int> ResolveNonClientServerEventIssuesAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var current = await _store.ReadAsync(cancellationToken);
            if (current is null || current.ServerEventIssues is not { Count: > 0 } issues)
            {
                return 0;
            }

            var retained = issues
                .Where(issue =>
                    issue.ReasonCode != "invalid_server_event"
                    || issue.Message != NonClientServerEventMessage)
                .ToArray();
            var resolvedCount = issues.Count - retained.Length;
            if (resolvedCount > 0)
            {
                await _store.WriteAsync(
                    current with { ServerEventIssues = retained },
                    cancellationToken);
            }
            return resolvedCount;
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
