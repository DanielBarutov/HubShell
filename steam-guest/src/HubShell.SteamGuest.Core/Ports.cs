namespace HubShell.SteamGuest.Core;

public interface IGuestAccountStore
{
    Task RegisterStationAsync(string stationId, string stationKey, CancellationToken cancellationToken = default);

    Task<Guid> AddAccountAsync(SteamCredentials credentials, CancellationToken cancellationToken = default);

    Task<GuestAccountLease> ClaimAsync(
        string stationId,
        string stationKey,
        DateTimeOffset now,
        CancellationToken cancellationToken = default);

    Task<bool> ReleaseAsync(
        string stationId,
        string stationKey,
        Guid leaseId,
        DateTimeOffset now,
        CancellationToken cancellationToken = default);

    Task<bool> RenewAsync(
        string stationId,
        string stationKey,
        Guid leaseId,
        DateTimeOffset now,
        CancellationToken cancellationToken = default);

    Task<int> ReleaseExpiredAsync(
        DateTimeOffset now,
        TimeSpan maximumSilence,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyCollection<GuestAccountSummary>> ListAsync(CancellationToken cancellationToken = default);
}

public interface ISteamProcess
{
    Task StopAsync(CancellationToken cancellationToken = default);

    Task WaitForExitAsync(CancellationToken cancellationToken = default);
}

public interface ISteamLauncher
{
    Task<ISteamProcess> StartAsync(SteamCredentials credentials, CancellationToken cancellationToken = default);
}
