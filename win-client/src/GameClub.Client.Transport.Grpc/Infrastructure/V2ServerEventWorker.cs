using GameClub.Client.Application;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// Поддерживает опрос событий сервера с ограниченной экспоненциальной задержкой
/// между повторными попытками.
/// </summary>
public sealed class V2ServerEventWorker
{
    private readonly V2HttpServerEventConsumer _consumer;
    private readonly TimeSpan _pollInterval;
    private readonly TimeSpan _initialRetryDelay;
    private readonly TimeSpan _maximumRetryDelay;
    private readonly Func<TimeSpan, CancellationToken, Task> _delay;
    private readonly Action<Exception>? _onFailure;
    private readonly Action<V2ServerEventPollResult>? _onPoll;

    public V2ServerEventWorker(
        V2HttpServerEventConsumer consumer,
        TimeSpan? pollInterval = null,
        TimeSpan? initialRetryDelay = null,
        TimeSpan? maximumRetryDelay = null,
        Func<TimeSpan, CancellationToken, Task>? delay = null,
        Action<Exception>? onFailure = null,
        Action<V2ServerEventPollResult>? onPoll = null)
    {
        _consumer = consumer;
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
        _onPoll = onPoll;
    }

    public async Task RunAsync(CancellationToken cancellationToken = default)
    {
        var retryDelay = _initialRetryDelay;
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                var result = await _consumer.PollOnceAsync(cancellationToken);
                if (result.ReceivedCount > 0 || result.RejectedCount > 0)
                {
                    ClientLog.Info(
                        "v2.server-events",
                        $"poll received={result.ReceivedCount} " +
                        $"acknowledged={result.AcknowledgedCount} rejected={result.RejectedCount}");
                }
                _onPoll?.Invoke(result);
                retryDelay = _initialRetryDelay;
                await _delay(_pollInterval, cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception error)
            {
                ClientLog.Exception("v2.server-events", error, "server event poll failed");
                _onFailure?.Invoke(error);
                await _delay(retryDelay, cancellationToken);
                retryDelay = NextRetryDelay(retryDelay);
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
