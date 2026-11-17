using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Grpc.Core;
using TransferV2Proto = GameClub.Client.Contracts.Events.V2;

namespace GameClub.Client.Infrastructure;

public sealed partial class V2GrpcBackendClient
{
    public async Task<IReadOnlyList<V2TransferTarget>> ListTransferTargetsAsync(
        string deviceId, Guid sessionId, CancellationToken cancellationToken)
    {
        var result = await _offlineSessionClient.ListTransferTargetsAsync(
            new TransferV2Proto.ListTransferTargetsRequest { DeviceId = deviceId, SessionId = sessionId.ToString() },
            await TransferOptionsAsync(cancellationToken));
        return result.Targets.Select(target => new V2TransferTarget(
            Guid.Parse(target.WorkstationId), target.Name,
            string.IsNullOrEmpty(target.GroupId) ? null : target.GroupId)).ToArray();
    }

    public async Task<V2TransferQuote> QuoteTransferAsync(
        string deviceId, Guid sessionId, Guid targetWorkstationId, CancellationToken cancellationToken)
    {
        var quote = await _offlineSessionClient.QuoteTransferAsync(
            new TransferV2Proto.QuoteTransferRequest
            {
                DeviceId = deviceId,
                SessionId = sessionId.ToString(),
                TargetWorkstationId = targetWorkstationId.ToString(),
            },
            await TransferOptionsAsync(cancellationToken));
        return new(
            quote.Token,
            quote.HasPerMinutePriceCents ? quote.PerMinutePriceCents : null,
            string.IsNullOrEmpty(quote.BurnedPackageName) ? null : quote.BurnedPackageName,
            quote.HasBurnedPackageMinutes ? checked((int)quote.BurnedPackageMinutes) : null,
            quote.HasFallbackGrantMinutes ? checked((int)quote.FallbackGrantMinutes) : null);
    }

    public async Task<V2TransferOperation> BeginTransferAsync(
        string deviceId, Guid sessionId, V2PendingSourceTransfer request, CancellationToken cancellationToken) =>
        ReadTransfer(await _offlineSessionClient.BeginTransferAsync(
            new TransferV2Proto.BeginTransferRequest
            {
                DeviceId = deviceId,
                SessionId = sessionId.ToString(),
                TargetWorkstationId = request.TargetWorkstationId.ToString(),
                OperationId = request.OperationId.ToString(),
                QuoteToken = request.QuoteToken,
            },
            await TransferOptionsAsync(cancellationToken)));

    public async Task<V2TransferOperation?> GetPendingTransferAsync(
        string deviceId, CancellationToken cancellationToken)
    {
        var result = await _offlineSessionClient.GetPendingTransferAsync(
            new TransferV2Proto.GetPendingTransferRequest { DeviceId = deviceId },
            await TransferOptionsAsync(cancellationToken));
        return result.Operation is null ? null : ReadTransfer(result.Operation);
    }

    public async Task<V2TransferOperation> GetTransferOperationAsync(
        string deviceId, Guid operationId, CancellationToken cancellationToken) =>
        ReadTransfer(await _offlineSessionClient.GetTransferOperationAsync(
            TransferRequest(deviceId, operationId), await TransferOptionsAsync(cancellationToken)));

    public async Task<V2TransferOperation> ReadyTransferTargetAsync(
        string deviceId, Guid operationId, CancellationToken cancellationToken) =>
        ReadTransfer(await _offlineSessionClient.ReadyTransferTargetAsync(
            TransferRequest(deviceId, operationId), await TransferOptionsAsync(cancellationToken)));

    public async Task<V2TransferOperation> ConfirmTransferSourceAsync(
        string deviceId, Guid operationId, V2TransferCheckpoint checkpoint,
        CancellationToken cancellationToken) =>
        ReadTransfer(await _offlineSessionClient.ConfirmTransferSourceAsync(
            new TransferV2Proto.ConfirmTransferSourceRequest
            {
                DeviceId = deviceId,
                OperationId = operationId.ToString(),
                Checkpoint = new TransferV2Proto.TransferSourceCheckpoint
                {
                    Sequence = checked((int)checkpoint.Sequence),
                    PayloadHash = checkpoint.PayloadHash ?? string.Empty,
                },
            },
            await TransferOptionsAsync(cancellationToken)));

    public async Task<V2TransferOperation> CancelTransferAsync(
        string deviceId, Guid operationId, CancellationToken cancellationToken) =>
        ReadTransfer(await _offlineSessionClient.CancelTransferAsync(
            TransferRequest(deviceId, operationId), await TransferOptionsAsync(cancellationToken)));

    public async Task<V2TransferOperation> CommitTransferAsync(
        string deviceId, Guid operationId, CancellationToken cancellationToken) =>
        ReadTransfer(await _offlineSessionClient.CommitTransferAsync(
            TransferRequest(deviceId, operationId), await TransferOptionsAsync(cancellationToken)));

    public async Task<V2LocalSessionLedger> GetTransferredLedgerAsync(
        string deviceId, V2TransferOperation operation, IOfflineSnapshotSignatureVerifier verifier,
        CancellationToken cancellationToken)
    {
        if (operation.Status != V2TransferStatus.Committed)
        {
            throw new InvalidOperationException("The transfer is not committed");
        }
        var response = await _offlineSessionClient.GetTransferredSnapshotAsync(
            TransferRequest(deviceId, operation.OperationId), await TransferOptionsAsync(cancellationToken));
        return V2OfflineSessionSnapshotReader.VerifyAndCreateTransferredLedger(
            response, verifier, operation.OperationId, operation.SessionId, deviceId);
    }

    private async Task<CallOptions> TransferOptionsAsync(CancellationToken cancellationToken) =>
        new(await CreateDeviceMetadataAsync(cancellationToken), DateTime.UtcNow.AddSeconds(10), cancellationToken);

    private static TransferV2Proto.TransferOperationRequest TransferRequest(string deviceId, Guid operationId) =>
        new() { DeviceId = deviceId, OperationId = operationId.ToString() };

    private static V2TransferOperation ReadTransfer(TransferV2Proto.TransferOperation operation) => new(
        Guid.Parse(operation.OperationId),
        Guid.Parse(operation.SessionId),
        Guid.Parse(operation.SourceWorkstationId),
        Guid.Parse(operation.TargetWorkstationId),
        operation.Status switch
        {
            "preparing" => V2TransferStatus.Preparing,
            "committed" => V2TransferStatus.Committed,
            "cancelled" => V2TransferStatus.Cancelled,
            "expired" => V2TransferStatus.Expired,
            _ => throw new InvalidOperationException("Unexpected V2 transfer status"),
        },
        operation.ExpiresAt.ToDateTimeOffset(),
        operation.TargetReady,
        operation.SourceCheckpoint is { } checkpoint
            ? new V2TransferCheckpoint(checkpoint.Sequence,
                string.IsNullOrEmpty(checkpoint.PayloadHash) ? null : checkpoint.PayloadHash)
            : null);
}
