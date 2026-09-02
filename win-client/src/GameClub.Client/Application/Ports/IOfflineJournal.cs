using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IOfflineJournal
{
    Task<long> NextSequenceAsync(
        string sessionId,
        CancellationToken cancellationToken = default);

    Task AppendAsync(
        OfflineOperationSnapshot operation,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<OfflineOperationSnapshot>> ReadPendingAsync(
        string sessionId,
        CancellationToken cancellationToken = default);

    Task AcknowledgeAsync(
        IReadOnlyCollection<string> operationIds,
        CancellationToken cancellationToken = default);
}
