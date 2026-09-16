namespace GameClub.Client.Domain;

public sealed record ClientPortalAuthenticationSnapshot(
    string AccessToken,
    int ExpiresIn,
    bool PasswordResetRequired,
    ClientPortalSnapshot Snapshot);

public sealed record ClientPortalSnapshot(
    string ClientId,
    string Nickname,
    string Phone,
    long BalanceCents,
    long BalanceBonus,
    long AvailableTimeMinutes,
    IReadOnlyList<ClientPortalBalanceOperation> BalanceOperations,
    IReadOnlyList<ClientPortalSession> Sessions,
    IReadOnlyList<ClientPortalCharge> Charges,
    IReadOnlyList<ClientPortalPurchase> Purchases,
    IReadOnlyList<ClientPortalEntitlement> Entitlements,
    IReadOnlyList<ClientPortalTariff> Tariffs,
    IReadOnlyList<ClientPortalReservation> Reservations,
    IReadOnlyList<ClientPortalPaymentMethod>? PaymentMethods = null);

public sealed record ClientPortalPaymentMethod(string Key, string Name);

public sealed record ClientPortalPaymentPart(string Method, long AmountCents, string? Reference);

public sealed record ClientPortalBalanceOperation(
    string Id,
    string OperationType,
    long AmountCents,
    long BonusAmount,
    string Reason,
    string CreatedAt,
    IReadOnlyList<ClientPortalPaymentPart>? PaymentParts = null);

public sealed record ClientPortalSession(
    string Id,
    string WorkstationId,
    string Status,
    string StartedAt,
    string? EndedAt,
    string? TariffId,
    string? TariffName,
    int TariffQuantity,
    string? WorkstationName = null,
    int DurationMinutes = 0);

public sealed record ClientPortalCharge(
    string Id,
    string SessionId,
    string TariffId,
    int DurationMinutes,
    long AmountCents,
    string? TariffName,
    string CreatedAt);

public sealed record ClientPortalPurchase(
    string Id,
    string ProductName,
    int Quantity,
    long TotalPriceCents,
    string PaymentMethod,
    string CreatedAt,
    IReadOnlyList<ClientPortalPaymentPart>? PaymentParts = null);

public sealed record ClientPortalEntitlement(
    string Id,
    string TariffId,
    string? ZoneId,
    string Status,
    int DurationMinutes,
    int RemainingMinutes,
    long PriceCents,
    int QueuePosition,
    string? TariffName,
    string PurchasedAt,
    string? ActivatedAt);

public sealed record ClientPortalTariff(
    string Id,
    string Name,
    string? ZoneId,
    int DurationMinutes,
    long PriceCents)
{
    public string DurationSummary => $"{DurationMinutes} мин";
    public string PriceSummary => $"{(PriceCents / 100m):N0} ₽";
}

public sealed record ClientPortalReservation(
    string Id,
    IReadOnlyList<string> WorkstationIds,
    string StartAt,
    string EndAt,
    string Status,
    string? TariffId);
