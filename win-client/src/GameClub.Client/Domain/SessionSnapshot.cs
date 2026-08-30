namespace GameClub.Client.Domain;

public sealed record SessionSnapshot(
    string Id,
    string WorkstationId,
    string? ClientId,
    string? GuestName,
    string Status,
    string StartedAt,
    string? EndedAt,
    string Source,
    string ReservationId);
