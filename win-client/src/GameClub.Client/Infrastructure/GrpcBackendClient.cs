using System.Net;
using System.Runtime.CompilerServices;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Contracts;
using Workstations = GameClub.Client.Contracts.Workstations.V1;
using Sessions = GameClub.Client.Contracts.Sessions.V1;
using GameClub.Client.Domain;
using Grpc.Core;
using Grpc.Net.Client;
using Google.Protobuf.WellKnownTypes;

namespace GameClub.Client.Infrastructure;

public sealed class GrpcBackendClient : IBackendClient
{
    private readonly GrpcChannel _channel;
    private readonly SystemService.SystemServiceClient _systemClient;
    private readonly Workstations.WorkstationService.WorkstationServiceClient _workstationClient;
    private readonly Sessions.SessionService.SessionServiceClient _sessionClient;
    private readonly ITokenProvider? _tokenProvider;

    public GrpcBackendClient(Uri backendAddress, ITokenProvider? tokenProvider = null)
    {
        _channel = GrpcChannel.ForAddress(backendAddress);
        _systemClient = new SystemService.SystemServiceClient(_channel);
        _workstationClient = new Workstations.WorkstationService.WorkstationServiceClient(_channel);
        _sessionClient = new Sessions.SessionService.SessionServiceClient(_channel);
        _tokenProvider = tokenProvider;
    }

    public async Task<ClientConnectionSnapshot> CheckConnectionAsync(
        CancellationToken cancellationToken = default)
    {
        try
        {
            var metadata = await CreateMetadataAsync(cancellationToken);

            var response = await _systemClient.GetHealthAsync(
                new HealthRequest(),
                headers: metadata,
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
            throw new DeviceAuthenticationRequiredException(error);
        }
        catch (HttpRequestException error) when (
            error.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            throw new DeviceAuthenticationRequiredException(error);
        }
    }

    public async Task<WorkstationHeartbeatSnapshot> SendHeartbeatAsync(
        string deviceId,
        string clientVersion,
        IReadOnlyCollection<string> capabilities,
        CancellationToken cancellationToken = default)
    {
        var metadata = await CreateMetadataAsync(cancellationToken);
        var request = new Workstations.HeartbeatRequest
        {
            DeviceId = deviceId,
            ClientVersion = clientVersion,
        };
        request.Capabilities.AddRange(capabilities);
        var response = await _workstationClient.HeartbeatAsync(
            request,
            headers: metadata,
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return new WorkstationHeartbeatSnapshot(
            response.DeviceId,
            response.GroupId,
            response.Theme,
            response.ManagerPasswordVerifier,
            ToLockdownPolicySnapshot(response.LockdownPolicy));
    }

    public async Task<SessionSnapshot> StartSessionAsync(
        string workstationId,
        string deviceId,
        string? clientId,
        string? guestName,
        string? reservationId,
        string idempotencyKey,
        CancellationToken cancellationToken = default,
        string? tariffId = null,
        int tariffQuantity = 1)
    {
        var metadata = await CreateMetadataAsync(cancellationToken);
        var response = await _sessionClient.StartAsync(
            new Sessions.StartSessionRequest
            {
                WorkstationId = workstationId,
                DeviceId = deviceId,
                ClientId = clientId ?? string.Empty,
                GuestName = guestName ?? string.Empty,
                ReservationId = reservationId ?? string.Empty,
                IdempotencyKey = idempotencyKey,
                TariffId = tariffId ?? string.Empty,
                TariffQuantity = tariffQuantity,
            },
            headers: metadata,
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return ToSessionSnapshot(response);
    }

    public async Task<SessionSnapshot> StopSessionAsync(
        string sessionId,
        string deviceId,
        CancellationToken cancellationToken = default)
    {
        var metadata = await CreateMetadataAsync(cancellationToken);
        var response = await _sessionClient.StopAsync(
            new Sessions.StopSessionRequest
            {
                SessionId = sessionId,
                DeviceId = deviceId,
            },
            headers: metadata,
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return ToSessionSnapshot(response);
    }

    public async IAsyncEnumerable<WorkstationCommandSnapshot> WatchCommandsAsync(
        string deviceId,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var metadata = await CreateMetadataAsync(cancellationToken);
        using var call = _workstationClient.WatchCommands(
            new Workstations.WatchCommandsRequest { DeviceId = deviceId },
            headers: metadata,
            deadline: DateTime.UtcNow.AddMinutes(10),
            cancellationToken: cancellationToken);

        await foreach (var command in call.ResponseStream.ReadAllAsync(cancellationToken))
        {
            yield return new WorkstationCommandSnapshot(
                command.Id,
                command.WorkstationId,
                command.CommandType,
                command.PayloadJson,
                command.IdempotencyKey,
                command.Status.ToString(),
                command.AcknowledgementMessage,
                ToIsoTimestamp(command.ExpiresAt));
        }
    }

    public async Task<WorkstationCommandSnapshot> AcknowledgeCommandAsync(
        string commandId,
        string deviceId,
        bool success,
        string message,
        CancellationToken cancellationToken = default)
    {
        var metadata = await CreateMetadataAsync(cancellationToken);
        var command = await _workstationClient.AcknowledgeCommandAsync(
            new Workstations.AcknowledgeCommandRequest
            {
                CommandId = commandId,
                DeviceId = deviceId,
                Success = success,
                Message = message,
            },
            headers: metadata,
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return ToSnapshot(command);
    }

    public async ValueTask DisposeAsync()
    {
        _channel.Dispose();
        if (_tokenProvider is IAsyncDisposable asyncDisposable)
        {
            await asyncDisposable.DisposeAsync();
        }
        else if (_tokenProvider is IDisposable disposable)
        {
            disposable.Dispose();
        }
    }

    private async Task<Metadata> CreateMetadataAsync(CancellationToken cancellationToken)
    {
        var metadata = new Metadata();
        var token = await (_tokenProvider?.GetAccessTokenAsync(cancellationToken)
            ?? ValueTask.FromResult<string?>(null));
        if (!string.IsNullOrWhiteSpace(token))
        {
            metadata.Add("authorization", $"Bearer {token}");
        }
        return metadata;
    }

    private static WorkstationCommandSnapshot ToSnapshot(Workstations.WorkstationCommand command) =>
        new(
            command.Id,
            command.WorkstationId,
            command.CommandType,
            command.PayloadJson,
            command.IdempotencyKey,
            command.Status.ToString(),
            command.AcknowledgementMessage,
            ToIsoTimestamp(command.ExpiresAt));

    private static SessionSnapshot ToSessionSnapshot(Sessions.Session session) =>
        new(
            session.Id,
            session.WorkstationId,
            string.IsNullOrWhiteSpace(session.ClientId) ? null : session.ClientId,
            string.IsNullOrWhiteSpace(session.GuestName) ? null : session.GuestName,
            session.Status.ToString(),
            ToIsoTimestamp(session.StartedAt),
            session.EndedAt is null ? null : ToIsoTimestamp(session.EndedAt),
            session.Source,
            session.ReservationId);

    private static WorkstationLockdownPolicySnapshot ToLockdownPolicySnapshot(
        Workstations.WorkstationLockdownPolicy policy)
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
            deploymentMode,
            policy.ShellEnabled,
            policy.UserSelfLoginEnabled,
            policy.LockAfterSession,
            policy.RestartAfterSession,
            policy.HiddenDrives.ToArray(),
            policy.BlockExternalStorage,
            policy.DisableStartMenu,
            policy.DisableDesktopSwitching,
            policy.BlockedWindowRules.ToArray(),
            policy.AllowedApplicationIds.ToArray(),
            policy.Version > 0 ? policy.Version : 1);
    }

    private static string ToIsoTimestamp(Timestamp timestamp) =>
        timestamp is null ? string.Empty : timestamp.ToDateTimeOffset().ToString("O");
}
