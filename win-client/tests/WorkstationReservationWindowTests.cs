using GameClub.Client.Domain;
using Xunit;

public sealed class WorkstationReservationWindowTests
{
    [Fact]
    public void StopsOnlyASessionStartedBeforeTheActiveReservation()
    {
        var start = new DateTimeOffset(2026, 11, 16, 17, 0, 0, TimeSpan.Zero);
        var reservation = new WorkstationReservationWindow(start, start.AddHours(2));
        var previousSession = start.AddMinutes(-5);

        Assert.False(reservation.RequiresStop(previousSession, start.AddTicks(-1)));
        Assert.True(reservation.RequiresStop(previousSession, start));
        Assert.False(reservation.RequiresStop(start, start));
        Assert.False(reservation.RequiresStop(previousSession, reservation.EndsAt));
    }
}
