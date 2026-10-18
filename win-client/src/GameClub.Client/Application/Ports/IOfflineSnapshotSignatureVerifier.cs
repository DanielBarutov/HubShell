namespace GameClub.Client.Application.Ports;

/// <summary>
/// Проверяет подпись snapshot по известному публичному ключу. Реализация не
/// хранит приватный ключ на игровом ПК.
/// </summary>
public interface IOfflineSnapshotSignatureVerifier
{
    bool Verify(
        string signingKeyId,
        ReadOnlyMemory<byte> payload,
        ReadOnlyMemory<byte> signature);
}
