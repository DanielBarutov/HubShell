using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

/// <summary>
/// Постоянная V2-запись: ledger и outbox сохраняются только вместе.
/// </summary>
public interface IV2LocalLedgerStore
{
    Task<V2LocalLedgerStorageSnapshot?> ReadAsync(
        CancellationToken cancellationToken = default);

    Task WriteAsync(
        V2LocalLedgerStorageSnapshot snapshot,
        CancellationToken cancellationToken = default);
}
