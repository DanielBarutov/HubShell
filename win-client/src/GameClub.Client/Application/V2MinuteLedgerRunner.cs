using GameClub.Client.Domain;

namespace GameClub.Client.Application;

/// <summary>
/// Догоняет durable V2 ledger строго по minute boundaries. После каждого
/// списания coordinator сохраняет новую границу вместе с outbox-фактом, поэтому
/// crash между минутами не может списать одну минуту дважды.
/// </summary>
public sealed class V2MinuteLedgerRunner
{
    private readonly V2LocalLedgerCoordinator _ledger;
    private readonly Func<Guid> _newActionId;

    public V2MinuteLedgerRunner(
        V2LocalLedgerCoordinator ledger,
        Func<Guid>? newActionId = null)
    {
        _ledger = ledger;
        _newActionId = newActionId ?? Guid.NewGuid;
    }

    public async Task<IReadOnlyList<V2LocalLedgerTransition>> ConsumeDueMinutesAsync(
        DateTimeOffset now,
        CancellationToken cancellationToken = default)
    {
        var current = await _ledger.ReadLedgerAsync(cancellationToken);
        if (current.ActivatedAtUtc is null)
        {
            throw new InvalidOperationException("V2 ledger has no signed activation time");
        }

        var lastBoundary = V2LocalLedgerEngine.TruncateToMinuteUtc(
            current.LastConsumedMinuteUtc ?? current.ActivatedAtUtc.Value);
        var dueBoundary = V2LocalLedgerEngine.TruncateToMinuteUtc(now);
        if (dueBoundary <= lastBoundary || current.Status != V2LocalSessionStatus.Active)
        {
            return Array.Empty<V2LocalLedgerTransition>();
        }

        var transitions = new List<V2LocalLedgerTransition>();
        for (var boundary = lastBoundary.AddMinutes(1);
             boundary <= dueBoundary;
             boundary = boundary.AddMinutes(1))
        {
            var transition = await _ledger.ConsumeMinuteBoundaryAsync(
                _newActionId(),
                boundary,
                cancellationToken);
            if (transition.IsDuplicate)
            {
                continue;
            }
            transitions.Add(transition);
            if (transition.LockWorkstation)
            {
                break;
            }
        }
        return transitions;
    }
}
