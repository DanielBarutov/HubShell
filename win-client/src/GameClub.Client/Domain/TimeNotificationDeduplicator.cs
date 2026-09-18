namespace GameClub.Client.Domain;

public sealed record TimeNotificationCandidate(
    string EventId,
    int ThresholdMinutes,
    string Message,
    bool PlaySound,
    string Sound,
    string? CustomSoundPath,
    bool ShowSystemNotification);

/// <summary>Удаляет повтор одного server-backed события при heartbeat/reconnect.</summary>
public sealed class TimeNotificationDeduplicator
{
    private readonly HashSet<string> _delivered = new(StringComparer.Ordinal);

    public IReadOnlyList<TimeNotificationCandidate> Accept(
        IEnumerable<TimeNotificationCandidate> candidates)
    {
        var result = new List<TimeNotificationCandidate>();
        foreach (var candidate in candidates)
        {
            if (string.IsNullOrWhiteSpace(candidate.EventId) || !_delivered.Add(candidate.EventId))
            {
                continue;
            }

            result.Add(candidate);
        }

        return result;
    }

    public void Reset() => _delivered.Clear();
}
