using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

/// <summary>
/// Транспорт V2 входа и явного завершения сессии. Он не создаёт V1
/// portal-сессию и не запрашивает server-side timer.
/// </summary>
public interface IV2OfflineSessionGateway
{
    Task<V2OfflineLoginResult> RegisterAsync(
        string nickname,
        string phone,
        string password,
        string deviceId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default);

    Task<V2OfflineLoginResult> LoginAsync(
        string identifier,
        string password,
        string deviceId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default);

    Task ChangePasswordAsync(
        string newPassword,
        string deviceId,
        string resetToken,
        CancellationToken cancellationToken = default);

    Task StopSessionAsync(
        string deviceId,
        string sessionId,
        string clientId,
        CancellationToken cancellationToken = default);
}
