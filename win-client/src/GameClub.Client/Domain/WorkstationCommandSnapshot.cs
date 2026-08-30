namespace GameClub.Client.Domain;

public sealed record WorkstationCommandSnapshot(
    string Id,
    string WorkstationId,
    string CommandType,
    string PayloadJson,
    string IdempotencyKey,
    string Status,
    string AcknowledgementMessage,
    string ExpiresAt)
{
    public bool IsExpired(DateTimeOffset now)
    {
        if (string.IsNullOrWhiteSpace(ExpiresAt))
        {
            return false;
        }

        return !DateTimeOffset.TryParse(ExpiresAt, out var expiresAt) || expiresAt <= now;
    }
}
