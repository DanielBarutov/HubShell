using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using DevicesV2 = GameClub.Client.Contracts.Devices.V2;
using Grpc.Core;
using Grpc.Net.Client;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// V2-only device bootstrap. It intentionally has no HTTP or V1 endpoint.
/// </summary>
public sealed class V2DeviceEnrollmentTokenProvider : ITokenProvider, IDisposable
{
    private const int MaxEnrollmentMacAddresses = 16;
    private readonly GrpcChannel _channel;
    private readonly DevicesV2.DeviceControlService.DeviceControlServiceClient _client;
    private readonly IReadOnlyList<string> _macAddresses;
    private readonly string _installationId;
    private readonly SemaphoreSlim _refreshLock = new(1, 1);
    private string? _accessToken;
    private DateTimeOffset _expiresAt;

    public V2DeviceEnrollmentTokenProvider(Uri grpcAddress, string environment)
    {
        var endpoint = EndpointPolicy.Validate(grpcAddress, "GAMECLUB_GRPC_ADDRESS", environment);
        if (string.Equals(endpoint.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase))
        {
            AppContext.SetSwitch("System.Net.Http.SocketsHttpHandler.Http2UnencryptedSupport", true);
        }
        _channel = GrpcChannel.ForAddress(endpoint);
        _client = new DevicesV2.DeviceControlService.DeviceControlServiceClient(_channel);
        _macAddresses = MacAddressProvider.GetActiveMacAddresses()
            .Take(MaxEnrollmentMacAddresses)
            .ToArray();
        _installationId = LoadOrCreateInstallationId();
    }

    public string? DeviceId { get; private set; }
    public string? WorkstationId { get; private set; }
    public string? WorkstationName { get; private set; }

    public async ValueTask<string?> GetAccessTokenAsync(CancellationToken cancellationToken = default)
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
            DevicesV2.DeviceEnrollmentResponse response;
            try
            {
                var request = new DevicesV2.DeviceEnrollmentRequest { InstallationId = _installationId };
                request.MacAddresses.AddRange(_macAddresses);
                response = await _client.EnrollAsync(
                    request,
                    deadline: DateTime.UtcNow.AddSeconds(10),
                    cancellationToken: cancellationToken);
            }
            catch (RpcException error) when (error.StatusCode == StatusCode.PermissionDenied)
            {
                ClientLog.RpcFailure("enrollment", error, "device enrollment");
                throw new DeviceEnrollmentRejectedException();
            }
            catch (RpcException error)
            {
                ClientLog.RpcFailure("enrollment", error, "device enrollment");
                throw;
            }

            if (string.Equals(response.State, "pending", StringComparison.OrdinalIgnoreCase))
            {
                ClientLog.Info("enrollment", "backend returned state=pending");
                throw new DeviceEnrollmentPendingException();
            }
            if (string.Equals(response.State, "disabled", StringComparison.OrdinalIgnoreCase))
            {
                ClientLog.Warning("enrollment", "backend returned state=disabled");
                throw new DeviceEnrollmentDisabledException();
            }
            if (!string.Equals(response.State, "approved", StringComparison.OrdinalIgnoreCase)
                || string.IsNullOrWhiteSpace(response.AccessToken)
                || string.IsNullOrWhiteSpace(response.DeviceId)
                || string.IsNullOrWhiteSpace(response.WorkstationId))
            {
                throw new InvalidOperationException("Backend returned an invalid V2 enrollment response.");
            }

            DeviceId = response.DeviceId;
            WorkstationId = response.WorkstationId;
            WorkstationName = response.WorkstationName;
            _accessToken = response.AccessToken;
            _expiresAt = DateTimeOffset.UtcNow.AddSeconds(Math.Max(response.ExpiresIn, 1));
            ClientLog.Info("enrollment", "backend returned state=approved");
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
        _channel.Dispose();
    }

    private bool HasUsableToken() =>
        !string.IsNullOrWhiteSpace(_accessToken)
        && _expiresAt > DateTimeOffset.UtcNow.AddSeconds(30);

    private static string LoadOrCreateInstallationId()
    {
        var path = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "GameClub", "Client", "installation-id");
        try
        {
            var existing = File.Exists(path) ? File.ReadAllText(path).Trim() : string.Empty;
            if (!string.IsNullOrWhiteSpace(existing) && existing.Length <= 128)
            {
                return existing;
            }
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var created = Guid.NewGuid().ToString("N");
            File.WriteAllText(path, created);
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
