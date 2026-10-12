using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using DevicesV2 = GameClub.Client.Contracts.Devices.V2;
using OfflineSessionsV2 = GameClub.Client.Contracts.Events.V2.OfflineSessionService;
using Grpc.Core;
using Grpc.Net.Client;
using Google.Protobuf.WellKnownTypes;
using System.Runtime.CompilerServices;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// Транспорт Windows-релиза V2. Он не содержит клиентов V1 protobuf;
/// унаследованные порты V1 безопасно отказывают при ошибочном старом вызове.
/// </summary>
public sealed class V2GrpcBackendClient : IBackendClient, IV2OfflineSessionGateway, IV2GuestSessionGateway, IV2ClientPortalGateway
{
    private readonly GrpcChannel _channel;
    private readonly OfflineSessionsV2.OfflineSessionServiceClient _offlineSessionClient;
    private readonly DevicesV2.DeviceControlService.DeviceControlServiceClient _deviceControlClient;
    private readonly ITokenProvider _tokenProvider;
    private string? _clientPortalAccessToken;

    public V2GrpcBackendClient(Uri backendAddress, ITokenProvider tokenProvider)
    {
        ArgumentNullException.ThrowIfNull(backendAddress);
        ArgumentNullException.ThrowIfNull(tokenProvider);
        if (string.Equals(backendAddress.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase))
        {
            AppContext.SetSwitch("System.Net.Http.SocketsHttpHandler.Http2UnencryptedSupport", true);
        }

        _channel = GrpcChannel.ForAddress(backendAddress);
        _offlineSessionClient = new OfflineSessionsV2.OfflineSessionServiceClient(_channel);
        _deviceControlClient = new DevicesV2.DeviceControlService.DeviceControlServiceClient(_channel);
        _tokenProvider = tokenProvider;
        ClientLog.Info("transport", $"v2 grpc channel created endpoint={backendAddress}");
    }

    public async Task<V2OfflineLoginResult> LoginAsync(
        string identifier,
        string password,
        string deviceId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default)
    {
        GameClub.Client.Contracts.Events.V2.SignedOfflineSessionSnapshot snapshot;
        try
        {
            snapshot = await _offlineSessionClient.LoginAsync(
                new GameClub.Client.Contracts.Events.V2.LoginOfflineSessionRequest
                {
                    Identifier = identifier,
                    Password = password,
                    DeviceId = deviceId,
                    IdempotencyKey = idempotencyKey,
                },
                headers: await CreateDeviceMetadataAsync(cancellationToken),
                deadline: DateTime.UtcNow.AddSeconds(10),
                cancellationToken: cancellationToken);
        }
        catch (RpcException error)
        {
            ClientLog.RpcFailure("v2.login", error, "offline login");
            throw;
        }
        if (snapshot.PasswordResetRequired)
        {
            _clientPortalAccessToken = null;
            return new V2OfflineLoginResult(
                Ledger: null,
                PasswordResetRequired: true,
                PasswordResetToken: snapshot.PasswordResetToken);
        }
        _clientPortalAccessToken = snapshot.PortalAccessToken;
        return new V2OfflineLoginResult(
            V2OfflineSessionSnapshotReader.VerifyAndCreateLedger(snapshot, signatureVerifier),
            PasswordResetRequired: false,
            PasswordResetToken: null);
    }

    public async Task<V2OfflineLoginResult> RegisterAsync(
        string nickname,
        string phone,
        string password,
        string deviceId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default)
    {
        var snapshot = await _offlineSessionClient.RegisterAsync(
            new GameClub.Client.Contracts.Events.V2.RegisterOfflineSessionRequest
            {
                Nickname = nickname,
                Phone = phone,
                Password = password,
                DeviceId = deviceId,
                IdempotencyKey = idempotencyKey,
            },
            headers: await CreateDeviceMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        _clientPortalAccessToken = snapshot.PortalAccessToken;
        return new V2OfflineLoginResult(
            V2OfflineSessionSnapshotReader.VerifyAndCreateLedger(snapshot, signatureVerifier),
            PasswordResetRequired: false,
            PasswordResetToken: null);
    }

    public async Task ChangePasswordAsync(
        string newPassword,
        string deviceId,
        string resetToken,
        CancellationToken cancellationToken = default)
    {
        Google.Protobuf.WellKnownTypes.Empty response;
        try
        {
            response = await _offlineSessionClient.ChangePasswordAsync(
                new GameClub.Client.Contracts.Events.V2.ChangeOfflinePasswordRequest
                {
                    DeviceId = deviceId,
                    NewPassword = newPassword,
                },
                headers: CreateBearerMetadata(resetToken),
                deadline: DateTime.UtcNow.AddSeconds(10),
                cancellationToken: cancellationToken);
        }
        catch (RpcException error)
        {
            ClientLog.RpcFailure("v2.password-reset", error, "change password");
            throw;
        }
        _ = response;
    }

    public async Task<ClientConnectionSnapshot> CheckConnectionAsync(
        CancellationToken cancellationToken = default)
    {
        try
        {
            var response = await _deviceControlClient.GetHealthAsync(
                new DevicesV2.DeviceHealthRequest(),
                headers: await CreateDeviceMetadataAsync(cancellationToken),
                deadline: DateTime.UtcNow.AddSeconds(5),
                cancellationToken: cancellationToken);
            return new ClientConnectionSnapshot(
                ClientConnectionState.Online,
                "Соединение установлено",
                DateTimeOffset.UtcNow,
                response.Version);
        }
        catch (RpcException error) when (
            error.StatusCode is StatusCode.Unauthenticated or StatusCode.PermissionDenied)
        {
            ClientLog.RpcFailure("connection", error, "device health");
            throw new DeviceAuthenticationRequiredException(error);
        }
        catch (RpcException error)
        {
            ClientLog.RpcFailure("connection", error, "device health");
            throw;
        }
        catch (Exception error)
        {
            ClientLog.Exception("connection", error, "device health");
            throw;
        }
    }

    public async Task<WorkstationHeartbeatSnapshot> SendHeartbeatAsync(
        string deviceId,
        string clientVersion,
        IReadOnlyCollection<string> capabilities,
        CancellationToken cancellationToken = default)
    {
        var request = new DevicesV2.DeviceHeartbeatRequest
        {
            DeviceId = deviceId,
            ClientVersion = clientVersion,
        };
        request.Capabilities.AddRange(capabilities);
        DevicesV2.DeviceHeartbeatResponse response;
        try
        {
            response = await _deviceControlClient.HeartbeatAsync(
                request,
                headers: await CreateDeviceMetadataAsync(cancellationToken),
                deadline: DateTime.UtcNow.AddSeconds(5),
                cancellationToken: cancellationToken);
        }
        catch (RpcException error) when (error.StatusCode == StatusCode.AlreadyExists)
        {
            ClientLog.RpcFailure("heartbeat", error, "device heartbeat");
            throw new DeviceEnrollmentDisabledException();
        }
        catch (RpcException error)
        {
            ClientLog.RpcFailure("heartbeat", error, "device heartbeat");
            throw;
        }
        return new WorkstationHeartbeatSnapshot(
            response.DeviceId,
            response.GroupId,
            response.Theme,
            response.ManagerPasswordVerifier,
            ToLockdownPolicySnapshot(response.LockdownPolicy),
            SessionSnapshot: null,
            WorkstationName: response.WorkstationName);
    }

    public Task<EntryDecisionSnapshot> CheckEntryAsync(string workstationId, string? clientId, string? guestId, string deviceId, CancellationToken cancellationToken = default) => Unsupported<EntryDecisionSnapshot>();
    public Task<SessionSnapshot> StartSessionAsync(string workstationId, string deviceId, string? clientId, string? guestName, string? reservationId, string idempotencyKey, CancellationToken cancellationToken = default, string? tariffId = null, int tariffQuantity = 1) => Unsupported<SessionSnapshot>();
    public Task<SessionSnapshot> StopSessionAsync(string sessionId, string deviceId, CancellationToken cancellationToken = default) => Unsupported<SessionSnapshot>();
    public Task<SessionSnapshot> GetSessionSnapshotAsync(string sessionId, string deviceId, CancellationToken cancellationToken = default) => Unsupported<SessionSnapshot>();
    public Task<SessionTransferOfferSnapshot> CreateTransferOfferAsync(string sessionId, string? targetWorkstationId, string deviceId, string idempotencyKey, CancellationToken cancellationToken = default) => Unsupported<SessionTransferOfferSnapshot>();
    public Task<SessionTransferOfferSnapshot> GetTransferOfferAsync(string offerId, string deviceId, string token, CancellationToken cancellationToken = default) => Unsupported<SessionTransferOfferSnapshot>();
    public Task<SessionTransferResultSnapshot> ConfirmTransferAsync(string offerId, string deviceId, string token, string idempotencyKey, CancellationToken cancellationToken = default) => Unsupported<SessionTransferResultSnapshot>();
    public Task<SessionTransferResultSnapshot> ClaimPendingTransferAsync(string clientId, string workstationId, string deviceId, string idempotencyKey, CancellationToken cancellationToken = default) => Unsupported<SessionTransferResultSnapshot>();
    public Task<OfflineBatchResultSnapshot> ReplayOfflineBatchAsync(string sessionId, string deviceId, IReadOnlyCollection<OfflineOperationSnapshot> operations, CancellationToken cancellationToken = default) => Unsupported<OfflineBatchResultSnapshot>();
    public Task<ClientPortalAuthenticationSnapshot> RegisterAsync(string nickname, string phone, string password, string deviceId, CancellationToken cancellationToken = default) => Unsupported<ClientPortalAuthenticationSnapshot>();
    public Task<ClientPortalAuthenticationSnapshot> LoginAsync(string identifier, string password, string deviceId, CancellationToken cancellationToken = default) => Unsupported<ClientPortalAuthenticationSnapshot>();
    public Task<ClientPortalAuthenticationSnapshot?> ResumeAsync(string deviceId, CancellationToken cancellationToken = default) => Unsupported<ClientPortalAuthenticationSnapshot?>();
    public Task<ClientPortalAuthenticationSnapshot> ChangePasswordAsync(string newPassword, string deviceId, CancellationToken cancellationToken = default) => Unsupported<ClientPortalAuthenticationSnapshot>();
    public async Task<ClientPortalSnapshot> ResumePortalAsync(
        string deviceId,
        string sessionId,
        string clientId,
        CancellationToken cancellationToken = default)
    {
        var metadata = await CreateDeviceMetadataAsync(cancellationToken);
        var response = await _offlineSessionClient.ResumePortalAsync(
            new GameClub.Client.Contracts.Events.V2.ResumeOfflinePortalRequest
            {
                DeviceId = deviceId,
                SessionId = sessionId,
                ClientId = clientId,
            },
            headers: metadata,
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        if (!string.Equals(response.ClientId, clientId, StringComparison.OrdinalIgnoreCase)
            || string.IsNullOrWhiteSpace(response.PortalAccessToken))
        {
            throw new InvalidOperationException("V2 portal resume response does not match its session");
        }

        _clientPortalAccessToken = response.PortalAccessToken;
        ClientLog.Info(
            "v2.portal",
            $"resume accepted session_id={sessionId} client_id={clientId} " +
            $"token_expires_in={response.PortalAccessExpiresIn}");
        return await RefreshAsync(deviceId, cancellationToken: cancellationToken);
    }

    public async Task StopSessionAsync(
        string deviceId,
        string sessionId,
        string clientId,
        CancellationToken cancellationToken = default)
    {
        try
        {
            await _offlineSessionClient.StopSessionAsync(
                new GameClub.Client.Contracts.Events.V2.StopOfflineSessionRequest
                {
                    DeviceId = deviceId,
                    SessionId = sessionId,
                    ClientId = clientId,
                },
                headers: await CreateDeviceMetadataAsync(cancellationToken),
                deadline: DateTime.UtcNow.AddSeconds(10),
                cancellationToken: cancellationToken);
        }
        catch (RpcException error)
        {
            ClientLog.RpcFailure("v2.session", error, "stop session on server");
            throw;
        }

        ClientLog.Info("v2.session", $"server stop accepted session_id={sessionId}");
    }

    public async Task<V2LocalSessionLedger?> RedeemPendingGuestAccessAsync(
        string deviceId,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default,
        V2LocalSessionLedger? activeGuestLedger = null)
    {
        try
        {
            var request = new GameClub.Client.Contracts.Events.V2.RedeemGuestAccessRequest
            {
                DeviceId = deviceId,
                SessionId = activeGuestLedger?.SessionId.ToString() ?? string.Empty,
            };
            if (activeGuestLedger is not null)
            {
                request.AppliedGrantIds.Add(activeGuestLedger.AppliedServerOperationIds
                    .Append(activeGuestLedger.SnapshotId).Select(id => id.ToString()));
            }
            var snapshot = await _offlineSessionClient.RedeemGuestAccessAsync(
                request,
                headers: await CreateDeviceMetadataAsync(cancellationToken),
                deadline: DateTime.UtcNow.AddSeconds(10),
                cancellationToken: cancellationToken);
            return V2OfflineSessionSnapshotReader.VerifyAndCreateGuestLedger(
                snapshot,
                signatureVerifier,
                deviceId,
                activeGuestLedger?.SessionId);
        }
        catch (RpcException error) when (error.StatusCode == StatusCode.NotFound)
        {
            return null;
        }
    }

    public async Task StopGuestSessionAsync(
        string deviceId,
        string sessionId,
        string paymentId,
        CancellationToken cancellationToken = default)
    {
        await _offlineSessionClient.StopGuestAccessAsync(
            new GameClub.Client.Contracts.Events.V2.StopGuestAccessRequest
            {
                DeviceId = deviceId,
                SessionId = sessionId,
                PaymentId = paymentId,
            },
            headers: await CreateDeviceMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
    }

    public async Task<ClientPortalSnapshot> RefreshAsync(
        string deviceId,
        int limit = 50,
        CancellationToken cancellationToken = default)
    {
        var response = await _offlineSessionClient.GetPortalSnapshotAsync(
            new GameClub.Client.Contracts.Events.V2.GetOfflinePortalSnapshotRequest
            {
                DeviceId = deviceId,
                Limit = (uint)Math.Clamp(limit, 1, 100),
            },
            headers: CreateClientPortalMetadata(),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        return V2PortalSnapshotMapper.ToDomain(response);
    }

    public async Task<ClientPortalSnapshot> ActivateEntitlementAsync(
        string deviceId,
        string entitlementId,
        CancellationToken cancellationToken = default)
    {
        var response = await _offlineSessionClient.ActivateEntitlementAsync(
            new GameClub.Client.Contracts.Events.V2.ActivateOfflineEntitlementRequest
            {
                DeviceId = deviceId,
                EntitlementId = entitlementId,
            },
            headers: CreateClientPortalMetadata(),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        return V2PortalSnapshotMapper.ToDomain(response);
    }

    public async Task<ClientPortalSnapshot> PurchaseEntitlementAsync(
        string deviceId,
        string tariffId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default)
    {
        var response = await _offlineSessionClient.PurchaseEntitlementAsync(
            new GameClub.Client.Contracts.Events.V2.PurchaseOfflineEntitlementRequest
            {
                DeviceId = deviceId,
                TariffId = tariffId,
                IdempotencyKey = idempotencyKey,
            },
            headers: CreateClientPortalMetadata(),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        if (response.PurchasedPackage?.Payload?.PurchaseIdempotencyKey != idempotencyKey)
        {
            throw new InvalidOperationException("V2 package purchase receipt does not match the request");
        }
        return V2PortalSnapshotMapper.ToDomain(response) with
        {
            PurchasedPackage = V2OfflineSessionSnapshotReader.VerifyAndCreateLedger(
                response.PurchasedPackage, signatureVerifier),
        };
    }

    Task<ClientPortalSnapshot> IClientPortalGateway.PurchaseEntitlementAsync(
        string deviceId,
        string tariffId,
        string idempotencyKey,
        CancellationToken cancellationToken) => Unsupported<ClientPortalSnapshot>();

    public void Logout() => _clientPortalAccessToken = null;
    public async IAsyncEnumerable<WorkstationCommandSnapshot> WatchDeviceCommandsAsync(
        string deviceId,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        using var call = _deviceControlClient.WatchCommands(
            new DevicesV2.DeviceCommandWatchRequest { DeviceId = deviceId },
            headers: await CreateDeviceMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(30),
            cancellationToken: cancellationToken);
        await foreach (var command in call.ResponseStream.ReadAllAsync(cancellationToken))
        {
            yield return ToWorkstationCommandSnapshot(command);
        }
    }

    public async Task<WorkstationCommandSnapshot> AcknowledgeDeviceCommandAsync(
        string commandId,
        string deviceId,
        bool success,
        string message,
        CancellationToken cancellationToken = default)
    {
        var command = await _deviceControlClient.AcknowledgeCommandAsync(
            new DevicesV2.DeviceCommandAcknowledgementRequest
            {
                CommandId = commandId,
                DeviceId = deviceId,
                Success = success,
                Message = message,
            },
            headers: await CreateDeviceMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        return ToWorkstationCommandSnapshot(command);
    }
    public ValueTask DisposeAsync()
    {
        _channel.Dispose();
        return ValueTask.CompletedTask;
    }

    private async Task<Metadata> CreateDeviceMetadataAsync(CancellationToken cancellationToken)
    {
        var accessToken = await _tokenProvider.GetAccessTokenAsync(cancellationToken);
        if (string.IsNullOrWhiteSpace(accessToken))
        {
            throw new DeviceAuthenticationRequiredException(
                new InvalidOperationException("Device enrollment has not issued an access token."));
        }
        return CreateBearerMetadata(accessToken);
    }

    private static Metadata CreateBearerMetadata(string accessToken) =>
        new() { { "authorization", $"Bearer {accessToken}" } };

    private Metadata CreateClientPortalMetadata()
    {
        if (string.IsNullOrWhiteSpace(_clientPortalAccessToken))
        {
            throw new DeviceAuthenticationRequiredException(
                new InvalidOperationException("V2 portal access token is not available."));
        }
        return CreateBearerMetadata(_clientPortalAccessToken);
    }

    private static Task<T> Unsupported<T>() =>
        Task.FromException<T>(new NotSupportedException("This client no longer supports the retired session API."));

    private static WorkstationCommandSnapshot ToWorkstationCommandSnapshot(
        DevicesV2.DeviceCommand command) =>
        new(
            command.Id,
            string.Empty,
            command.CommandType,
            command.PayloadJson,
            command.IdempotencyKey,
            command.Status,
            command.AcknowledgementMessage,
            command.ExpiresAt);

    private static WorkstationLockdownPolicySnapshot ToLockdownPolicySnapshot(
        DevicesV2.WorkstationLockdownPolicy policy)
    {
        if (policy is null || policy.CalculateSize() == 0)
        {
            return WorkstationLockdownPolicySnapshot.SafeDefault;
        }
        var deploymentMode = policy.DeploymentMode.Trim().ToLowerInvariant();
        if (deploymentMode is not ("app_gate" or "assigned_access" or "shell_launcher"))
        {
            return WorkstationLockdownPolicySnapshot.SafeDefault;
        }
        return new WorkstationLockdownPolicySnapshot(
            deploymentMode, policy.ShellEnabled, policy.UserSelfLoginEnabled,
            policy.LockAfterSession, policy.RestartAfterSession, policy.HiddenDrives.ToArray(),
            policy.BlockExternalStorage, policy.DisableStartMenu, policy.DisableDesktopSwitching,
            policy.BlockedWindowRules.ToArray(), policy.AllowedApplicationIds.ToArray(),
            policy.Version > 0 ? policy.Version : 1);
    }
}
