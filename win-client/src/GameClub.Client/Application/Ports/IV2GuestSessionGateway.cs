using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IV2GuestSessionGateway
{
    Task<V2LocalSessionLedger?> RedeemPendingGuestAccessAsync(
        string deviceId,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default,
        V2LocalSessionLedger? activeGuestLedger = null);

    Task StopGuestSessionAsync(
        string deviceId,
        string sessionId,
        string paymentId,
        CancellationToken cancellationToken = default);
}
