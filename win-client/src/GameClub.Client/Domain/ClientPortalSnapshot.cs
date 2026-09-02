namespace GameClub.Client.Domain;

public sealed record ClientPortalAuthenticationSnapshot(
    string AccessToken,
    int ExpiresIn,
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
    IReadOnlyList<ClientPortalEntitlement> Entitlements);

public sealed record ClientPortalBalanceOperation(
    string Id,
    string OperationType,
    long AmountCents,
    long BonusAmount,
    string Reason,
    string CreatedAt);

public sealed record ClientPortalSession(
    string Id,
    string WorkstationId,
    string Status,
    string StartedAt,
    string? EndedAt,
    string? TariffId,
    string? TariffName,
    int TariffQuantity);

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
    string CreatedAt);

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
