namespace HubShell.SteamGuest.Core;

public enum GuestAccountState
{
    Available,
    Leased,
    Blocked,
    NeedsReview,
}

public sealed record SteamCredentials(string Login, string Password);

public sealed record GuestAccountLease(
    Guid LeaseId,
    Guid AccountId,
    string StationId,
    SteamCredentials Credentials,
    DateTimeOffset LeasedAt);

public sealed record GuestAccountSummary(
    Guid AccountId,
    string Login,
    GuestAccountState State,
    string? StationId,
    DateTimeOffset? LeasedAt);

public sealed class GuestAccountUnavailableException : Exception
{
    public GuestAccountUnavailableException() : base("Нет свободного гостевого Steam-аккаунта.")
    {
    }
}

public sealed class StationAccessDeniedException : Exception
{
    public StationAccessDeniedException() : base("Станция не зарегистрирована или ключ неверен.")
    {
    }
}
