namespace HubShell.SteamGuest.Core;

/// <summary>
/// Выдаёт один аккаунт станции, запускает Steam и освобождает его только после
/// завершения Steam либо локального подтверждённого сигнала завершения сессии.
/// </summary>
public sealed class GuestSteamAgent
{
    private readonly IGuestAccountStore _accounts;
    private readonly ISteamLauncher _launcher;
    private readonly ISessionStopSignal _stopSignal;
    private readonly Func<DateTimeOffset> _clock;

    public GuestSteamAgent(
        IGuestAccountStore accounts,
        ISteamLauncher launcher,
        ISessionStopSignal stopSignal,
        Func<DateTimeOffset>? clock = null)
    {
        _accounts = accounts;
        _launcher = launcher;
        _stopSignal = stopSignal;
        _clock = clock ?? (() => DateTimeOffset.UtcNow);
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
            var stopTask = _stopSignal.WaitAsync(cancellationToken);
            var exitTask = steam.WaitForExitAsync(cancellationToken);
            var completed = await Task.WhenAny(stopTask, exitTask);
            await completed;
            if (completed == stopTask)
            {
                await steam.StopAsync(cancellationToken);
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
}
