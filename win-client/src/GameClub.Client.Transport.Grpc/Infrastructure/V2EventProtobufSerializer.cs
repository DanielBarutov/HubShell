using GameClub.Client.Contracts.Events.V2;
using GameClub.Client.Domain;
using Google.Protobuf.WellKnownTypes;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// Переводит уже зафиксированный local fact в общий V2 Protobuf-конверт. Этот
/// класс не открывает Kafka-соединение и не меняет содержимое факта.
/// </summary>
public static class V2EventProtobufSerializer
{
    public static EventEnvelope Serialize(V2LocalFact fact)
    {
        var envelope = new EventEnvelope
        {
            EventId = fact.EventId.ToString(),
            OperationId = fact.OperationId.ToString(),
            EventType = ParseEventType(fact.EventType),
            SchemaVersion = 1,
            ProducerId = $"workstation:{fact.DeviceId}",
            ClientId = fact.ClientId.ToString(),
            SessionId = fact.SessionId.ToString(),
            DeviceId = fact.DeviceId,
            Sequence = checked((ulong)fact.Sequence),
            OccurredAt = Timestamp.FromDateTimeOffset(fact.OccurredAt),
            CausationId = fact.CausationId.ToString(),
            CorrelationId = fact.CorrelationId.ToString(),
            Traceparent = fact.Traceparent,
            PayloadHash = fact.PayloadHash,
            PayloadJson = fact.PayloadJson,
        };

        // previous_hash необязателен в общем контракте. Пустая строка всё равно
        // считается переданным значением в proto3 и делает первый факт недействительным.
        if (!string.IsNullOrWhiteSpace(fact.PreviousHash))
        {
            envelope.PreviousHash = fact.PreviousHash;
        }

        return envelope;
    }

    private static V2EventType ParseEventType(string value) => value switch
    {
        "login_requested" => V2EventType.LoginRequested,
        "login_snapshot_issued" => V2EventType.LoginSnapshotIssued,
        "login_grant_consumed" => V2EventType.LoginGrantConsumed,
        "login_grant_burned" => V2EventType.LoginGrantBurned,
        "package_purchased" => V2EventType.PackagePurchased,
        "package_consumed" => V2EventType.PackageConsumed,
        "per_minute_debit" => V2EventType.PerMinuteDebit,
        "bonus_payment_disabled" => V2EventType.BonusPaymentDisabled,
        "package_burned" => V2EventType.PackageBurned,
        "session_stopped" => V2EventType.SessionStopped,
        "balance_credit_applied" => V2EventType.BalanceCreditApplied,
        "reconciliation_completed" => V2EventType.ReconciliationCompleted,
        _ => throw new InvalidOperationException("Unsupported V2 local event type"),
    };
}
