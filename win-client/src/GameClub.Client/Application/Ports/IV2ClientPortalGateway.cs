using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

/// <summary>
/// Операции личного кабинета V2. В контракте нет методов аутентификации
/// и управления сессиями V1.
/// </summary>
public interface IV2ClientPortalGateway
{
    Task CancelMinuteBonusAsync(V2MinuteBonusRequest request, CancellationToken cancellationToken = default);
    Task<BonusGameQuote> QuoteMinuteBonusAsync(V2MinuteBonusRequest request, CancellationToken cancellationToken = default);
    Task<V2MinuteBonusGrant> EnableMinuteBonusAsync(V2MinuteBonusRequest request,
        IOfflineSnapshotSignatureVerifier signatureVerifier, CancellationToken cancellationToken = default);
    Task<ClientPortalSnapshot> ResumePortalAsync(
        string deviceId,
        string sessionId,
        string clientId,
        CancellationToken cancellationToken = default, IOfflineSnapshotSignatureVerifier? signatureVerifier = null);

    Task<ClientPortalSnapshot> RefreshAsync(
        string deviceId,
        int limit = 50,
        CancellationToken cancellationToken = default, IOfflineSnapshotSignatureVerifier? signatureVerifier = null);

    Task<ClientPortalSnapshot> ActivateEntitlementAsync(
        string deviceId,
        string entitlementId,
        CancellationToken cancellationToken = default, IOfflineSnapshotSignatureVerifier? signatureVerifier = null);

    Task<ClientPortalSnapshot> PurchaseEntitlementAsync(
        string deviceId,
        string tariffId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default,
        BonusPurchaseConfirmation? bonusConfirmation = null);

    Task<BonusGameQuote> QuoteEntitlementAsync(
        string deviceId, string tariffId, bool useBonus,
        CancellationToken cancellationToken = default);
}
