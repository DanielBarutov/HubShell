using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public sealed record V2TransferTarget(Guid WorkstationId, string Name, string? GroupId);

public sealed record V2TransferQuote(
    string Token,
    long? PerMinutePriceCents,
    string? BurnedPackageName,
    int? BurnedPackageMinutes,
    int? FallbackGrantMinutes);

public sealed record V2TransferOperation(
    Guid OperationId,
    Guid SessionId,
    Guid SourceWorkstationId,
    Guid TargetWorkstationId,
    V2TransferStatus Status,
    DateTimeOffset ExpiresAt,
    bool TargetReady,
    V2TransferCheckpoint? SourceCheckpoint);

public interface IV2SessionTransferGateway
{
    Task<IReadOnlyList<V2TransferTarget>> ListTransferTargetsAsync(
        string deviceId, Guid sessionId, CancellationToken cancellationToken);
    Task<V2TransferQuote> QuoteTransferAsync(
        string deviceId, Guid sessionId, Guid targetWorkstationId, CancellationToken cancellationToken);
    Task<V2TransferOperation> BeginTransferAsync(
        string deviceId, Guid sessionId, V2PendingSourceTransfer request, CancellationToken cancellationToken);
    Task<V2TransferOperation?> GetPendingTransferAsync(string deviceId, CancellationToken cancellationToken);
    Task<V2TransferOperation> GetTransferOperationAsync(
        string deviceId, Guid operationId, CancellationToken cancellationToken);
    Task<V2TransferOperation> ReadyTransferTargetAsync(
        string deviceId, Guid operationId, CancellationToken cancellationToken);
    Task<V2TransferOperation> ConfirmTransferSourceAsync(
        string deviceId, Guid operationId, V2TransferCheckpoint checkpoint, CancellationToken cancellationToken);
    Task<V2TransferOperation> CancelTransferAsync(
        string deviceId, Guid operationId, CancellationToken cancellationToken);
    Task<V2TransferOperation> CommitTransferAsync(
        string deviceId, Guid operationId, CancellationToken cancellationToken);
    Task<V2LocalSessionLedger> GetTransferredLedgerAsync(
        string deviceId, V2TransferOperation operation, IOfflineSnapshotSignatureVerifier verifier,
        CancellationToken cancellationToken);
}
