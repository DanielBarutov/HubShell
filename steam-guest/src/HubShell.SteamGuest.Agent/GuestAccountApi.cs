using System.Net;
using System.Net.Http.Json;
using HubShell.SteamGuest.Core;

namespace HubShell.SteamGuest.Agent;

public sealed class GuestAccountApi : IGuestAccountStore
{
    private readonly HttpClient _http;

    public GuestAccountApi(Uri serverUrl, string stationKey)
    {
        if (serverUrl.Scheme != Uri.UriSchemeHttps && !AllowsLocalHttp())
        {
            throw new InvalidOperationException("HTTP нужно явно разрешить в .env только для локальной сети клуба.");
        }
        _http = new HttpClient { BaseAddress = serverUrl };
        _http.DefaultRequestHeaders.Add("X-Steam-Guest-Station-Key", stationKey);
    }

    public Task RegisterStationAsync(string stationId, string stationKey, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("Регистрация станции выполняется администратором на сервере.");

    public Task<Guid> AddAccountAsync(SteamCredentials credentials, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("Добавление аккаунта выполняется администратором на сервере.");

    public async Task<GuestAccountLease> ClaimAsync(string stationId, string stationKey, DateTimeOffset now, CancellationToken cancellationToken = default)
    {
        using var response = await _http.PostAsJsonAsync("v1/leases/claim", new { stationId }, cancellationToken);
        if (response.StatusCode == HttpStatusCode.Unauthorized)
        {
            throw new StationAccessDeniedException();
        }
        if (response.StatusCode == HttpStatusCode.Conflict)
        {
            throw new GuestAccountUnavailableException();
        }
        response.EnsureSuccessStatusCode();
        var lease = await response.Content.ReadFromJsonAsync<LeaseResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Сервер вернул пустую аренду Steam-аккаунта.");
        return new GuestAccountLease(lease.LeaseId, Guid.Empty, stationId, new SteamCredentials(lease.Login, lease.Password), now);
    }

    public async Task<bool> ReleaseAsync(string stationId, string stationKey, Guid leaseId, DateTimeOffset now, CancellationToken cancellationToken = default)
    {
        using var response = await _http.PostAsJsonAsync($"v1/leases/{leaseId}/release", new { stationId }, cancellationToken);
        if (response.StatusCode == HttpStatusCode.Unauthorized)
        {
            throw new StationAccessDeniedException();
        }
        return response.StatusCode == HttpStatusCode.NoContent;
    }

    public async Task<bool> RenewAsync(string stationId, string stationKey, Guid leaseId, DateTimeOffset now, CancellationToken cancellationToken = default)
    {
        using var response = await _http.PostAsJsonAsync($"v1/leases/{leaseId}/confirm", new { stationId }, cancellationToken);
        if (response.StatusCode == HttpStatusCode.Unauthorized)
        {
            throw new StationAccessDeniedException();
        }
        return response.StatusCode == HttpStatusCode.NoContent;
    }

    public Task<int> ReleaseExpiredAsync(DateTimeOffset now, TimeSpan maximumSilence, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("Просроченные аренды освобождает сервер.");

    public Task<IReadOnlyCollection<GuestAccountSummary>> ListAsync(CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("Список аккаунтов доступен только администратору.");

    private static bool AllowsLocalHttp() => string.Equals(
        Environment.GetEnvironmentVariable("HUBSHELL_STEAM_ALLOW_HTTP"),
        "true",
        StringComparison.OrdinalIgnoreCase);

    private sealed record LeaseResponse(Guid LeaseId, string Login, string Password);
}
