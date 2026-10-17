using GameClub.Client.Contracts.Events.V2;
using GameClub.Client.Domain;

namespace GameClub.Client.Infrastructure;

internal static class V2PortalSnapshotMapper
{
    public static ClientPortalSnapshot ToDomain(OfflinePortalSnapshot source) =>
        new(
            source.ClientId,
            source.Nickname,
            source.Phone,
            source.BalanceCents,
            source.BalanceBonus,
            (int)source.AvailableTimeMinutes,
            source.BalanceOperations.Select(ToBalanceOperation).ToArray(),
            source.Sessions.Select(ToSession).ToArray(),
            source.Charges.Select(ToCharge).ToArray(),
            source.Purchases.Select(ToPurchase).ToArray(),
            source.Entitlements.Select(ToEntitlement).ToArray(),
            source.Tariffs.Select(ToTariff).ToArray(),
            source.Reservations.Select(ToReservation).ToArray(),
            source.PaymentMethods
                .Select(item => new ClientPortalPaymentMethod(item.Key, item.Name))
                .ToArray(),
            BonusWallet: source.BonusWallet is { } wallet
                ? new(wallet.TotalCents, wallet.AvailableCents, wallet.ReservedCents, wallet.PendingCents)
                : null);

    private static ClientPortalBalanceOperation ToBalanceOperation(OfflineBalanceOperation item) =>
        new(
            item.Id,
            item.OperationType,
            item.AmountCents,
            item.BonusAmount,
            item.Reason,
            item.CreatedAt,
            item.PaymentParts.Select(ToPaymentPart).ToArray());

    private static ClientPortalSession ToSession(OfflinePortalSession item) =>
        new(
            item.Id,
            item.WorkstationId,
            item.Status,
            item.StartedAt,
            string.IsNullOrWhiteSpace(item.EndedAt) ? null : item.EndedAt,
            string.IsNullOrWhiteSpace(item.TariffId) ? null : item.TariffId,
            string.IsNullOrWhiteSpace(item.TariffName) ? null : item.TariffName,
            (int)item.TariffQuantity,
            string.IsNullOrWhiteSpace(item.WorkstationName) ? null : item.WorkstationName,
            (int)item.DurationMinutes);

    private static ClientPortalCharge ToCharge(OfflinePortalCharge item) =>
        new(
            item.Id,
            item.SessionId,
            item.TariffId,
            (int)item.DurationMinutes,
            item.AmountCents,
            string.IsNullOrWhiteSpace(item.TariffName) ? null : item.TariffName,
            item.CreatedAt);

    private static ClientPortalPurchase ToPurchase(OfflinePortalPurchase item) =>
        new(
            item.Id,
            item.ProductName,
            (int)item.Quantity,
            item.TotalPriceCents,
            item.PaymentMethod,
            item.CreatedAt,
            item.PaymentParts.Select(ToPaymentPart).ToArray());

    private static ClientPortalEntitlement ToEntitlement(OfflinePortalEntitlement item) =>
        new(
            item.Id,
            item.TariffId,
            string.IsNullOrWhiteSpace(item.ZoneId) ? null : item.ZoneId,
            item.Status,
            (int)item.DurationMinutes,
            (int)item.RemainingMinutes,
            item.PriceCents,
            (int)item.QueuePosition,
            string.IsNullOrWhiteSpace(item.TariffName) ? null : item.TariffName,
            item.PurchasedAt,
            string.IsNullOrWhiteSpace(item.ActivatedAt) ? null : item.ActivatedAt,
            item.TimeRestricted,
            item.SaleWindowStartMinute == 0 ? null : (int)item.SaleWindowStartMinute,
            item.SaleWindowEndMinute == 0 ? null : (int)item.SaleWindowEndMinute,
            item.UsageWindowStartMinute == 0 ? null : (int)item.UsageWindowStartMinute,
            item.UsageWindowEndMinute == 0 ? null : (int)item.UsageWindowEndMinute,
            string.IsNullOrWhiteSpace(item.WindowTimezone) ? null : item.WindowTimezone,
            item.Audience);

    private static ClientPortalTariff ToTariff(OfflinePortalTariff item) =>
        new(
            item.Id,
            item.Name,
            string.IsNullOrWhiteSpace(item.ZoneId) ? null : item.ZoneId,
            (int)item.DurationMinutes,
            item.PriceCents,
            item.TimeRestricted,
            item.SaleWindowStartMinute == 0 ? null : (int)item.SaleWindowStartMinute,
            item.SaleWindowEndMinute == 0 ? null : (int)item.SaleWindowEndMinute,
            item.UsageWindowStartMinute == 0 ? null : (int)item.UsageWindowStartMinute,
            item.UsageWindowEndMinute == 0 ? null : (int)item.UsageWindowEndMinute,
            string.IsNullOrWhiteSpace(item.WindowTimezone) ? null : item.WindowTimezone,
            item.Audience);

    private static ClientPortalReservation ToReservation(OfflinePortalReservation item) =>
        new(
            item.Id,
            item.WorkstationIds.ToArray(),
            item.StartAt,
            item.EndAt,
            item.Status,
            string.IsNullOrWhiteSpace(item.TariffId) ? null : item.TariffId);

    private static ClientPortalPaymentPart ToPaymentPart(OfflinePaymentPart item) =>
        new(item.Method, item.AmountCents, string.IsNullOrWhiteSpace(item.Reference) ? null : item.Reference);
}
