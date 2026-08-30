using System.Net.Http.Json;
using System.Text.Json.Serialization;
using GameClub.Client.Application.Ports;

namespace GameClub.Client.Infrastructure;

public sealed class DeviceBootstrapTokenProvider : ITokenProvider, IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly bool _ownsHttpClient;
    private readonly Uri _tokenEndpoint;
    private readonly string _deviceId;
    private readonly string _bootstrapToken;
    private readonly SemaphoreSlim _refreshLock = new(1, 1);

    private string? _accessToken;
    private DateTimeOffset _expiresAt;

    public DeviceBootstrapTokenProvider(
        Uri authAddress,
        string deviceId,
        string bootstrapToken,
        HttpClient? httpClient = null,
        string environment = "dev")
    {
        ArgumentNullException.ThrowIfNull(authAddress);
        _deviceId = RequireValue(deviceId, nameof(deviceId));
        _bootstrapToken = RequireValue(bootstrapToken, nameof(bootstrapToken));
        _httpClient = httpClient ?? new HttpClient();
        _ownsHttpClient = httpClient is null;
        _tokenEndpoint = new Uri(
            EndpointPolicy.Validate(authAddress, "GAMECLUB_AUTH_ADDRESS", environment),
            "/api/v1/auth/device-token");
    }

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

            using var response = await _httpClient.PostAsJsonAsync(
                _tokenEndpoint,
                new DeviceTokenRequest(_deviceId, _bootstrapToken),
                cancellationToken);
            response.EnsureSuccessStatusCode();

            var payload = await response.Content.ReadFromJsonAsync<TokenResponse>(
                cancellationToken);
            if (payload is null || string.IsNullOrWhiteSpace(payload.AccessToken))
            {
                throw new InvalidOperationException("Backend вернул пустой device JWT");
            }

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

    private static string RequireValue(string value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("Значение не может быть пустым", parameterName);
        }

        return value.Trim();
    }

    private sealed record DeviceTokenRequest(
        [property: JsonPropertyName("device_id")] string DeviceId,
        [property: JsonPropertyName("bootstrap_token")] string BootstrapToken);

    private sealed record TokenResponse(
        [property: JsonPropertyName("access_token")] string AccessToken,
        [property: JsonPropertyName("expires_in")] int ExpiresIn);
}
