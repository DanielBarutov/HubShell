using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace GameClub.Client.Domain;

public sealed record SessionSnapshot(
    string Id,
    string WorkstationId,
    string? ClientId,
    string? GuestName,
    string Status,
    string StartedAt,
    string? EndedAt,
    string Source,
    string ReservationId,
    int LoginGrantMinutes = 0,
    string? EntitlementId = null,
    string? ZoneId = null,
    long? BalanceCents = null,
    long? BalanceBonus = null,
    SessionPackageSnapshot? ActivePackage = null,
    IReadOnlyList<SessionPackageSnapshot>? PackageQueue = null,
    SessionMeterSnapshot? Meter = null,
    string? ServerTime = null,
    string? DeviceId = null);

public sealed record SessionPackageSnapshot(
    string Id,
    string TariffId,
    string? ZoneId,
    int DurationMinutes,
    int RemainingMinutes,
    int QueuePosition,
    string Status,
    int WindowStartMinute,
    int WindowEndMinute,
    string? WindowTimezone);

public sealed record SessionMeterSnapshot(
    string SessionId,
    int BilledMinutes,
    long BilledCents,
    int PackageMinutes,
    string? ActiveEntitlementId,
    string Status,
    string UpdatedAt);

public sealed record SessionTransferOfferSnapshot(
    string Id,
    string SessionId,
    string ClientId,
    string SourceWorkstationId,
    string TargetWorkstationId,
    string Token,
    string Status,
    bool RequiresPackageBurn,
    string? Warning,
    string CreatedAt,
    string ExpiresAt,
    string? ConfirmedAt);

public sealed record SessionTransferResultSnapshot(
    SessionTransferOfferSnapshot Offer,
    SessionSnapshot Session);

public sealed record OfflineOperationSnapshot(
    string Id,
    string SessionId,
    string DeviceId,
    long Sequence,
    string Kind,
    string PayloadJson,
    int SnapshotVersion,
    string IdempotencyKey,
    string Checksum,
    DateTimeOffset CreatedAt)
{
    public static OfflineOperationSnapshot Create(
        string sessionId,
        string deviceId,
        long sequence,
        string kind,
        string payloadJson,
        int snapshotVersion,
        string idempotencyKey,
        DateTimeOffset createdAt,
        string? id = null)
    {
        using var document = JsonDocument.Parse(payloadJson);
        if (document.RootElement.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("Offline payload must be a JSON object", nameof(payloadJson));
        }

        var canonical = string.Concat(
            "{\"device_id\":", JsonSerializer.Serialize(deviceId.Trim()),
            ",\"idempotency_key\":", JsonSerializer.Serialize(idempotencyKey.Trim()),
            ",\"kind\":", JsonSerializer.Serialize(kind),
            ",\"payload\":", document.RootElement.GetRawText(),
            ",\"sequence\":", sequence,
            ",\"session_id\":", JsonSerializer.Serialize(sessionId),
            ",\"snapshot_version\":", snapshotVersion,
            "}");
        var checksum = Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
        return new OfflineOperationSnapshot(
            id ?? Guid.NewGuid().ToString(),
            sessionId,
            deviceId,
            sequence,
            kind,
            document.RootElement.GetRawText(),
            snapshotVersion,
            idempotencyKey,
            checksum,
            createdAt);
    }
}

public sealed record OfflineOperationResultSnapshot(
    string OperationId,
    long Sequence,
    string Status,
    string Message,
    string? AppliedAt);

public sealed record OfflineBatchResultSnapshot(
    string SessionId,
    IReadOnlyList<OfflineOperationResultSnapshot> Results,
    SessionSnapshot? Snapshot);
