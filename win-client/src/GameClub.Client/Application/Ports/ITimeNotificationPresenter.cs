using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface ITimeNotificationPresenter
{
    void Present(TimeNotificationCandidate candidate);
}

public sealed class NullTimeNotificationPresenter : ITimeNotificationPresenter
{
    public void Present(TimeNotificationCandidate candidate)
    {
        _ = candidate;
    }
}
