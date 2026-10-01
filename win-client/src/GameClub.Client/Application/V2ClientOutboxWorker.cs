namespace GameClub.Client.Application;

/// <summary>
/// Держит V2 outbox живым на протяжении процесса. Worker не перескакивает
/// через первый неподтверждённый факт: ошибка транспорта только увеличивает
/// задержку следующей попытки, а локальная запись остаётся источником истины.
/// </summary>
public sealed class V2ClientOutboxWorker
{
    private readonly V2ClientOutboxPublisher _publisher;
    private readonly TimeSpan _pollInterval;
    private readonly TimeSpan _initialRetryDelay;
    private readonly TimeSpan _maximumRetryDelay;
    private readonly Func<TimeSpan, CancellationToken, Task> _delay;
    private readonly Action<Exception>? _onFailure;

    public V2ClientOutboxWorker(
        V2ClientOutboxPublisher publisher,
        TimeSpan? pollInterval = null,
        TimeSpan? initialRetryDelay = null,
        TimeSpan? maximumRetryDelay = null,
        Func<TimeSpan, CancellationToken, Task>? delay = null,
        Action<Exception>? onFailure = null)
    {
        _publisher = publisher;
        _pollInterval = pollInterval ?? TimeSpan.FromSeconds(5);
        _initialRetryDelay = initialRetryDelay ?? TimeSpan.FromSeconds(2);
        _maximumRetryDelay = maximumRetryDelay ?? TimeSpan.FromMinutes(1);
        if (_pollInterval <= TimeSpan.Zero
            || _initialRetryDelay <= TimeSpan.Zero
            || _maximumRetryDelay < _initialRetryDelay)
        {
            throw new ArgumentOutOfRangeException(nameof(pollInterval));
        }
        _delay = delay ?? Task.Delay;
        _onFailure = onFailure;
    }

    public async Task RunAsync(CancellationToken cancellationToken = default)
    {
        var retryDelay = _initialRetryDelay;
        while (!cancellationToken.IsCancellationRequested)
        {
            V2OutboxPublishResult result;
            try
            {
                result = await _publisher.TryPublishPendingAsync(cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception error)
            {
                result = new(0, 0, error);
            }

            if (result.Failure is not null)
            {
                _onFailure?.Invoke(result.Failure);
                await _delay(retryDelay, cancellationToken);
                retryDelay = NextRetryDelay(retryDelay);
            }
            else
            {
                retryDelay = _initialRetryDelay;
                await _delay(_pollInterval, cancellationToken);
            }
        }
    }

    private TimeSpan NextRetryDelay(TimeSpan current) => current >= _maximumRetryDelay
        ? _maximumRetryDelay
        : TimeSpan.FromTicks(Math.Min(
            _maximumRetryDelay.Ticks,
            current.Ticks > _maximumRetryDelay.Ticks / 2
                ? _maximumRetryDelay.Ticks
                : current.Ticks * 2));
}
