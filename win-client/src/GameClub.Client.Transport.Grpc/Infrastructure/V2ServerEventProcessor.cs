using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using GameClub.Client.Application;
using GameClub.Client.Contracts.Events.V2;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// Проверяет адресное сообщение сервера и только затем меняет локальный V2
/// ledger. HTTP polling consumer вызывает этот класс до server ack: accepted/
/// duplicate уже сохранены в ClientInbox, а rejected остаётся без ack для
/// controlled review без повторного финансового действия.
/// </summary>
public sealed class V2ServerEventProcessor
{
    private readonly V2LocalLedgerCoordinator _ledger;

    public V2ServerEventProcessor(V2LocalLedgerCoordinator ledger) => _ledger = ledger;

    public async Task<EventProcessingResult> ProcessAsync(
        EventEnvelope envelope,
        CancellationToken cancellationToken = default)
    {
        try
        {
            ValidateEnvelope(envelope);
            var eventId = ParseRequiredGuid(envelope.EventId, "event_id");
            var operationId = ParseRequiredGuid(envelope.OperationId, "operation_id");
            var local = await _ledger.ReadLedgerAsync(cancellationToken);
            if (!MatchesLocalSession(envelope, local))
            {
                return await RejectAsync(
                    envelope,
                    "target_mismatch",
                    "Сообщение предназначено другой V2-сессии.",
                    cancellationToken);
            }

            var payload = ParseBalanceCreditPayload(envelope.PayloadJson, operationId);
            ValidatePayloadHash(envelope.PayloadJson, envelope.PayloadHash);
            var transition = await _ledger.ApplyBalanceCreditAsync(
                eventId,
                operationId,
                payload.AmountCents,
                cancellationToken);
            return new EventProcessingResult
            {
                EventId = envelope.EventId,
                OperationId = envelope.OperationId,
                Status = transition.IsDuplicate
                    ? V2EventProcessingStatus.Duplicate
                    : V2EventProcessingStatus.Accepted,
                ReasonCode = transition.IsDuplicate ? "already_applied" : "balance_credit_applied",
                Message = transition.IsDuplicate
                    ? "Пополнение уже есть в локальном журнале."
                    : "Пополнение сохранено в локальном журнале.",
                ProcessedAt = Google.Protobuf.WellKnownTypes.Timestamp.FromDateTime(DateTime.UtcNow),
            };
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error) when (error is ArgumentException or InvalidOperationException or JsonException or CryptographicException)
        {
            return await RejectAsync(envelope, "invalid_server_event", error.Message, cancellationToken);
        }
    }

    private async Task<EventProcessingResult> RejectAsync(
        EventEnvelope envelope,
        string reasonCode,
        string message,
        CancellationToken cancellationToken)
    {
        try
        {
            await _ledger.RecordServerEventIssueAsync(
                envelope.EventId,
                envelope.OperationId,
                reasonCode,
                message,
                cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception)
        {
            // Preserve the reject result even when the local diagnostic write
            // cannot complete during a damaged-store recovery.
        }

        return Rejected(envelope, reasonCode, message);
    }

    private static void ValidateEnvelope(EventEnvelope envelope)
    {
        if (envelope.SchemaVersion != 1)
        {
            throw new InvalidOperationException("Неизвестная версия V2 server event.");
        }
        if (envelope.EventType != V2EventType.BalanceCreditApplied)
        {
            throw new InvalidOperationException("Для локального баланса разрешён только BalanceCreditApplied.");
        }
        if (!envelope.ProducerId.StartsWith("server:", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Адресное сообщение не подтверждено серверным producer id.");
        }
        if (string.IsNullOrWhiteSpace(envelope.PayloadHash) || string.IsNullOrWhiteSpace(envelope.PayloadJson))
        {
            throw new InvalidOperationException("В server event отсутствует payload или его hash.");
        }
    }

    private static bool MatchesLocalSession(
        EventEnvelope envelope,
        GameClub.Client.Domain.V2LocalSessionLedger local) =>
        string.Equals(envelope.ClientId, local.ClientId.ToString(), StringComparison.OrdinalIgnoreCase)
        && string.Equals(envelope.SessionId, local.SessionId.ToString(), StringComparison.OrdinalIgnoreCase)
        && string.Equals(envelope.DeviceId, local.DeviceId, StringComparison.Ordinal);

    private static BalanceCreditPayload ParseBalanceCreditPayload(string json, Guid operationId)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty("amount_delta_cents", out var amount)
            || !amount.TryGetInt64(out var amountCents)
            || amountCents <= 0
            || !root.TryGetProperty("currency", out var currency)
            || !string.Equals(currency.GetString(), "RUB", StringComparison.Ordinal)
            || !root.TryGetProperty("deposit_operation_id", out var depositOperation))
        {
            throw new InvalidOperationException("Недопустимый payload пополнения V2.");
        }
        if (ParseRequiredGuid(depositOperation.GetString(), "deposit_operation_id") != operationId)
        {
            throw new InvalidOperationException("deposit_operation_id не совпадает с operation_id.");
        }
        return new BalanceCreditPayload(amountCents);
    }

    private static void ValidatePayloadHash(string payloadJson, string expectedHash)
    {
        using var document = JsonDocument.Parse(payloadJson);
        var canonical = CanonicalJson(document.RootElement);
        var actualHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
        if (!string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
        {
            throw new CryptographicException("Payload hash server event не совпадает.");
        }
    }

    private static string CanonicalJson(JsonElement element)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            WriteCanonicalJson(writer, element);
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static void WriteCanonicalJson(Utf8JsonWriter writer, JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (var property in element.EnumerateObject().OrderBy(item => item.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    WriteCanonicalJson(writer, property.Value);
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (var item in element.EnumerateArray())
                {
                    WriteCanonicalJson(writer, item);
                }
                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(element.GetString());
                break;
            case JsonValueKind.Number:
                writer.WriteRawValue(element.GetRawText());
                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Null:
                writer.WriteNullValue();
                break;
            default:
                throw new InvalidOperationException("Недопустимое JSON значение V2 payload.");
        }
    }

    private static Guid ParseRequiredGuid(string? value, string fieldName) =>
        Guid.TryParse(value, out var parsed) && parsed != Guid.Empty
            ? parsed
            : throw new InvalidOperationException($"Поле {fieldName} должно содержать UUID.");

    private static EventProcessingResult Rejected(
        EventEnvelope envelope,
        string reasonCode,
        string message) => new()
        {
            EventId = envelope.EventId,
            OperationId = envelope.OperationId,
            Status = V2EventProcessingStatus.Rejected,
            ReasonCode = reasonCode,
            Message = message,
            ProcessedAt = Google.Protobuf.WellKnownTypes.Timestamp.FromDateTime(DateTime.UtcNow),
        };

    private sealed record BalanceCreditPayload(long AmountCents);
}
