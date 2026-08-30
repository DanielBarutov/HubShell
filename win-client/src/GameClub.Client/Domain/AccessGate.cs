namespace GameClub.Client.Domain;

public enum AccessMode
{
    Locked,
    SessionLocked,
    User,
    Maintenance,
}

public sealed record AccessGateSnapshot(
    AccessMode Mode,
    DateTimeOffset LastActivityAt,
    string Message);
