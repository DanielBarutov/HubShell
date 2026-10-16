using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace GameClub.Client.Domain;

public enum V2LocalSessionStatus
{
    Active,
    Exhausted,
    Stopped,
    NeedsReview,
}

public enum V2TimeSource
{
    LoginGrant,
    Package,
    PerMinute,
    Exhausted,
}

public enum V2LocalPackageStatus
{
    Active,
    Queued,
    Exhausted,
    Burned,
}

public sealed record V2LocalPackage(
    string Id,
    string TariffId,
    string? ZoneId,
    int RemainingMinutes,
    V2LocalPackageStatus Status);

public sealed record V2LocalTariff(
    string Id,
    string Name,
    string? ZoneId,
    int PackageMinutes,
    long PackagePriceCents,
    long PerMinutePriceCents,
    bool IsPurchasable,
    bool IsPerMinute = false);

public sealed record V2LocalFact(
    Guid EventId,
    Guid OperationId,
    Guid CausationId,
    Guid ClientId,
    Guid SessionId,
    string DeviceId,
    Guid CorrelationId,
    string Traceparent,
    string EventType,
    long Sequence,
    DateTimeOffset OccurredAt,
    string PayloadJson,
    string PayloadHash,
    string? PreviousHash);

public sealed record V2LocalSessionLedger(
    Guid SnapshotId,
    int SnapshotVersion,
    Guid ClientId,
    Guid SessionId,
    string DeviceId,
    string? ZoneId,
    long BalanceCents,
    long DebtLimitCents,
    int LoginGrantRemainingMinutes,
    IReadOnlyList<V2LocalPackage> Packages,
    IReadOnlyList<V2LocalTariff> Tariffs,
    long NextSequence,
    string? PreviousPayloadHash,
    V2LocalSessionStatus Status,
    IReadOnlyList<Guid> AppliedClientActionIds,
    IReadOnlyList<Guid> AppliedServerOperationIds,
    DateTimeOffset? ActivatedAtUtc,
    DateTimeOffset? LastConsumedMinuteUtc,
    string? GuestName = null,
    Guid? GuestPaymentId = null)
{
    public bool IsGuest => GuestPaymentId is not null;

    public static V2LocalSessionLedger Create(
        int snapshotVersion,
        Guid clientId,
        Guid sessionId,
        string deviceId,
        string? zoneId,
        long balanceCents,
        long debtLimitCents,
        int loginGrantRemainingMinutes,
        IReadOnlyList<V2LocalPackage> packages,
        IReadOnlyList<V2LocalTariff> tariffs,
        Guid? snapshotId = null,
        DateTimeOffset? activatedAtUtc = null,
        string? guestName = null,
        Guid? guestPaymentId = null)
    {
        if (snapshotVersion < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(snapshotVersion));
        }
        if (string.IsNullOrWhiteSpace(deviceId))
        {
            throw new ArgumentException("Device id is required", nameof(deviceId));
        }
        if (debtLimitCents < 0 || loginGrantRemainingMinutes < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(debtLimitCents));
        }
        if (packages.Count(item => item.Status == V2LocalPackageStatus.Active) > 1)
        {
            throw new ArgumentException("Only one package can be active", nameof(packages));
        }
        if (packages.Any(item => item.RemainingMinutes < 0))
        {
            throw new ArgumentException("Package minutes cannot be negative", nameof(packages));
        }
        if (packages.Any(item => !IsZoneCompatible(item.ZoneId, zoneId)))
        {
            throw new ArgumentException("Package is incompatible with workstation zone", nameof(packages));
        }
        if (tariffs.Any(item => item.PackageMinutes < 0
            || item.PackagePriceCents < 0
            || item.PerMinutePriceCents < 0))
        {
            throw new ArgumentException("Tariff values cannot be negative", nameof(tariffs));
        }

        return new(
            snapshotId ?? Guid.NewGuid(),
            snapshotVersion,
            clientId,
            sessionId,
            deviceId.Trim(),
            zoneId,
            balanceCents,
            debtLimitCents,
            loginGrantRemainingMinutes,
            packages.ToArray(),
            tariffs.ToArray(),
            NextSequence: 1,
            PreviousPayloadHash: null,
            V2LocalSessionStatus.Active,
            Array.Empty<Guid>(),
            Array.Empty<Guid>(),
            activatedAtUtc?.ToUniversalTime(),
            null,
            guestName?.Trim(),
            guestPaymentId);
    }

    public static bool IsZoneCompatible(string? tariffZoneId, string? workstationZoneId) =>
        tariffZoneId is null || string.Equals(tariffZoneId, workstationZoneId, StringComparison.Ordinal);
}

public sealed record V2LocalLedgerTransition(
    V2LocalSessionLedger Ledger,
    IReadOnlyList<V2LocalFact> OutboxFacts,
    bool LockWorkstation,
    bool IsDuplicate = false);

public sealed record V2LocalLedgerStorageSnapshot(
    V2LocalSessionLedger Ledger,
    IReadOnlyList<V2LocalFact> PendingOutbox,
    IReadOnlyList<V2ClientInboxEntry> ClientInbox,
    IReadOnlyList<V2ServerEventIssue>? ServerEventIssues = null,
    V2PendingPortalPackagePurchase? PendingPortalPackagePurchase = null);

public sealed record V2PendingPortalPackagePurchase(
    Guid ActionId,
    string IdempotencyKey,
    string TariffId);

public sealed record V2ClientInboxEntry(
    Guid EventId,
    Guid OperationId,
    string EventType,
    DateTimeOffset AcceptedAt);

public sealed record V2ServerEventIssue(
    string EventId,
    string OperationId,
    string ReasonCode,
    string Message,
    DateTimeOffset FirstSeenAtUtc,
    DateTimeOffset LastSeenAtUtc,
    int Attempts);

/// <summary>
/// Чистое ядро автономной сессии. Хранилище должно сохранять возвращённые Ledger
/// и OutboxFacts одной транзакцией до изменения интерфейса или отправки Kafka.
/// </summary>
public static class V2LocalLedgerEngine
{
    public static bool HasFreePerMinuteTime(V2LocalSessionLedger ledger) =>
        ledger.Status == V2LocalSessionStatus.Active
        && FindPerMinuteTariff(ledger) is { IsPerMinute: true, PerMinutePriceCents: 0 };

    public static long RemainingMinutes(V2LocalSessionLedger ledger)
    {
        if (ledger.Status != V2LocalSessionStatus.Active)
        {
            return 0;
        }
        var rate = FindPerMinuteTariff(ledger)?.PerMinutePriceCents ?? 0;
        var paidMinutes = rate > 0 ? Math.Max(0, ledger.BalanceCents) / rate : 0;
        return ledger.LoginGrantRemainingMinutes + paidMinutes
            + ledger.Packages.Where(item =>
                item.Status is V2LocalPackageStatus.Active or V2LocalPackageStatus.Queued
                && V2LocalSessionLedger.IsZoneCompatible(item.ZoneId, ledger.ZoneId))
                .Sum(item => (long)item.RemainingMinutes);
    }

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public static V2TimeSource CurrentSource(V2LocalSessionLedger ledger)
    {
        if (ledger.Status != V2LocalSessionStatus.Active)
        {
            return V2TimeSource.Exhausted;
        }
        if (ledger.LoginGrantRemainingMinutes > 0)
        {
            return V2TimeSource.LoginGrant;
        }
        if (FindActivePackage(ledger) is not null || FindQueuedPackage(ledger) is not null)
        {
            return V2TimeSource.Package;
        }
        return FindPerMinuteTariff(ledger) is not null
            ? V2TimeSource.PerMinute
            : V2TimeSource.Exhausted;
    }

    public static V2LocalLedgerTransition ConsumeOneMinute(
        V2LocalSessionLedger ledger,
        Guid actionId,
        DateTimeOffset occurredAt)
    {
        if (IsDuplicate(ledger, actionId))
        {
            return new(ledger, Array.Empty<V2LocalFact>(), Locks(ledger), IsDuplicate: true);
        }
        EnsureActive(ledger);

        if (ledger.LoginGrantRemainingMinutes > 0)
        {
            return AppendClientFacts(
                ledger with { LoginGrantRemainingMinutes = ledger.LoginGrantRemainingMinutes - 1 },
                actionId,
                occurredAt,
                [("login_grant_consumed", Payload(("remaining_minutes", ledger.LoginGrantRemainingMinutes - 1)))]);
        }

        var package = FindActivePackage(ledger) ?? FindQueuedPackage(ledger);
        if (package is not null)
        {
            var remaining = package.RemainingMinutes - 1;
            var packages = ledger.Packages
                .Select(item => item.Id == package.Id
                    ? item with
                    {
                        Status = remaining == 0 ? V2LocalPackageStatus.Exhausted : V2LocalPackageStatus.Active,
                        RemainingMinutes = remaining,
                    }
                    : item)
                .ToArray();
            return AppendClientFacts(
                ledger with { Packages = packages },
                actionId,
                occurredAt,
                [("package_consumed", Payload(
                    ("package_id", package.Id),
                    ("remaining_minutes", remaining),
                    ("tariff_id", package.TariffId)))]);
        }

        var perMinuteTariff = FindPerMinuteTariff(ledger);
        if (perMinuteTariff is { IsPerMinute: true, PerMinutePriceCents: 0 })
        {
            return AppendClientFacts(ledger, actionId, occurredAt, []);
        }
        if (perMinuteTariff is not null
            && perMinuteTariff.PerMinutePriceCents > 0
            && ledger.BalanceCents - perMinuteTariff.PerMinutePriceCents >= -ledger.DebtLimitCents)
        {
            var balanceAfterDebit = ledger.BalanceCents - perMinuteTariff.PerMinutePriceCents;
            return AppendClientFacts(
                ledger with { BalanceCents = balanceAfterDebit },
                actionId,
                occurredAt,
                [("per_minute_debit", Payload(
                    ("amount_cents", perMinuteTariff.PerMinutePriceCents),
                    ("balance_after_cents", balanceAfterDebit),
                    ("tariff_id", perMinuteTariff.Id)))]);
        }

        return AppendClientFacts(
            ledger with { Status = V2LocalSessionStatus.Exhausted },
            actionId,
            occurredAt,
            [("session_stopped", Payload(("reason", "known_balance_exhausted")))],
            lockWorkstation: true);
    }

    /// <summary>
    /// Используется только lifecycle runner. Один durable minute boundary не
    /// может породить второй debit после restart или повторного timer tick.
    /// </summary>
    public static V2LocalLedgerTransition ConsumeMinuteBoundary(
        V2LocalSessionLedger ledger,
        Guid actionId,
        DateTimeOffset minuteBoundaryUtc)
    {
        var boundary = TruncateToMinuteUtc(minuteBoundaryUtc);
        if (ledger.LastConsumedMinuteUtc is { } last
            && boundary <= TruncateToMinuteUtc(last))
        {
            return new(ledger, Array.Empty<V2LocalFact>(), Locks(ledger), IsDuplicate: true);
        }
        var transition = ConsumeOneMinute(ledger, actionId, boundary);
        return transition with
        {
            Ledger = transition.Ledger with { LastConsumedMinuteUtc = boundary },
        };
    }

    public static V2LocalLedgerTransition PurchasePackage(
        V2LocalSessionLedger ledger,
        Guid actionId,
        string tariffId,
        DateTimeOffset occurredAt,
        bool serverConfirmed = false,
        string? packageId = null,
        string? purchaseIdempotencyKey = null)
    {
        if (IsDuplicate(ledger, actionId))
        {
            return new(ledger, Array.Empty<V2LocalFact>(), Locks(ledger), IsDuplicate: true);
        }
        var tariff = RequirePurchasablePackageTariff(ledger, tariffId);
        if (!serverConfirmed
            && ledger.BalanceCents - tariff.PackagePriceCents < -ledger.DebtLimitCents)
        {
            throw new InvalidOperationException("Known balance is insufficient for package purchase");
        }

        var package = new V2LocalPackage(
            packageId ?? Guid.NewGuid().ToString(),
            tariff.Id,
            tariff.ZoneId,
            tariff.PackageMinutes,
            V2LocalPackageStatus.Queued);
        return AppendClientFacts(
            ledger with
            {
                BalanceCents = ledger.BalanceCents - tariff.PackagePriceCents,
                Packages = ledger.Packages.Append(package).ToArray(),
            },
            actionId,
            occurredAt,
            [("package_purchased", Payload(
                ("amount_cents", tariff.PackagePriceCents),
                ("package_id", package.Id),
                ("tariff_id", tariff.Id),
                ("tariff_name", tariff.Name),
                ("total_minutes", tariff.PackageMinutes),
                ("purchase_idempotency_key", purchaseIdempotencyKey ?? "")))]);
    }

    public static void ValidatePackagePurchase(
        V2LocalSessionLedger ledger,
        string tariffId)
    {
        var tariff = RequirePurchasablePackageTariff(ledger, tariffId);
        if (ledger.BalanceCents - tariff.PackagePriceCents < -ledger.DebtLimitCents)
        {
            throw new InvalidOperationException("Known balance is insufficient for package purchase");
        }
    }

    private static V2LocalTariff RequirePurchasablePackageTariff(
        V2LocalSessionLedger ledger,
        string tariffId)
    {
        EnsureActive(ledger);
        var tariff = ledger.Tariffs.SingleOrDefault(item => item.Id == tariffId)
            ?? throw new InvalidOperationException("Package tariff is not present in the signed snapshot");
        if (!tariff.IsPurchasable
            || tariff.PackageMinutes <= 0
            || !V2LocalSessionLedger.IsZoneCompatible(tariff.ZoneId, ledger.ZoneId))
        {
            throw new InvalidOperationException("Package tariff is not available on this workstation");
        }
        return tariff;
    }

    public static V2LocalLedgerTransition StopEarly(
        V2LocalSessionLedger ledger,
        Guid actionId,
        DateTimeOffset occurredAt)
    {
        if (IsDuplicate(ledger, actionId))
        {
            return new(ledger, Array.Empty<V2LocalFact>(), Locks(ledger), IsDuplicate: true);
        }
        EnsureActive(ledger);

        var facts = new List<(string EventType, string Payload)>();
        var next = ledger;
        if (ledger.LoginGrantRemainingMinutes > 0)
        {
            facts.Add(("login_grant_burned", Payload(("remaining_minutes", ledger.LoginGrantRemainingMinutes))));
            next = next with { LoginGrantRemainingMinutes = 0 };
        }
        else if (FindActivePackage(ledger) is { } package)
        {
            facts.Add(("package_burned", Payload(
                ("package_id", package.Id),
                ("remaining_minutes", package.RemainingMinutes),
                ("tariff_id", package.TariffId))));
            next = next with
            {
                Packages = next.Packages
                    .Select(item => item.Id == package.Id
                        ? item with { RemainingMinutes = 0, Status = V2LocalPackageStatus.Burned }
                        : item)
                    .ToArray(),
            };
        }
        if (ledger.IsGuest)
        {
            next = next with
            {
                Packages = next.Packages.Select(item =>
                    item.Status is V2LocalPackageStatus.Active or V2LocalPackageStatus.Queued
                        ? item with { RemainingMinutes = 0, Status = V2LocalPackageStatus.Burned }
                        : item).ToArray(),
            };
        }
        facts.Add(("session_stopped", Payload(("reason", "client_early_exit"))));
        return AppendClientFacts(
            next with { Status = V2LocalSessionStatus.Stopped },
            actionId,
            occurredAt,
            facts,
            lockWorkstation: true);
    }

    public static V2LocalLedgerTransition ApplyServerStop(V2LocalSessionLedger ledger)
    {
        if (ledger.Status != V2LocalSessionStatus.Active)
        {
            return new(ledger, Array.Empty<V2LocalFact>(), Locks(ledger), IsDuplicate: true);
        }

        return new(
            ledger with
            {
                Status = V2LocalSessionStatus.Stopped,
                LoginGrantRemainingMinutes = 0,
                Packages = ledger.Packages
                    .Select(item => (item.Status == V2LocalPackageStatus.Active
                        || ledger.IsGuest && item.Status == V2LocalPackageStatus.Queued)
                        ? item with { RemainingMinutes = 0, Status = V2LocalPackageStatus.Burned }
                        : item)
                    .ToArray(),
            },
            Array.Empty<V2LocalFact>(),
            LockWorkstation: true);
    }

    public static V2LocalLedgerTransition ApplyGuestPackage(
        V2LocalSessionLedger ledger,
        V2LocalSessionLedger signedPackage)
    {
        EnsureActive(ledger);
        if (!ledger.IsGuest || !signedPackage.IsGuest
            || ledger.SessionId != signedPackage.SessionId
            || ledger.DeviceId != signedPackage.DeviceId
            || ledger.ZoneId != signedPackage.ZoneId)
        {
            throw new InvalidOperationException("Guest package belongs to another session");
        }
        var grantId = signedPackage.SnapshotId;
        if (ledger.AppliedServerOperationIds.Contains(grantId) || ledger.SnapshotId == grantId)
        {
            return new(ledger, Array.Empty<V2LocalFact>(), false, IsDuplicate: true);
        }
        var package = signedPackage.Packages.Single();
        if (package.RemainingMinutes <= 0
            || !V2LocalSessionLedger.IsZoneCompatible(package.ZoneId, ledger.ZoneId))
        {
            throw new InvalidOperationException("Guest package is invalid");
        }
        return new(
            ledger with
            {
                Packages = ledger.Packages.Append(package with
                    { Status = V2LocalPackageStatus.Queued }).ToArray(),
                Tariffs = ledger.Tariffs.Concat(signedPackage.Tariffs)
                    .DistinctBy(item => item.Id).ToArray(),
                AppliedServerOperationIds = ledger.AppliedServerOperationIds.Append(grantId).ToArray(),
            },
            Array.Empty<V2LocalFact>(), false);
    }

    public static V2LocalLedgerTransition ApplyBalanceCredit(
        V2LocalSessionLedger ledger,
        Guid depositOperationId,
        long amountCents)
    {
        if (amountCents <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(amountCents));
        }
        if (ledger.AppliedServerOperationIds.Contains(depositOperationId))
        {
            return new(ledger, Array.Empty<V2LocalFact>(), Locks(ledger), IsDuplicate: true);
        }
        return new(
            ledger with
            {
                BalanceCents = checked(ledger.BalanceCents + amountCents),
                AppliedServerOperationIds = ledger.AppliedServerOperationIds.Append(depositOperationId).ToArray(),
            },
            Array.Empty<V2LocalFact>(),
            Locks(ledger));
    }

    private static V2LocalLedgerTransition AppendClientFacts(
        V2LocalSessionLedger ledger,
        Guid actionId,
        DateTimeOffset occurredAt,
        IReadOnlyList<(string EventType, string Payload)> pendingFacts,
        bool lockWorkstation = false)
    {
        if (ledger.IsGuest)
        {
            return new(
                ledger with
                {
                    AppliedClientActionIds = ledger.AppliedClientActionIds.Append(actionId).ToArray(),
                },
                Array.Empty<V2LocalFact>(),
                lockWorkstation);
        }
        var nextSequence = ledger.NextSequence;
        var previousHash = ledger.PreviousPayloadHash;
        var facts = new List<V2LocalFact>(pendingFacts.Count);
        foreach (var (eventType, payload) in pendingFacts)
        {
            var snapshotBoundPayload = BindPayloadToSnapshot(ledger, payload);
            var payloadHash = Hash(snapshotBoundPayload);
            facts.Add(new(
                Guid.NewGuid(),
                Guid.NewGuid(),
                actionId,
                ledger.ClientId,
                ledger.SessionId,
                ledger.DeviceId,
                ledger.SessionId,
                NewTraceparent(),
                eventType,
                nextSequence++,
                occurredAt,
                snapshotBoundPayload,
                payloadHash,
                previousHash));
            previousHash = payloadHash;
        }
        return new(
            ledger with
            {
                NextSequence = nextSequence,
                PreviousPayloadHash = previousHash,
                AppliedClientActionIds = ledger.AppliedClientActionIds.Append(actionId).ToArray(),
            },
            facts,
            lockWorkstation);
    }

    private static V2LocalPackage? FindActivePackage(V2LocalSessionLedger ledger) =>
        ledger.Packages.SingleOrDefault(item =>
            item.Status == V2LocalPackageStatus.Active && item.RemainingMinutes > 0);

    private static V2LocalPackage? FindQueuedPackage(V2LocalSessionLedger ledger) =>
        ledger.Packages.FirstOrDefault(item =>
            item.Status == V2LocalPackageStatus.Queued
            && item.RemainingMinutes > 0
            && V2LocalSessionLedger.IsZoneCompatible(item.ZoneId, ledger.ZoneId));

    private static V2LocalTariff? FindPerMinuteTariff(V2LocalSessionLedger ledger) =>
        ledger.Tariffs.SingleOrDefault(item =>
            (item.IsPerMinute || item.PerMinutePriceCents > 0)
            && V2LocalSessionLedger.IsZoneCompatible(item.ZoneId, ledger.ZoneId));

    private static string Payload(params (string Key, object Value)[] values) =>
        JsonSerializer.Serialize(
            new SortedDictionary<string, object>(
                values.ToDictionary(item => item.Key, item => item.Value, StringComparer.Ordinal),
                StringComparer.Ordinal),
            JsonOptions);

    private static string BindPayloadToSnapshot(V2LocalSessionLedger ledger, string payload)
    {
        using var document = JsonDocument.Parse(payload);
        var values = new SortedDictionary<string, object>(StringComparer.Ordinal);
        foreach (var property in document.RootElement.EnumerateObject())
        {
            values[property.Name] = property.Value.Clone();
        }
        values["snapshot_id"] = ledger.SnapshotId.ToString();
        values["snapshot_version"] = ledger.SnapshotVersion;
        return JsonSerializer.Serialize(values, JsonOptions);
    }

    private static string Hash(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static string NewTraceparent()
    {
        var traceId = Guid.NewGuid().ToString("N");
        var spanId = Guid.NewGuid().ToString("N")[..16];
        return $"00-{traceId}-{spanId}-01";
    }

    private static bool IsDuplicate(V2LocalSessionLedger ledger, Guid actionId) =>
        ledger.AppliedClientActionIds.Contains(actionId);

    private static void EnsureActive(V2LocalSessionLedger ledger)
    {
        if (ledger.Status != V2LocalSessionStatus.Active)
        {
            throw new InvalidOperationException("V2 local session no longer accepts financial actions");
        }
    }

    private static bool Locks(V2LocalSessionLedger ledger) =>
        ledger.Status is V2LocalSessionStatus.Exhausted or V2LocalSessionStatus.Stopped;

    internal static DateTimeOffset TruncateToMinuteUtc(DateTimeOffset value)
    {
        var utc = value.ToUniversalTime();
        return new DateTimeOffset(
            utc.Year,
            utc.Month,
            utc.Day,
            utc.Hour,
            utc.Minute,
            0,
            TimeSpan.Zero);
    }
}
