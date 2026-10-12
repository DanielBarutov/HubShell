using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

/// <summary>
/// Операции личного кабинета V2. В контракте нет методов аутентификации
/// и управления сессиями V1.
/// </summary>
public interface IV2ClientPortalGateway
{
    Task<ClientPortalSnapshot> ResumePortalAsync(
        string deviceId,
        string sessionId,
        string clientId,
        CancellationToken cancellationToken = default);

    Task<ClientPortalSnapshot> RefreshAsync(
        string deviceId,
        int limit = 50,
        CancellationToken cancellationToken = default);

    Task<ClientPortalSnapshot> ActivateEntitlementAsync(
        string deviceId,
        string entitlementId,
        CancellationToken cancellationToken = default);

    Task<ClientPortalSnapshot> PurchaseEntitlementAsync(
        string deviceId,
        string tariffId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default);
}
