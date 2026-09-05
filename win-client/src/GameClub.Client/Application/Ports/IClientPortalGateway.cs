using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IClientPortalGateway
{
    Task<ClientPortalAuthenticationSnapshot> RegisterAsync(
        string nickname,
        string phone,
        string password,
        string deviceId,
        CancellationToken cancellationToken = default);

    Task<ClientPortalAuthenticationSnapshot> LoginAsync(
        string identifier,
        string password,
        string deviceId,
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
        CancellationToken cancellationToken = default);

    void Logout();
}
