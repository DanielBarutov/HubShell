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
}
