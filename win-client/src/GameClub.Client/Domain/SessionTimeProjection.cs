namespace GameClub.Client.Domain;

/// <summary>
/// Показывает серверный прогноз до остановки сессии между snapshot-ами.
/// Расчёт не списывает деньги и не меняет порядок пакетов на сервере.
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
        var input = ProjectionInput.From(snapshot, receivedAt);
        if (input is null)
        {
            Reset();
            return;
        }

        var sourceChanged = !_initialized
            || !string.Equals(_sourceKey, input.SourceKey, StringComparison.Ordinal);
        var balanceIncreased = input.BalanceCents is not null
            && _anchorBalanceCents is not null
            && input.BalanceCents > _anchorBalanceCents;
        var current = GetRemainingMinutes(receivedAt);

        if (!sourceChanged && !balanceIncreased && current is not null)
        {
            if (input.RemainingMinutes < current.Value)
            {
                _anchorMinutes = Math.Max(0, input.RemainingMinutes);
                _anchorAt = receivedAt;
            }

            _anchorBalanceCents = input.BalanceCents;
            return;
        }

        _sourceKey = input.SourceKey;
        _anchorMinutes = Math.Max(0, input.RemainingMinutes);
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

    private sealed record ProjectionInput(string SourceKey, int RemainingMinutes, long? BalanceCents)
    {
        public static ProjectionInput? From(SessionSnapshot snapshot, DateTimeOffset now)
        {
            var packages = new[] { snapshot.ActivePackage }
                .Concat(snapshot.PackageQueue ?? Array.Empty<SessionPackageSnapshot>())
                .Where(item => item is not null && item.RemainingMinutes > 0)
                .Select(item => item!)
                .ToArray();
            if (snapshot.LoginGrantRemainingMinutes <= 0 && packages.Length == 0
                && snapshot.BalanceRemainingMinutes is not > 0)
            {
                return null;
            }

            var queueKey = string.Join(',', packages.Select(item => $"{item.Id}:{item.Status}"));
            return new(
                $"{snapshot.Id}:{queueKey}:{snapshot.LoginGrantRemainingMinutes}",
                Calculate(snapshot.LoginGrantRemainingMinutes, packages, snapshot.BalanceRemainingMinutes, now),
                snapshot.BalanceCents);
        }

        private static int Calculate(
            int grantMinutes,
            IReadOnlyList<SessionPackageSnapshot> packages,
            long? balanceMinutes,
            DateTimeOffset now)
        {
            var grant = Math.Max(0, grantMinutes);
            if (grant > 0)
            {
                return grant;
            }
            var balance = checked((int)Math.Clamp(balanceMinutes ?? 0, 0, int.MaxValue));
            var pending = packages.Select(item => item with { }).ToList();
            var active = pending.FirstOrDefault(item => item.Status.Equals("active", StringComparison.OrdinalIgnoreCase));
            var minutes = 0;

            while (grant > 0 || active is not null || pending.Count > 0 || balance > 0)
            {
                var at = now.AddMinutes(minutes);
                if (grant > 0)
                {
                    grant--;
                }
                else if (active is not null)
                {
                    if (!CanUse(active, at))
                    {
                        break;
                    }
                    active = Consume(active, pending);
                }
                else
                {
                    active = pending.FirstOrDefault(item => CanUse(item, at));
                    if (active is not null)
                    {
                        active = Consume(active, pending);
                    }
                    else if (balance > 0)
                    {
                        balance--;
                    }
                    else
                    {
                        break;
                    }
                }
                minutes++;
            }
            return minutes;
        }

        private static SessionPackageSnapshot? Consume(
            SessionPackageSnapshot package,
            ICollection<SessionPackageSnapshot> pending)
        {
            pending.Remove(package);
            if (package.RemainingMinutes == 1)
            {
                return null;
            }
            var next = package with { RemainingMinutes = package.RemainingMinutes - 1, Status = "active" };
            pending.Add(next);
            return next;
        }

        private static bool CanUse(SessionPackageSnapshot package, DateTimeOffset at)
        {
            if (package.UsageWindowStartMinute == 0 && package.UsageWindowEndMinute == 0)
            {
                return true;
            }
            if (string.IsNullOrWhiteSpace(package.WindowTimezone))
            {
                return false;
            }
            try
            {
                var local = TimeZoneInfo.ConvertTime(at, TimeZoneInfo.FindSystemTimeZoneById(package.WindowTimezone));
                var minute = local.Hour * 60 + local.Minute;
                return package.UsageWindowStartMinute < package.UsageWindowEndMinute
                    ? minute >= package.UsageWindowStartMinute && minute < package.UsageWindowEndMinute
                    : minute >= package.UsageWindowStartMinute || minute < package.UsageWindowEndMinute;
            }
            catch (TimeZoneNotFoundException)
            {
                return false;
            }
        }
    }
}
