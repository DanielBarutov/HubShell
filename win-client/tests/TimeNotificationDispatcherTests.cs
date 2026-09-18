using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class TimeNotificationDispatcherTests
{
    [Fact]
    public void DispatchesServerEventOnceAndSendsItToPresenter()
    {
        var presenter = new RecordingPresenter();
        var dispatcher = new TimeNotificationDispatcher(presenter);
        var notification = new TimeNotificationSnapshot(
            "server-event-5",
            5,
            "До окончания 5 минут",
            true,
            "standard",
            null,
            true);

        var first = dispatcher.Dispatch([notification]);
        var repeated = dispatcher.Dispatch([notification]);

        Assert.Single(first);
        Assert.Empty(repeated);
        Assert.Single(presenter.Items);
        Assert.Equal("server-event-5", presenter.Items[0].EventId);
    }

    private sealed class RecordingPresenter : ITimeNotificationPresenter
    {
        public List<TimeNotificationCandidate> Items { get; } = [];

        public void Present(TimeNotificationCandidate candidate) => Items.Add(candidate);
    }
}
