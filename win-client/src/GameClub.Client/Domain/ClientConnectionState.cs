namespace GameClub.Client.Domain;

public enum ClientConnectionState
{
    Connecting,
    Online,
    Reconnecting,
    Offline,
    AuthenticationRequired,
    WaitingForAssignment,
}

public sealed record ClientConnectionSnapshot(
    ClientConnectionState State,
    string Message,
    DateTimeOffset? LastSuccessfulContact,
    string BackendVersion);
