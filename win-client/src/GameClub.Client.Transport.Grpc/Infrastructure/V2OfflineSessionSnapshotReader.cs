using GameClub.Client.Application.Ports;
using GameClub.Client.Contracts.Events.V2;
using GameClub.Client.Domain;
using Google.Protobuf;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// Проверяет подпись строго до создания local ledger. Подписывается только
/// payload, поэтому wrapper с key id и signature не влияет на байты подписи.
/// </summary>
public static class V2OfflineSessionSnapshotReader
{
    public static V2LocalSessionLedger VerifyAndCreateLedger(
        SignedOfflineSessionSnapshot snapshot,
        IOfflineSnapshotSignatureVerifier verifier)
    {
        if (snapshot.Payload is null
            || string.IsNullOrWhiteSpace(snapshot.SigningKeyId)
            || snapshot.Signature.IsEmpty)
        {
            throw new InvalidOperationException("V2 offline snapshot signature data is incomplete");
        }
        var signedBytes = SerializeDeterministic(snapshot.Payload);
        if (!verifier.Verify(snapshot.SigningKeyId, signedBytes, snapshot.Signature.Memory))
        {
            throw new InvalidOperationException("V2 offline snapshot signature is invalid");
        }

        var payload = snapshot.Payload;
        if (payload.SchemaVersion != 1 || payload.SnapshotVersion < 1 || payload.IssuedAt is null)
        {
            throw new InvalidOperationException("V2 offline snapshot version is invalid");
        }
        return V2LocalSessionLedger.Create(
            snapshotVersion: checked((int)payload.SnapshotVersion),
            clientId: ParseGuid(payload.ClientId, "client id"),
            sessionId: ParseGuid(payload.SessionId, "session id"),
            deviceId: payload.DeviceId,
            zoneId: payload.HasWorkstationZoneId ? payload.WorkstationZoneId : null,
            balanceCents: payload.BalanceCents,
            debtLimitCents: payload.DebtLimitCents,
            loginGrantRemainingMinutes: checked((int)payload.LoginGrantRemainingMinutes),
            packages: payload.Packages.Select(ToPackage).ToArray(),
            tariffs: payload.Tariffs.Select(ToTariff).ToArray(),
            snapshotId: ParseGuid(payload.SnapshotId, "snapshot id"),
            activatedAtUtc: new DateTimeOffset(payload.IssuedAt.ToDateTime()));
    }

    public static byte[] SerializeDeterministic(OfflineSessionSnapshotPayload payload)
    {
        using var stream = new MemoryStream();
        using var output = new CodedOutputStream(stream, leaveOpen: true)
        {
            Deterministic = true,
        };
        payload.WriteTo(output);
        output.Flush();
        return stream.ToArray();
    }

    public static V2LocalSessionLedger VerifyAndCreateGuestLedger(
        SignedGuestSessionAccess snapshot,
        IOfflineSnapshotSignatureVerifier verifier,
        string? expectedDeviceId = null)
    {
        if (snapshot.Payload is null
            || string.IsNullOrWhiteSpace(snapshot.SigningKeyId)
            || snapshot.Signature.IsEmpty)
        {
            throw new InvalidOperationException("V2 guest access signature data is incomplete");
        }
        var signedBytes = SerializeDeterministic(snapshot.Payload);
        if (!verifier.Verify(snapshot.SigningKeyId, signedBytes, snapshot.Signature.Memory))
        {
            throw new InvalidOperationException("V2 guest access signature is invalid");
        }
        var payload = snapshot.Payload;
        if (payload.SchemaVersion != 1 || payload.IssuedAt is null || payload.ExpiresAt is null
            || string.IsNullOrWhiteSpace(payload.GuestName)
            || (expectedDeviceId is not null
                && !string.Equals(payload.DeviceId, expectedDeviceId, StringComparison.Ordinal)))
        {
            throw new InvalidOperationException("V2 guest access payload is invalid");
        }
        var paymentId = ParseGuid(payload.PaymentId, "payment id");
        var sessionId = ParseGuid(payload.SessionId, "session id");
        var grantId = ParseGuid(payload.GrantId, "grant id");
        if (payload.TariffQuantity < 1 || payload.DurationMinutes < 1)
        {
            throw new InvalidOperationException("V2 guest access duration is invalid");
        }
        var minutes = checked((int)payload.DurationMinutes * (int)payload.TariffQuantity);
        var package = new V2LocalPackage(
            grantId.ToString(),
            payload.TariffId,
            payload.HasWorkstationZoneId ? payload.WorkstationZoneId : null,
            minutes,
            V2LocalPackageStatus.Active);
        return V2LocalSessionLedger.Create(
            snapshotVersion: 1,
            clientId: Guid.Empty,
            sessionId: sessionId,
            deviceId: payload.DeviceId,
            zoneId: payload.HasWorkstationZoneId ? payload.WorkstationZoneId : null,
            balanceCents: 0,
            debtLimitCents: 0,
            loginGrantRemainingMinutes: 0,
            packages: new[] { package },
            tariffs: Array.Empty<V2LocalTariff>(),
            snapshotId: grantId,
            activatedAtUtc: new DateTimeOffset(payload.IssuedAt.ToDateTime()),
            guestName: payload.GuestName,
            guestPaymentId: paymentId);
    }

    public static byte[] SerializeDeterministic(GuestSessionAccessPayload payload)
    {
        using var stream = new MemoryStream();
        using var output = new CodedOutputStream(stream, leaveOpen: true) { Deterministic = true };
        payload.WriteTo(output);
        output.Flush();
        return stream.ToArray();
    }

    private static V2LocalPackage ToPackage(OfflinePackageSnapshot package) =>
        new(
            package.PackageId,
            package.TariffId,
            package.HasZoneId ? package.ZoneId : null,
            checked((int)package.RemainingMinutes),
            package.Status switch
            {
                OfflinePackageStatus.Active => V2LocalPackageStatus.Active,
                OfflinePackageStatus.Queued => V2LocalPackageStatus.Queued,
                OfflinePackageStatus.Exhausted => V2LocalPackageStatus.Exhausted,
                OfflinePackageStatus.Burned => V2LocalPackageStatus.Burned,
                _ => throw new InvalidOperationException("V2 offline package status is invalid"),
            });

    private static V2LocalTariff ToTariff(OfflineTariffSnapshot tariff) =>
        new(
            tariff.TariffId,
            tariff.Name,
            tariff.HasZoneId ? tariff.ZoneId : null,
            checked((int)tariff.PackageMinutes),
            tariff.PackagePriceCents,
            tariff.PerMinutePriceCents,
            tariff.IsPurchasable);

    private static Guid ParseGuid(string value, string fieldName) =>
        Guid.TryParse(value, out var result)
            ? result
            : throw new InvalidOperationException($"V2 offline snapshot {fieldName} is invalid");
}
