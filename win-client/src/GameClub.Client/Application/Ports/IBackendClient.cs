using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IBackendClient : IAsyncDisposable, IWorkstationSessionGateway, IClientPortalGateway
{
    Task<ClientConnectionSnapshot> CheckConnectionAsync(
        CancellationToken cancellationToken = default);

    Task<WorkstationHeartbeatSnapshot> SendHeartbeatAsync(
        string deviceId,
        string clientVersion,
        IReadOnlyCollection<string> capabilities,
        CancellationToken cancellationToken = default);

    IAsyncEnumerable<WorkstationCommandSnapshot> WatchDeviceCommandsAsync(
        string deviceId,
        CancellationToken cancellationToken = default);

    Task<WorkstationCommandSnapshot> AcknowledgeDeviceCommandAsync(
        string commandId,
        string deviceId,
        bool success,
        string message,
        CancellationToken cancellationToken = default);
}
