using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ClientPortalBookingSelectorTests
{
    [Fact]
    public void SelectsOnlyTheNextConfirmedBookingForCurrentWorkstation()
    {
        var now = DateTimeOffset.UtcNow;
        var selected = ClientPortalBookingSelector.FindUpcoming(
            [
                Booking("other-place", "confirmed", now.AddHours(1)),
                Booking("pc-09", "cancelled", now.AddHours(2)),
                Booking("pc-09", "confirmed", now.AddHours(3)),
                Booking("pc-09", "confirmed", now.AddHours(4)),
            ],
            "pc-09",
            now);

        Assert.NotNull(selected);
        Assert.Equal("pc-09", selected.WorkstationIds[0]);
        Assert.Equal("confirmed", selected.Status);
        Assert.Equal(now.AddHours(3).ToString("O"), selected.StartAt);
    }

    [Fact]
    public void HidesBookingWhenThereIsNoFutureConfirmedMatch()
    {
        var now = DateTimeOffset.UtcNow;

        var selected = ClientPortalBookingSelector.FindUpcoming(
            [Booking("pc-09", "completed", now.AddHours(-1))],
            "pc-09",
            now);

        Assert.Null(selected);
    }

    private static ClientPortalReservation Booking(
        string workstationId,
        string status,
        DateTimeOffset startAt) =>
        new(
            Guid.NewGuid().ToString(),
            [workstationId],
            startAt.ToString("O"),
            startAt.AddHours(1).ToString("O"),
            status,
            null);
}
