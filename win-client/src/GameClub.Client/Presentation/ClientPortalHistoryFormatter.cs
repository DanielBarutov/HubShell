using System.Globalization;
using GameClub.Client.Domain;

namespace GameClub.Client.Presentation;

/// <summary>
/// Turns the server-backed portal ledger into customer-facing history lines.
/// Technical identifiers and transport enum values are intentionally never shown here.
/// </summary>
public static class ClientPortalHistoryFormatter
{
    private static readonly CultureInfo RussianCulture = CultureInfo.GetCultureInfo("ru-RU");

    public static IReadOnlyList<string> FormatBalanceOperations(ClientPortalSnapshot snapshot) =>
        snapshot.BalanceOperations
            .OrderByDescending(operation => ParseTimestamp(operation.CreatedAt))
            .Select(operation => string.Join(" · ", new[]
            {
                FormatTimestamp(operation.CreatedAt),
                FormatOperationType(operation.OperationType),
                FormatMoney(operation.AmountCents),
                FormatBalancePurpose(snapshot, operation),
            }))
            .ToArray();

    public static IReadOnlyList<string> FormatPurchases(ClientPortalSnapshot snapshot) =>
        snapshot.Purchases
            .OrderByDescending(purchase => ParseTimestamp(purchase.CreatedAt))
            .Select(purchase => string.Join(" · ", new[]
            {
                FormatTimestamp(purchase.CreatedAt),
                $"{purchase.ProductName} × {purchase.Quantity}",
                FormatMoney(purchase.TotalPriceCents),
                FormatPaymentSummary(snapshot, purchase.PaymentParts, purchase.PaymentMethod),
            }))
            .ToArray();

    public static IReadOnlyList<string> FormatCharges(ClientPortalSnapshot snapshot) =>
        snapshot.Charges
            .OrderByDescending(charge => ParseTimestamp(charge.CreatedAt))
            .Select(charge => string.Join(" · ", new[]
            {
                FormatTimestamp(charge.CreatedAt),
                string.IsNullOrWhiteSpace(charge.TariffName) ? "Игровая сессия" : charge.TariffName,
                $"{FormatDuration(charge.DurationMinutes)} игры",
                $"Списано {FormatMoney(Math.Abs(charge.AmountCents))}",
            }))
            .ToArray();

    public static IReadOnlyList<string> FormatSessions(ClientPortalSnapshot snapshot) =>
        snapshot.Sessions
            .OrderByDescending(session => ParseTimestamp(session.StartedAt))
            .Select(session => string.Join(" · ", SessionParts(session)))
            .ToArray();

    private static IEnumerable<string> SessionParts(ClientPortalSession session)
    {
        yield return FormatTimestamp(session.StartedAt);
        yield return string.IsNullOrWhiteSpace(session.WorkstationName)
            ? "Игровое место"
            : session.WorkstationName;
        yield return string.Equals(session.Status, "active", StringComparison.OrdinalIgnoreCase)
            ? "Текущая сессия"
            : "Завершена";
        if (!string.IsNullOrWhiteSpace(session.TariffName))
        {
            yield return session.TariffName;
        }

        yield return session.DurationMinutes > 0
            ? $"Всего {FormatDuration(session.DurationMinutes)}"
            : "Длительность не указана";
    }

    private static string FormatBalancePurpose(
        ClientPortalSnapshot snapshot,
        ClientPortalBalanceOperation operation)
    {
        if (string.Equals(operation.OperationType, "top_up", StringComparison.OrdinalIgnoreCase))
        {
            return FormatPaymentSummary(snapshot, operation.PaymentParts, null);
        }

        var reason = operation.Reason.Trim();
        if (reason.StartsWith("Package purchase ", StringComparison.OrdinalIgnoreCase))
        {
            var package = snapshot.Entitlements.FirstOrDefault(item =>
                reason.EndsWith(item.Id, StringComparison.OrdinalIgnoreCase));
            return string.IsNullOrWhiteSpace(package?.TariffName)
                ? "Покупка пакета времени"
                : $"Покупка пакета «{package.TariffName}" + "»";
        }

        if (reason.StartsWith("Per-minute session ", StringComparison.OrdinalIgnoreCase))
        {
            return "Поминутная игра";
        }

        if (reason.StartsWith("Gaming session ", StringComparison.OrdinalIgnoreCase))
        {
            return "Игровая сессия";
        }

        if (reason.StartsWith("Product sale ", StringComparison.OrdinalIgnoreCase))
        {
            return "Покупка товара";
        }

        return "Списание с баланса";
    }

    private static string FormatOperationType(string operationType) =>
        operationType.Trim().ToLowerInvariant() switch
        {
            "top_up" => "Пополнение баланса",
            "debit" => "Списание с баланса",
            _ => "Операция с балансом",
        };

    private static string FormatPaymentSummary(
        ClientPortalSnapshot snapshot,
        IReadOnlyList<ClientPortalPaymentPart>? parts,
        string? fallbackMethod)
    {
        var paymentParts = parts ?? Array.Empty<ClientPortalPaymentPart>();
        if (paymentParts.Count == 0)
        {
            var name = PaymentMethodName(snapshot, fallbackMethod);
            return string.IsNullOrWhiteSpace(name)
                ? "Способ оплаты не указан"
                : $"Оплата: {name}";
        }

        if (paymentParts.Count == 1)
        {
            return $"Оплата: {PaymentMethodName(snapshot, paymentParts[0].Method) ?? "Способ не указан"}";
        }

        return "Оплата: " + string.Join(
            " + ",
            paymentParts.Select(part =>
                $"{PaymentMethodName(snapshot, part.Method) ?? "Способ не указан"} {FormatMoney(part.AmountCents)}"));
    }

    private static string? PaymentMethodName(ClientPortalSnapshot snapshot, string? key)
    {
        if (string.IsNullOrWhiteSpace(key))
        {
            return null;
        }

        var configured = (snapshot.PaymentMethods ?? Array.Empty<ClientPortalPaymentMethod>())
            .FirstOrDefault(method => string.Equals(method.Key, key, StringComparison.OrdinalIgnoreCase));
        if (!string.IsNullOrWhiteSpace(configured?.Name))
        {
            return configured.Name;
        }

        return key.Trim().ToLowerInvariant() switch
        {
            "cash" => "Наличные",
            "balance" => "Баланс",
            "transfer" => "Перевод",
            "mixed" => "Смешанная оплата",
            _ => null,
        };
    }

    private static DateTimeOffset ParseTimestamp(string value) =>
        DateTimeOffset.TryParse(
            value,
            CultureInfo.InvariantCulture,
            DateTimeStyles.AssumeUniversal,
            out var timestamp)
            ? timestamp
            : DateTimeOffset.MinValue;

    private static string FormatTimestamp(string value)
    {
        var timestamp = ParseTimestamp(value);
        return timestamp == DateTimeOffset.MinValue
            ? "Дата не указана"
            : timestamp.ToLocalTime().ToString("dd.MM.yyyy HH:mm", RussianCulture);
    }

    private static string FormatMoney(long cents) => $"{(cents / 100m):N2} ₽";

    private static string FormatDuration(int minutes) =>
        $"{minutes} {RussianMinuteWord(minutes)}";

    private static string RussianMinuteWord(int minutes)
    {
        var remainder = Math.Abs(minutes) % 100;
        if (remainder is >= 11 and <= 14)
        {
            return "минут";
        }

        return (Math.Abs(minutes) % 10) switch
        {
            1 => "минута",
            >= 2 and <= 4 => "минуты",
            _ => "минут",
        };
    }
}
