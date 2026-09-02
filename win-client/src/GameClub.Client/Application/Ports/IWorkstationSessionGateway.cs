using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IWorkstationSessionGateway
{
    Task<SessionSnapshot> StartSessionAsync(
        string workstationId,
        string deviceId,
        string? clientId,
        string? guestName,
        string? reservationId,
        string idempotencyKey,
        CancellationToken cancellationToken = default,
        string? tariffId = null,
        int tariffQuantity = 1);

    Task<SessionSnapshot> StopSessionAsync(
        string sessionId,
        string deviceId,
        CancellationToken cancellationToken = default);

    Task<SessionSnapshot> GetSessionSnapshotAsync(
        string sessionId,
        string deviceId,
        CancellationToken cancellationToken = default);

    Task<SessionTransferOfferSnapshot> CreateTransferOfferAsync(
        string sessionId,
        string targetWorkstationId,
        string deviceId,
        string idempotencyKey,
        CancellationToken cancellationToken = default);

    Task<SessionTransferOfferSnapshot> GetTransferOfferAsync(
        string offerId,
        string deviceId,
        string token,
        CancellationToken cancellationToken = default);

    Task<SessionTransferResultSnapshot> ConfirmTransferAsync(
        string offerId,
        string deviceId,
        string token,
        string idempotencyKey,
        CancellationToken cancellationToken = default);

    Task<OfflineBatchResultSnapshot> ReplayOfflineBatchAsync(
        string sessionId,
        string deviceId,
        IReadOnlyCollection<OfflineOperationSnapshot> operations,
        CancellationToken cancellationToken = default);
}
