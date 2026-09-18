using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Application;

public sealed class TimeNotificationDispatcher
{
    private readonly TimeNotificationDeduplicator _deduplicator = new();
    private readonly ITimeNotificationPresenter _presenter;

    public TimeNotificationDispatcher(ITimeNotificationPresenter? presenter = null)
    {
        _presenter = presenter ?? new NullTimeNotificationPresenter();
    }

    public IReadOnlyList<TimeNotificationCandidate> Dispatch(
        IEnumerable<TimeNotificationSnapshot>? notifications)
    {
        var candidates = (notifications ?? [])
            .Select(item => new TimeNotificationCandidate(
                item.Id,
                item.ThresholdMinutes,
                item.Message,
                item.PlaySound,
                item.Sound,
                item.CustomSoundPath,
                item.ShowSystemNotification))
            .ToArray();
        var accepted = _deduplicator.Accept(candidates);
        foreach (var candidate in accepted)
        {
            _presenter.Present(candidate);
        }

        return accepted;
    }

    public void Reset() => _deduplicator.Reset();
}
