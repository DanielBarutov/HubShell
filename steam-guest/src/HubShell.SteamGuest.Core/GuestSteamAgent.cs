namespace HubShell.SteamGuest.Core;

/// <summary>
/// Выдаёт один аккаунт станции, запускает Steam и регулярно подтверждает
/// серверу, что агент и Steam всё ещё работают на этой станции.
/// </summary>
public sealed class GuestSteamAgent
{
    public static readonly TimeSpan ConfirmationInterval = TimeSpan.FromSeconds(30);

    private readonly IGuestAccountStore _accounts;
    private readonly ISteamLauncher _launcher;
    private readonly Func<DateTimeOffset> _clock;
    private readonly TimeSpan _confirmationInterval;

    public GuestSteamAgent(
        IGuestAccountStore accounts,
        ISteamLauncher launcher,
        Func<DateTimeOffset>? clock = null,
        TimeSpan? confirmationInterval = null)
    {
        _accounts = accounts;
        _launcher = launcher;
        _clock = clock ?? (() => DateTimeOffset.UtcNow);
        _confirmationInterval = confirmationInterval ?? ConfirmationInterval;
        if (_confirmationInterval <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(confirmationInterval));
        }
    }

    public async Task RunAsync(
        string stationId,
        string stationKey,
        CancellationToken cancellationToken = default)
    {
        var lease = await _accounts.ClaimAsync(stationId, stationKey, _clock(), cancellationToken);
        ISteamProcess? steam = null;
        try
        {
            steam = await _launcher.StartAsync(lease.Credentials, cancellationToken);
            using var confirmationLifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            var confirmationTask = ConfirmWhileSteamRunsAsync(
                stationId,
                stationKey,
                lease.LeaseId,
                confirmationLifetime.Token);
            try
            {
                await steam.WaitForExitAsync(cancellationToken);
            }
            finally
            {
                confirmationLifetime.Cancel();
                await IgnoreCancellationAsync(confirmationTask);
            }

            var released = await _accounts.ReleaseAsync(
                stationId,
                stationKey,
                lease.LeaseId,
                _clock(),
                cancellationToken);
            if (!released)
            {
                throw new InvalidOperationException("Не удалось подтвердить освобождение Steam-аккаунта.");
            }
        }
        catch
        {
            // Не освобождаем аренду после ошибки запуска: иначе два ПК смогут
            // одновременно использовать один аккаунт, пока первый Steam ещё жив.
            throw;
        }
    }

    private async Task ConfirmWhileSteamRunsAsync(
        string stationId,
        string stationKey,
        Guid leaseId,
        CancellationToken cancellationToken)
    {
        using var timer = new PeriodicTimer(_confirmationInterval);
        while (await timer.WaitForNextTickAsync(cancellationToken))
        {
            try
            {
                await _accounts.RenewAsync(stationId, stationKey, leaseId, _clock(), cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch
            {
                // При временной потере сервера не останавливаем Steam. Если связь
                // не вернётся за пять минут, сервер сам освободит аренду.
            }
        }
    }

    private static async Task IgnoreCancellationAsync(Task task)
    {
        try
        {
            await task;
        }
        catch (OperationCanceledException)
        {
        }
    }
}
