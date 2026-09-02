namespace GameClub.Client.Domain;

public sealed record EntryDecisionSnapshot(
    bool Allowed,
    string Reason,
    string? ReservationId,
    string? AssignedClientId,
    DateTimeOffset? StartsAt,
    DateTimeOffset? EndsAt);
