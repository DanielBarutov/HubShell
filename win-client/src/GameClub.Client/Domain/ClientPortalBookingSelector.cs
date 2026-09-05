using System.Globalization;

namespace GameClub.Client.Domain;

public static class ClientPortalBookingSelector
{
    public static ClientPortalReservation? FindUpcoming(
        IEnumerable<ClientPortalReservation> reservations,
        string? workstationId,
        DateTimeOffset now)
    {
        if (string.IsNullOrWhiteSpace(workstationId))
        {
            return null;
        }

        return reservations
            .Where(item => item.Status.Equals("confirmed", StringComparison.OrdinalIgnoreCase))
            .Where(item => item.WorkstationIds.Contains(workstationId, StringComparer.OrdinalIgnoreCase))
            .Where(item => DateTimeOffset.TryParse(
                item.StartAt,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out var start) && start > now)
            .OrderBy(item => item.StartAt, StringComparer.Ordinal)
            .FirstOrDefault();
    }
}
