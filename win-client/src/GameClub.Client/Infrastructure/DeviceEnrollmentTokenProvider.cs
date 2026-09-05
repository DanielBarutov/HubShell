using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using GameClub.Client.Application.Ports;

namespace GameClub.Client.Infrastructure;

public sealed class DeviceEnrollmentTokenProvider : ITokenProvider, IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly bool _ownsHttpClient;
    private readonly Uri _enrollmentEndpoint;
    private readonly IReadOnlyList<string> _macAddresses;
    private readonly string _installationId;
    private readonly SemaphoreSlim _refreshLock = new(1, 1);

    private string? _accessToken;
    private DateTimeOffset _expiresAt;

    public DeviceEnrollmentTokenProvider(
        Uri authAddress,
        string environment,
        HttpClient? httpClient = null)
    {
        ArgumentNullException.ThrowIfNull(authAddress);
        _httpClient = httpClient ?? new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
        _ownsHttpClient = httpClient is null;
        _enrollmentEndpoint = new Uri(
            EndpointPolicy.Validate(authAddress, "GAMECLUB_AUTH_ADDRESS", environment),
            "/api/v1/auth/device-enrollment");
        _macAddresses = MacAddressProvider.GetActiveMacAddresses();
        _installationId = InstallationIdentity.LoadOrCreate();
    }

    public string? DeviceId { get; private set; }

    public string? WorkstationId { get; private set; }

    public bool IsEnrolled => !string.IsNullOrWhiteSpace(DeviceId) && HasUsableToken();

    public async ValueTask<string?> GetAccessTokenAsync(
        CancellationToken cancellationToken = default)
    {
        if (HasUsableToken())
        {
            return _accessToken;
        }

        await _refreshLock.WaitAsync(cancellationToken);
        try
        {
            if (HasUsableToken())
            {
                return _accessToken;
            }

            if (_macAddresses.Count == 0)
            {
                throw new DeviceEnrollmentPendingException();
            }

            using var response = await _httpClient.PostAsJsonAsync(
                _enrollmentEndpoint,
                new DeviceEnrollmentRequest(_macAddresses, _installationId),
                cancellationToken);
            if (response.StatusCode == HttpStatusCode.Conflict)
            {
                throw new DeviceEnrollmentDisabledException();
            }

            if (response.StatusCode == HttpStatusCode.Forbidden)
            {
                throw new DeviceEnrollmentRejectedException();
            }

            response.EnsureSuccessStatusCode();
            var payload = await response.Content.ReadFromJsonAsync<DeviceEnrollmentResponse>(
                cancellationToken);
            if (payload is null)
            {
                throw new InvalidOperationException("Backend returned an empty enrollment response");
            }

            if (string.Equals(payload.State, "pending", StringComparison.OrdinalIgnoreCase))
            {
                throw new DeviceEnrollmentPendingException();
            }

            if (string.Equals(payload.State, "disabled", StringComparison.OrdinalIgnoreCase))
            {
                throw new DeviceEnrollmentDisabledException();
            }

            if (!response.IsSuccessStatusCode
                || !string.Equals(payload.State, "approved", StringComparison.OrdinalIgnoreCase)
                || string.IsNullOrWhiteSpace(payload.AccessToken)
                || string.IsNullOrWhiteSpace(payload.DeviceId)
                || string.IsNullOrWhiteSpace(payload.WorkstationId))
            {
                response.EnsureSuccessStatusCode();
                throw new InvalidOperationException("Backend returned an invalid enrollment response");
            }

            DeviceId = payload.DeviceId;
            WorkstationId = payload.WorkstationId;
            _accessToken = payload.AccessToken;
            _expiresAt = DateTimeOffset.UtcNow.AddSeconds(Math.Max(payload.ExpiresIn, 1));
            return _accessToken;
        }
        finally
        {
            _refreshLock.Release();
        }
    }

    public void Dispose()
    {
        _refreshLock.Dispose();
        if (_ownsHttpClient)
        {
            _httpClient.Dispose();
        }
    }

    private bool HasUsableToken() =>
        !string.IsNullOrWhiteSpace(_accessToken)
        && _expiresAt > DateTimeOffset.UtcNow.AddSeconds(30);

    private sealed record DeviceEnrollmentRequest(
        [property: JsonPropertyName("mac_addresses")] IReadOnlyList<string> MacAddresses,
        [property: JsonPropertyName("installation_id")] string InstallationId);

    private sealed record DeviceEnrollmentResponse(
        [property: JsonPropertyName("state")] string State,
        [property: JsonPropertyName("device_id")] string? DeviceId,
        [property: JsonPropertyName("workstation_id")] string? WorkstationId,
        [property: JsonPropertyName("access_token")] string? AccessToken,
        [property: JsonPropertyName("expires_in")] int ExpiresIn);

    private static class InstallationIdentity
    {
        private static readonly string Path = System.IO.Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "GameClub",
            "Client",
            "installation-id");

        public static string LoadOrCreate()
        {
            try
            {
                var existing = File.Exists(Path) ? File.ReadAllText(Path).Trim() : string.Empty;
                if (!string.IsNullOrWhiteSpace(existing) && existing.Length <= 128)
                {
                    return existing;
                }

                Directory.CreateDirectory(System.IO.Path.GetDirectoryName(Path)!);
                var created = Guid.NewGuid().ToString("N");
                File.WriteAllText(Path, created);
                return created;
            }
            catch (IOException)
            {
                return Guid.NewGuid().ToString("N");
            }
            catch (UnauthorizedAccessException)
            {
                return Guid.NewGuid().ToString("N");
            }
        }
    }
}
