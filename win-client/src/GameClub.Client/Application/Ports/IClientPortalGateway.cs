using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IClientPortalGateway
{
    Task<ClientPortalAuthenticationSnapshot> RegisterAsync(
        string nickname,
        string phone,
        string pin,
        string deviceId,
        CancellationToken cancellationToken = default);

    Task<ClientPortalAuthenticationSnapshot> LoginAsync(
        string identifier,
        string pin,
        string deviceId,
        CancellationToken cancellationToken = default);

    Task<ClientPortalSnapshot> RefreshAsync(
        string deviceId,
        int limit = 50,
        CancellationToken cancellationToken = default);

    void Logout();
}
