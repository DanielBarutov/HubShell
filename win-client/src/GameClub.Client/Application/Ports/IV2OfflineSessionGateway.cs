using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

/// <summary>
/// Получает единственный подписанный снимок входа V2. Реализация не создаёт
/// V1 portal-сессию и не запрашивает серверный timer.
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
}
