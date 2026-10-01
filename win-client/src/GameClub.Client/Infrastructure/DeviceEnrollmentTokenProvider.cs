using GameClub.Client.Application.Ports;
using DevicesV2 = GameClub.Client.Contracts.Devices.V2;
using Grpc.Core;
using Grpc.Net.Client;

namespace GameClub.Client.Infrastructure;

public sealed class DeviceEnrollmentTokenProvider : ITokenProvider, IDisposable
{
    private const int MaxEnrollmentMacAddresses = 16;
    private readonly IDeviceEnrollmentGateway _gateway;
    private readonly IDisposable? _ownedGateway;
    private readonly IReadOnlyList<string> _macAddresses;
    private readonly string _installationId;
    private readonly SemaphoreSlim _refreshLock = new(1, 1);

    private string? _accessToken;
    private DateTimeOffset _expiresAt;

    public DeviceEnrollmentTokenProvider(
        Uri grpcAddress,
        string environment,
        IDeviceEnrollmentGateway? gateway = null,
        IReadOnlyList<string>? macAddresses = null,
        string? installationId = null)
    {
        ArgumentNullException.ThrowIfNull(grpcAddress);
        var endpoint = EndpointPolicy.Validate(grpcAddress, "GAMECLUB_GRPC_ADDRESS", environment);
        _gateway = gateway ?? new GrpcDeviceEnrollmentGateway(endpoint);
        _ownedGateway = gateway is null ? (IDisposable)_gateway : null;
        _macAddresses = (macAddresses ?? MacAddressProvider.GetActiveMacAddresses())
            .Take(MaxEnrollmentMacAddresses)
            .ToArray();
        _installationId = installationId ?? InstallationIdentity.LoadOrCreate();
    }

    public string? DeviceId { get; private set; }

    public string? WorkstationId { get; private set; }

    public string? WorkstationName { get; private set; }

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

            DeviceEnrollmentSnapshot payload;
            try
            {
                payload = await _gateway.EnrollAsync(
                    _macAddresses,
                    _installationId,
                    cancellationToken);
            }
            catch (RpcException error) when (error.StatusCode == StatusCode.PermissionDenied)
            {
                throw new DeviceEnrollmentRejectedException();
            }

            if (string.Equals(payload.State, "pending", StringComparison.OrdinalIgnoreCase))
            {
                throw new DeviceEnrollmentPendingException();
            }

            if (string.Equals(payload.State, "disabled", StringComparison.OrdinalIgnoreCase))
            {
                throw new DeviceEnrollmentDisabledException();
            }

            if (!string.Equals(payload.State, "approved", StringComparison.OrdinalIgnoreCase)
                || string.IsNullOrWhiteSpace(payload.AccessToken)
                || string.IsNullOrWhiteSpace(payload.DeviceId)
                || string.IsNullOrWhiteSpace(payload.WorkstationId))
            {
                throw new InvalidOperationException("Backend returned an invalid enrollment response");
            }

            DeviceId = payload.DeviceId;
            WorkstationId = payload.WorkstationId;
            WorkstationName = payload.WorkstationName;
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
        _ownedGateway?.Dispose();
    }

    private bool HasUsableToken() =>
        !string.IsNullOrWhiteSpace(_accessToken)
        && _expiresAt > DateTimeOffset.UtcNow.AddSeconds(30);

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

public interface IDeviceEnrollmentGateway
{
    ValueTask<DeviceEnrollmentSnapshot> EnrollAsync(
        IReadOnlyList<string> macAddresses,
        string installationId,
        CancellationToken cancellationToken = default);
}

public sealed record DeviceEnrollmentSnapshot(
    string State,
    string? DeviceId,
    string? WorkstationId,
    string? WorkstationName,
    string? AccessToken,
    int ExpiresIn);

public sealed class GrpcDeviceEnrollmentGateway : IDeviceEnrollmentGateway, IDisposable
{
    private readonly GrpcChannel _channel;
    private readonly DevicesV2.DeviceControlService.DeviceControlServiceClient _client;

    public GrpcDeviceEnrollmentGateway(Uri grpcAddress)
    {
        if (string.Equals(grpcAddress.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase))
        {
            AppContext.SetSwitch("System.Net.Http.SocketsHttpHandler.Http2UnencryptedSupport", true);
        }

        _channel = GrpcChannel.ForAddress(grpcAddress);
        _client = new DevicesV2.DeviceControlService.DeviceControlServiceClient(_channel);
    }

    public async ValueTask<DeviceEnrollmentSnapshot> EnrollAsync(
        IReadOnlyList<string> macAddresses,
        string installationId,
        CancellationToken cancellationToken = default)
    {
        var request = new DevicesV2.DeviceEnrollmentRequest
        {
            InstallationId = installationId,
        };
        request.MacAddresses.AddRange(macAddresses);
        var response = await _client.EnrollAsync(
            request,
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        return new DeviceEnrollmentSnapshot(
            response.State,
            string.IsNullOrWhiteSpace(response.DeviceId) ? null : response.DeviceId,
            string.IsNullOrWhiteSpace(response.WorkstationId) ? null : response.WorkstationId,
            string.IsNullOrWhiteSpace(response.WorkstationName) ? null : response.WorkstationName,
            string.IsNullOrWhiteSpace(response.AccessToken) ? null : response.AccessToken,
            response.ExpiresIn);
    }

    public void Dispose() => _channel.Dispose();
}
