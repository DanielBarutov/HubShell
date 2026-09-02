using System.Net;
using System.Runtime.CompilerServices;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Contracts;
using Workstations = GameClub.Client.Contracts.Workstations.V1;
using Sessions = GameClub.Client.Contracts.Sessions.V1;
using Clients = GameClub.Client.Contracts.Clients.V1;
using Reservations = GameClub.Client.Contracts.Reservations.V1;
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
    private readonly Reservations.ReservationService.ReservationServiceClient _reservationClient;
    private readonly Clients.ClientPortalService.ClientPortalServiceClient _clientPortalClient;
    private readonly ITokenProvider? _tokenProvider;
    private string? _clientPortalAccessToken;
    private DateTimeOffset _clientPortalExpiresAt;

    public GrpcBackendClient(Uri backendAddress, ITokenProvider? tokenProvider = null)
    {
        _channel = GrpcChannel.ForAddress(backendAddress);
        _systemClient = new SystemService.SystemServiceClient(_channel);
        _workstationClient = new Workstations.WorkstationService.WorkstationServiceClient(_channel);
        _sessionClient = new Sessions.SessionService.SessionServiceClient(_channel);
        _reservationClient = new Reservations.ReservationService.ReservationServiceClient(_channel);
        _clientPortalClient = new Clients.ClientPortalService.ClientPortalServiceClient(_channel);
        _tokenProvider = tokenProvider;
    }

    public async Task<ClientPortalAuthenticationSnapshot> RegisterAsync(
        string nickname,
        string phone,
        string pin,
        string deviceId,
        CancellationToken cancellationToken = default)
    {
        var response = await _clientPortalClient.RegisterAsync(
            new Clients.RegisterPortalRequest
            {
                Nickname = nickname,
                Phone = phone,
                Pin = pin,
                DeviceId = deviceId,
            },
            headers: await CreateDeviceMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        SetClientPortalToken(response);
        return ToPortalAuthenticationSnapshot(response);
    }

    public async Task<ClientPortalAuthenticationSnapshot> LoginAsync(
        string identifier,
        string pin,
        string deviceId,
        CancellationToken cancellationToken = default)
    {
        var response = await _clientPortalClient.LoginAsync(
            new Clients.LoginPortalRequest
            {
                Identifier = identifier,
                Pin = pin,
                DeviceId = deviceId,
            },
            headers: await CreateDeviceMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        SetClientPortalToken(response);
        return ToPortalAuthenticationSnapshot(response);
    }

    public async Task<ClientPortalSnapshot> RefreshAsync(
        string deviceId,
        int limit = 50,
        CancellationToken cancellationToken = default)
    {
        var metadata = await CreateClientPortalMetadataAsync(cancellationToken);
        var response = await _clientPortalClient.GetAsync(
            new Clients.GetPortalRequest { DeviceId = deviceId, Limit = limit },
            headers: metadata,
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        return ToPortalSnapshot(response);
    }

    public async Task<ClientPortalSnapshot> ActivateEntitlementAsync(
        string deviceId,
        string entitlementId,
        CancellationToken cancellationToken = default)
    {
        var response = await _clientPortalClient.ActivateEntitlementAsync(
            new Clients.ActivateEntitlementRequest
            {
                DeviceId = deviceId,
                EntitlementId = entitlementId,
            },
            headers: await CreateClientPortalMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        return ToPortalSnapshot(response);
    }

    public void Logout() => (_clientPortalAccessToken, _clientPortalExpiresAt) = (null, default);

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
            ToLockdownPolicySnapshot(response.LockdownPolicy),
            response.SessionSnapshot is null || response.SessionSnapshot.CalculateSize() == 0
                ? null
                : ToSessionSnapshot(response.SessionSnapshot));
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

    public async Task<EntryDecisionSnapshot> CheckEntryAsync(
        string workstationId,
        string? clientId,
        string? guestId,
        CancellationToken cancellationToken = default)
    {
        var metadata = await CreateMetadataAsync(cancellationToken);
        var response = await _reservationClient.CheckEntryAsync(
            new Reservations.CheckEntryRequest
            {
                WorkstationId = workstationId,
                ClientId = clientId ?? string.Empty,
                GuestId = guestId ?? string.Empty,
            },
            headers: metadata,
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return new EntryDecisionSnapshot(
            response.Allowed,
            response.Reason,
            string.IsNullOrWhiteSpace(response.ReservationId) ? null : response.ReservationId,
            string.IsNullOrWhiteSpace(response.AssignedClientId) ? null : response.AssignedClientId,
            response.StartsAt is not null ? response.StartsAt.ToDateTimeOffset() : null,
            response.EndsAt is not null ? response.EndsAt.ToDateTimeOffset() : null);
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

    public async Task<SessionSnapshot> GetSessionSnapshotAsync(
        string sessionId,
        string deviceId,
        CancellationToken cancellationToken = default)
    {
        var metadata = await CreateMetadataAsync(cancellationToken);
        var response = await _sessionClient.GetSnapshotAsync(
            new Sessions.GetSessionSnapshotRequest
            {
                SessionId = sessionId,
                DeviceId = deviceId,
            },
            headers: metadata,
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return ToSessionSnapshot(response);
    }

    private static SessionSnapshot ToSessionSnapshot(Sessions.SessionSnapshot response)
    {
        var session = ToSessionSnapshot(response.Session);
        return session with
        {
            LoginGrantMinutes = response.Session.LoginGrantMinutes,
            EntitlementId = string.IsNullOrWhiteSpace(response.Session.EntitlementId)
                ? null
                : response.Session.EntitlementId,
            ZoneId = string.IsNullOrWhiteSpace(response.ZoneId) ? null : response.ZoneId,
            BalanceCents = string.IsNullOrWhiteSpace(response.ClientId)
                ? null
                : response.BalanceCents,
            BalanceBonus = string.IsNullOrWhiteSpace(response.ClientId)
                ? null
                : response.BalanceBonus,
            ActivePackage = response.ActivePackage is null || response.ActivePackage.CalculateSize() == 0
                ? null
                : ToPackageSnapshot(response.ActivePackage),
            PackageQueue = response.PackageQueue.Select(ToPackageSnapshot).ToArray(),
            Meter = response.Meter is null || response.Meter.CalculateSize() == 0
                ? null
                : new SessionMeterSnapshot(
                    response.Meter.SessionId,
                    response.Meter.BilledMinutes,
                    response.Meter.BilledCents,
                    response.Meter.PackageMinutes,
                    string.IsNullOrWhiteSpace(response.Meter.ActiveEntitlementId)
                        ? null
                        : response.Meter.ActiveEntitlementId,
                    response.Meter.Status,
                    ToIsoTimestamp(response.Meter.UpdatedAt)),
            ServerTime = ToIsoTimestamp(response.ServerTime),
            DeviceId = string.IsNullOrWhiteSpace(response.DeviceId) ? null : response.DeviceId,
        };
    }

    public async Task<SessionTransferOfferSnapshot> CreateTransferOfferAsync(
        string sessionId,
        string targetWorkstationId,
        string deviceId,
        string idempotencyKey,
        CancellationToken cancellationToken = default)
    {
        var response = await _sessionClient.CreateTransferOfferAsync(
            new Sessions.CreateTransferOfferRequest
            {
                SessionId = sessionId,
                TargetWorkstationId = targetWorkstationId,
                DeviceId = deviceId,
                IdempotencyKey = idempotencyKey,
            },
            headers: await CreateMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return ToTransferOfferSnapshot(response);
    }

    public async Task<SessionTransferOfferSnapshot> GetTransferOfferAsync(
        string offerId,
        string deviceId,
        string token,
        CancellationToken cancellationToken = default)
    {
        var response = await _sessionClient.GetTransferOfferAsync(
            new Sessions.GetTransferOfferRequest
            {
                OfferId = offerId,
                DeviceId = deviceId,
                Token = token,
            },
            headers: await CreateMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return ToTransferOfferSnapshot(response);
    }

    public async Task<SessionTransferResultSnapshot> ConfirmTransferAsync(
        string offerId,
        string deviceId,
        string token,
        string idempotencyKey,
        CancellationToken cancellationToken = default)
    {
        var response = await _sessionClient.ConfirmTransferAsync(
            new Sessions.ConfirmTransferRequest
            {
                OfferId = offerId,
                DeviceId = deviceId,
                Token = token,
                IdempotencyKey = idempotencyKey,
            },
            headers: await CreateMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(5),
            cancellationToken: cancellationToken);
        return new SessionTransferResultSnapshot(
            ToTransferOfferSnapshot(response.Offer),
            ToSessionSnapshot(response.Session));
    }

    public async Task<OfflineBatchResultSnapshot> ReplayOfflineBatchAsync(
        string sessionId,
        string deviceId,
        IReadOnlyCollection<OfflineOperationSnapshot> operations,
        CancellationToken cancellationToken = default)
    {
        var request = new Sessions.ReplayOfflineBatchRequest
        {
            ProtocolVersion = 1,
            SessionId = sessionId,
            DeviceId = deviceId,
        };
        request.Operations.AddRange(operations.Select(operation =>
        {
            var item = new Sessions.OfflineOperation
            {
                Id = operation.Id,
                Sequence = operation.Sequence,
                Kind = operation.Kind,
                PayloadJson = operation.PayloadJson,
                SnapshotVersion = operation.SnapshotVersion,
                IdempotencyKey = operation.IdempotencyKey,
                Checksum = operation.Checksum,
            };
            item.CreatedAt = Timestamp.FromDateTime(operation.CreatedAt.UtcDateTime);
            return item;
        }));
        var response = await _sessionClient.ReplayOfflineBatchAsync(
            request,
            headers: await CreateMetadataAsync(cancellationToken),
            deadline: DateTime.UtcNow.AddSeconds(10),
            cancellationToken: cancellationToken);
        var results = response.Results.Select(item => new OfflineOperationResultSnapshot(
            item.OperationId,
            item.Sequence,
            item.Status,
            item.Message,
            item.AppliedAt is null ? null : ToIsoTimestamp(item.AppliedAt))).ToArray();
        return new OfflineBatchResultSnapshot(
            response.SessionId,
            results,
            response.Snapshot is null || response.Snapshot.CalculateSize() == 0
                ? null
                : ToSessionSnapshot(response.Snapshot));
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
        return await CreateDeviceMetadataAsync(cancellationToken);
    }

    private async Task<Metadata> CreateDeviceMetadataAsync(CancellationToken cancellationToken)
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

    private Task<Metadata> CreateClientPortalMetadataAsync(
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(_clientPortalAccessToken)
            || _clientPortalExpiresAt <= DateTimeOffset.UtcNow.AddSeconds(30))
        {
            throw new DeviceAuthenticationRequiredException(
                new InvalidOperationException("Client portal authentication has expired"));
        }

        var metadata = new Metadata
        {
            { "authorization", $"Bearer {_clientPortalAccessToken}" },
        };
        return Task.FromResult(metadata);
    }

    private void SetClientPortalToken(Clients.ClientPortalSession response)
    {
        _clientPortalAccessToken = response.AccessToken;
        _clientPortalExpiresAt = DateTimeOffset.UtcNow.AddSeconds(Math.Max(response.ExpiresIn, 1));
    }

    private static ClientPortalAuthenticationSnapshot ToPortalAuthenticationSnapshot(
        Clients.ClientPortalSession response) =>
        new(response.AccessToken, response.ExpiresIn, ToPortalSnapshot(response.Snapshot));

    private static ClientPortalSnapshot ToPortalSnapshot(Clients.ClientPortalSnapshot source) =>
        new(
            source.Client.Id,
            source.Client.Nickname,
            source.Client.Phone,
            source.Client.BalanceCents,
            source.Client.BalanceBonus,
            source.AvailableTimeMinutes,
            source.BalanceOperations.Select(operation => new ClientPortalBalanceOperation(
                operation.Id,
                operation.OperationType,
                operation.AmountCents,
                operation.BonusAmount,
                operation.Reason,
                ToIsoTimestamp(operation.CreatedAt))).ToArray(),
            source.Sessions.Select(session => new ClientPortalSession(
                session.Id,
                session.WorkstationId,
                session.Status,
                ToIsoTimestamp(session.StartedAt),
                session.EndedAt is null ? null : ToIsoTimestamp(session.EndedAt),
                string.IsNullOrWhiteSpace(session.TariffId) ? null : session.TariffId,
                string.IsNullOrWhiteSpace(session.TariffName) ? null : session.TariffName,
                session.TariffQuantity)).ToArray(),
            source.Charges.Select(charge => new ClientPortalCharge(
                charge.Id,
                charge.SessionId,
                charge.TariffId,
                charge.DurationMinutes,
                charge.AmountCents,
                string.IsNullOrWhiteSpace(charge.TariffName) ? null : charge.TariffName,
                ToIsoTimestamp(charge.CreatedAt))).ToArray(),
            source.Purchases.Select(purchase => new ClientPortalPurchase(
                purchase.Id,
                purchase.ProductName,
                purchase.Quantity,
                purchase.TotalPriceCents,
                purchase.PaymentMethod,
                ToIsoTimestamp(purchase.CreatedAt))).ToArray(),
            source.Entitlements.Select(entitlement => new ClientPortalEntitlement(
                entitlement.Id,
                entitlement.TariffId,
                string.IsNullOrWhiteSpace(entitlement.ZoneId) ? null : entitlement.ZoneId,
                entitlement.Status,
                entitlement.DurationMinutes,
                entitlement.RemainingMinutes,
                entitlement.PriceCents,
                entitlement.QueuePosition,
                string.IsNullOrWhiteSpace(entitlement.TariffName) ? null : entitlement.TariffName,
                ToIsoTimestamp(entitlement.PurchasedAt),
                entitlement.ActivatedAt is null ? null : ToIsoTimestamp(entitlement.ActivatedAt))).ToArray());

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

    private static SessionPackageSnapshot ToPackageSnapshot(Sessions.PackageSnapshot package) =>
        new(
            package.Id,
            package.TariffId,
            string.IsNullOrWhiteSpace(package.ZoneId) ? null : package.ZoneId,
            package.DurationMinutes,
            package.RemainingMinutes,
            package.QueuePosition,
            package.Status,
            package.WindowStartMinute,
            package.WindowEndMinute,
            string.IsNullOrWhiteSpace(package.WindowTimezone) ? null : package.WindowTimezone);

    private static SessionTransferOfferSnapshot ToTransferOfferSnapshot(
        Sessions.TransferOffer offer) =>
        new(
            offer.Id,
            offer.SessionId,
            offer.ClientId,
            offer.SourceWorkstationId,
            offer.TargetWorkstationId,
            offer.Token,
            offer.Status,
            offer.RequiresPackageBurn,
            string.IsNullOrWhiteSpace(offer.Warning) ? null : offer.Warning,
            ToIsoTimestamp(offer.CreatedAt),
            ToIsoTimestamp(offer.ExpiresAt),
            offer.ConfirmedAt is null ? null : ToIsoTimestamp(offer.ConfirmedAt));

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
