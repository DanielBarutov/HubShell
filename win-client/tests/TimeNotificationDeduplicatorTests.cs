using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class TimeNotificationDeduplicatorTests
{
    [Fact]
    public void SameServerEventIsDeliveredOnlyOnceAcrossHeartbeats()
    {
        var deduplicator = new TimeNotificationDeduplicator();
        var candidate = new TimeNotificationCandidate(
            "event-5-minutes",
            5,
            "Осталось 5 минут",
            true,
            "standard",
            null,
            true);

        var first = deduplicator.Accept([candidate]);
        var repeated = deduplicator.Accept([candidate]);

        Assert.Single(first);
        Assert.Empty(repeated);
    }

    [Fact]
    public void DifferentSourceOrThresholdEventIsNotCollapsed()
    {
        var deduplicator = new TimeNotificationDeduplicator();
        var package = new TimeNotificationCandidate(
            "package-5",
            5,
            "Пакет заканчивается",
            true,
            "standard",
            null,
            false);
        var balance = package with { EventId = "balance-5" };

        var accepted = deduplicator.Accept([package, balance]);

        Assert.Equal(2, accepted.Count);
    }
}
