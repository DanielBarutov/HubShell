using HubShell.SteamGuest.Core;
using Xunit;

namespace HubShell.SteamGuest.Tests;

public sealed class GuestSteamAgentTests
{
    [Fact]
    public async Task Завершение_Steam_освобождает_один_аккаунт()
    {
        var accounts = new RecordingAccounts();
        var steam = new CompletedSteamProcess();
        var agent = new GuestSteamAgent(
            accounts,
            new RecordingLauncher(steam),
            () => new DateTimeOffset(2026, 9, 19, 12, 0, 0, TimeSpan.Zero));

        await agent.RunAsync("vip-03", "station-secret");

        Assert.Equal(1, accounts.ReleaseCalls);
        Assert.Equal("vip-03", accounts.ReleasedStationId);
    }

    [Fact]
    public async Task Работающий_Steam_регулярно_подтверждает_аренду_до_завершения_процесса()
    {
        var accounts = new RecordingAccounts();
        var steam = new WaitingSteamProcess();
        var agent = new GuestSteamAgent(
            accounts,
            new RecordingLauncher(steam),
            confirmationInterval: TimeSpan.FromMilliseconds(1));

        var running = agent.RunAsync("vip-03", "station-secret");
        await accounts.Renewed.Task.WaitAsync(TimeSpan.FromSeconds(1));
        steam.Exit();
        await running;

        Assert.True(accounts.RenewCalls >= 1);
        Assert.Equal(1, accounts.ReleaseCalls);
    }

    [Fact]
    public async Task Ошибка_запуска_Steam_не_освобождает_аккаунт_автоматически()
    {
        var accounts = new RecordingAccounts();
        var agent = new GuestSteamAgent(
            accounts,
            new FailingLauncher());

        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync("vip-03", "station-secret"));

        Assert.Equal(0, accounts.ReleaseCalls);
    }

    private sealed class RecordingAccounts : IGuestAccountStore
    {
        public int ReleaseCalls { get; private set; }
        public int RenewCalls { get; private set; }
        public string? ReleasedStationId { get; private set; }
        public TaskCompletionSource Renewed { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task RegisterStationAsync(string stationId, string stationKey, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task<Guid> AddAccountAsync(SteamCredentials credentials, CancellationToken cancellationToken = default) => Task.FromResult(Guid.Empty);
        public Task<IReadOnlyCollection<GuestAccountSummary>> ListAsync(CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyCollection<GuestAccountSummary>>(Array.Empty<GuestAccountSummary>());

        public Task<GuestAccountLease> ClaimAsync(string stationId, string stationKey, DateTimeOffset now, CancellationToken cancellationToken = default) =>
            Task.FromResult(new GuestAccountLease(Guid.Parse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), Guid.Parse("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"), stationId, new SteamCredentials("guest", "secret"), now));

        public Task<bool> ReleaseAsync(string stationId, string stationKey, Guid leaseId, DateTimeOffset now, CancellationToken cancellationToken = default)
        {
            ReleaseCalls++;
            ReleasedStationId = stationId;
            return Task.FromResult(true);
        }

        public Task<bool> RenewAsync(string stationId, string stationKey, Guid leaseId, DateTimeOffset now, CancellationToken cancellationToken = default)
        {
            RenewCalls++;
            Renewed.TrySetResult();
            return Task.FromResult(true);
        }

        public Task<int> ReleaseExpiredAsync(DateTimeOffset now, TimeSpan maximumSilence, CancellationToken cancellationToken = default) =>
            Task.FromResult(0);
    }

    private sealed class RecordingLauncher : ISteamLauncher
    {
        private readonly ISteamProcess _process;
        public RecordingLauncher(ISteamProcess process) => _process = process;
        public Task<ISteamProcess> StartAsync(SteamCredentials credentials, CancellationToken cancellationToken = default) => Task.FromResult(_process);
    }

    private sealed class FailingLauncher : ISteamLauncher
    {
        public Task<ISteamProcess> StartAsync(SteamCredentials credentials, CancellationToken cancellationToken = default) =>
            throw new InvalidOperationException("Steam не запустилась");
    }

    private sealed class CompletedSteamProcess : ISteamProcess
    {
        public Task StopAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task WaitForExitAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
    }

    private sealed class WaitingSteamProcess : ISteamProcess
    {
        private readonly TaskCompletionSource _exited = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task StopAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task WaitForExitAsync(CancellationToken cancellationToken = default) => _exited.Task;
        public void Exit() => _exited.TrySetResult();
    }
}
