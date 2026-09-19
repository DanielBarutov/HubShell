using HubShell.SteamGuest.Core;
using Xunit;

namespace HubShell.SteamGuest.Tests;

public sealed class GuestSteamAgentTests
{
    [Fact]
    public async Task Завершение_сессии_закрывает_Steam_и_освобождает_один_аккаунт()
    {
        var accounts = new RecordingAccounts();
        var steam = new RecordingSteamProcess();
        var agent = new GuestSteamAgent(
            accounts,
            new RecordingLauncher(steam),
            new CompletedStopSignal(),
            () => new DateTimeOffset(2026, 9, 19, 12, 0, 0, TimeSpan.Zero));

        await agent.RunAsync("vip-03", "station-secret");

        Assert.True(steam.Stopped);
        Assert.Equal(1, accounts.ReleaseCalls);
        Assert.Equal("vip-03", accounts.ReleasedStationId);
    }

    [Fact]
    public async Task Ошибка_запуска_Steam_не_освобождает_аккаунт_автоматически()
    {
        var accounts = new RecordingAccounts();
        var agent = new GuestSteamAgent(
            accounts,
            new FailingLauncher(),
            new CompletedStopSignal());

        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync("vip-03", "station-secret"));

        Assert.Equal(0, accounts.ReleaseCalls);
    }

    private sealed class RecordingAccounts : IGuestAccountStore
    {
        public int ReleaseCalls { get; private set; }
        public string? ReleasedStationId { get; private set; }

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

    private sealed class RecordingSteamProcess : ISteamProcess
    {
        public bool Stopped { get; private set; }
        public Task StopAsync(CancellationToken cancellationToken = default)
        {
            Stopped = true;
            return Task.CompletedTask;
        }
        public Task WaitForExitAsync(CancellationToken cancellationToken = default) => new TaskCompletionSource().Task;
    }

    private sealed class CompletedStopSignal : ISessionStopSignal
    {
        public Task WaitAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
    }
}
