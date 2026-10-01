using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

/// <summary>
/// V2 client portal operations. This contract deliberately contains no V1
/// authentication or session methods.
/// </summary>
public interface IV2ClientPortalGateway
{
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
        CancellationToken cancellationToken = default);
}
