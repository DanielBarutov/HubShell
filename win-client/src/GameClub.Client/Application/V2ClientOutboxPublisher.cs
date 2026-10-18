using GameClub.Client.Application.Ports;

namespace GameClub.Client.Application;

/// <summary>
/// Отправляет V2 outbox строго по порядку. При первой ошибке оставляет текущий
/// и следующие факты на диске для следующей попытки, чтобы не разорвать цепочку.
/// </summary>
public sealed class V2ClientOutboxPublisher
{
    private readonly V2LocalLedgerCoordinator _ledger;
    private readonly IV2ClientEventPublisher _publisher;

    public V2ClientOutboxPublisher(
        V2LocalLedgerCoordinator ledger,
        IV2ClientEventPublisher publisher)
    {
        _ledger = ledger;
        _publisher = publisher;
    }

    public async Task<int> PublishPendingAsync(CancellationToken cancellationToken = default)
        => (await TryPublishPendingAsync(cancellationToken)).PublishedCount;

    public async Task<V2OutboxPublishResult> TryPublishPendingAsync(
        CancellationToken cancellationToken = default)
    {
        var published = 0;
        var pending = await _ledger.ReadPendingOutboxAsync(cancellationToken);
        Exception? failure = null;
        foreach (var fact in pending)
        {
            try
            {
                await _publisher.PublishAsync(fact, cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception error)
            {
                failure = error;
                break;
            }
            await _ledger.AcknowledgeOutboxAsync([fact.EventId], cancellationToken);
            published++;
        }
        return new(
            published,
            pending.Count - published,
            failure);
    }
}

public sealed record V2OutboxPublishResult(
    int PublishedCount,
    int PendingCount,
    Exception? Failure)
{
    public bool IsSuccessful => Failure is null;
}
