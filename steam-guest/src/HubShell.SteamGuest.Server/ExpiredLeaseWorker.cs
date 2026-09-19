using HubShell.SteamGuest.Core;

namespace HubShell.SteamGuest.Server;

/// <summary>
/// Возвращает в пул аренды, от которых агент не подтверждал работу пять минут.
/// </summary>
public sealed class ExpiredLeaseWorker : BackgroundService
{
    public static readonly TimeSpan MaximumSilence = TimeSpan.FromMinutes(5);
    private static readonly TimeSpan CheckInterval = TimeSpan.FromSeconds(10);

    private readonly IGuestAccountStore _accounts;
    private readonly ILogger<ExpiredLeaseWorker> _logger;

    public ExpiredLeaseWorker(IGuestAccountStore accounts, ILogger<ExpiredLeaseWorker> logger)
    {
        _accounts = accounts;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(CheckInterval);
        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            try
            {
                var released = await _accounts.ReleaseExpiredAsync(
                    DateTimeOffset.UtcNow,
                    MaximumSilence,
                    stoppingToken);
                if (released > 0)
                {
                    _logger.LogWarning("Освобождено просроченных Steam-аренд: {ReleasedCount}", released);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                _logger.LogError(exception, "Не удалось проверить просроченные Steam-аренды.");
            }
        }
    }
}
