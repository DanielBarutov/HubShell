using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IBackendClient : IAsyncDisposable, IWorkstationSessionGateway
{
    Task<ClientConnectionSnapshot> CheckConnectionAsync(
        CancellationToken cancellationToken = default);

    Task<WorkstationHeartbeatSnapshot> SendHeartbeatAsync(
        string deviceId,
        string clientVersion,
        IReadOnlyCollection<string> capabilities,
        CancellationToken cancellationToken = default);

    IAsyncEnumerable<WorkstationCommandSnapshot> WatchCommandsAsync(
        string deviceId,
        CancellationToken cancellationToken = default);

    Task<WorkstationCommandSnapshot> AcknowledgeCommandAsync(
        string commandId,
        string deviceId,
        bool success,
        string message,
        CancellationToken cancellationToken = default);
}
