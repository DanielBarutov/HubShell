namespace GameClub.Client.Domain;

/// <summary>
/// Projects a server-authoritative remaining-minute value between snapshots.
/// It never performs billing and only controls presentation.
/// </summary>
public sealed class SessionTimeProjection
{
    private string? _sourceKey;
    private int _anchorMinutes;
    private DateTimeOffset _anchorAt;
    private long? _anchorBalanceCents;
    private bool _initialized;

    public void Reset()
    {
        _sourceKey = null;
        _anchorMinutes = 0;
        _anchorAt = default;
        _anchorBalanceCents = null;
        _initialized = false;
    }

    public void Apply(SessionSnapshot snapshot, DateTimeOffset receivedAt)
    {
        var input = ProjectionInput.From(snapshot);
        if (input is null)
        {
            Reset();
            return;
        }

        var sourceChanged = !_initialized
            || !string.Equals(_sourceKey, input.SourceKey, StringComparison.Ordinal);
        var balanceChanged = input.SourceKey == "per-minute-balance"
            && input.BalanceCents != _anchorBalanceCents;
        var current = GetRemainingMinutes(receivedAt);
        var nextMinutes = input.RemainingMinutes;

        if (!sourceChanged && !balanceChanged && current is not null)
        {
            nextMinutes = Math.Min(nextMinutes, current.Value);
        }

        _sourceKey = input.SourceKey;
        _anchorMinutes = Math.Max(0, nextMinutes);
        _anchorAt = receivedAt;
        _anchorBalanceCents = input.BalanceCents;
        _initialized = true;
    }

    public int? GetRemainingMinutes(DateTimeOffset now)
    {
        if (!_initialized)
        {
            return null;
        }

        var elapsedMinutes = Math.Max(
            0,
            (int)Math.Floor((now - _anchorAt).TotalMinutes));
        return Math.Max(0, _anchorMinutes - elapsedMinutes);
    }

    private sealed record ProjectionInput(
        string SourceKey,
        int RemainingMinutes,
        long? BalanceCents)
    {
        public static ProjectionInput? From(SessionSnapshot snapshot)
        {
            if (snapshot.LoginGrantRemainingMinutes > 0)
            {
                return new("login-grant", snapshot.LoginGrantRemainingMinutes, snapshot.BalanceCents);
            }

            if (snapshot.ActivePackage is not null)
            {
                return new(
                    $"package:{snapshot.ActivePackage.Id}",
                    snapshot.ActivePackage.RemainingMinutes,
                    snapshot.BalanceCents);
            }

            if (snapshot.ActiveTariff is not null
                && snapshot.ActiveTariff.BillingMode == "block")
            {
                return new(
                    $"tariff:{snapshot.ActiveTariff.Id}",
                    snapshot.ActiveTariff.RemainingMinutes,
                    snapshot.BalanceCents);
            }

            if (snapshot.BalanceRemainingMinutes is not null)
            {
                return new(
                    "per-minute-balance",
                    checked((int)Math.Max(0, snapshot.BalanceRemainingMinutes.Value)),
                    snapshot.BalanceCents);
            }

            return null;
        }
    }
}
