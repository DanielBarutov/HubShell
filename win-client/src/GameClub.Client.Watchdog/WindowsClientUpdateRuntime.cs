using System.Diagnostics;
using System.Runtime.Versioning;
using GameClub.Client.Infrastructure.Updates;
using GameClub.Client.Windows;

namespace GameClub.Client.Watchdog;

[SupportedOSPlatform("windows")]
internal sealed class WindowsClientUpdateRuntime : IUpdateGuiPlatform
{
    private readonly ClientWatchdogService _service;
    private readonly string _directory = AppContext.BaseDirectory;
    private readonly WindowsUpdateGuiClient _pipe = new(AppContext.BaseDirectory);
    private readonly ClientUpdateStateStore _state = new(AppContext.BaseDirectory);
    private int Session => checked((int)(ClientWatchdogService.ConsoleSessionId
        ?? throw new InvalidOperationException("No interactive console session")));

    private WindowsClientUpdateRuntime(ClientWatchdogService service) => _service = service;

    internal static bool RequiresRecovery()
    {
        try { return new ClientUpdateStateStore(AppContext.BaseDirectory).Read()?.Stage is
            "closing" or "backup_pending" or "replace_pending" or "verifying" or "installed"; }
        catch { return true; }
    }

    internal static async Task RunAsync(ClientWatchdogService service, CancellationToken token)
    {
        try
        {
            var settings = WindowsUpdaterSettings.Load(AppContext.BaseDirectory);
            if (settings is null)
            {
                await ClientUpdateAgent.RecoverLocalAsync(AppContext.BaseDirectory, new WindowsClientUpdateRuntime(service), token);
                return;
            }
            using var handler = new HttpClientHandler { AllowAutoRedirect = false };
            using var http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(20) };
            var agent = new ClientUpdateAgent(http, new Uri(settings.BackendAddress), settings.DeviceId,
                settings.InstallationId, settings.DecryptSecret(), settings.TrustedPublicKeyPem,
                AppContext.BaseDirectory, new WindowsClientUpdateRuntime(service));
            using var timer = new PeriodicTimer(TimeSpan.FromSeconds(5));
            do
            {
                try { await agent.TickAsync(token); }
                catch (OperationCanceledException) when (token.IsCancellationRequested) { break; }
                catch (Exception error) { service.WriteUpdateLog(error.GetType().Name); }
            } while (await timer.WaitForNextTickAsync(token));
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        catch (Exception error)
        {
            service.WriteUpdateLog("configuration_" + error.GetType().Name);
            try { await ClientUpdateAgent.RecoverLocalAsync(AppContext.BaseDirectory, new WindowsClientUpdateRuntime(service), token); }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { }
            catch (Exception recoveryError) when (!token.IsCancellationRequested)
            { service.WriteUpdateLog("recovery_" + recoveryError.GetType().Name); }
        }
    }

    public Task PauseRecoveryAsync(CancellationToken token) => _service.PauseRecoveryAsync(token);
    public Task ResumeRecoveryAsync(CancellationToken token) => _service.ResumeRecoveryAsync(token);
    public Task<UpdateIpcStatus> QueryAsync(UpdateIpcRequest request, CancellationToken token) => _pipe.RequestAsync(Session, request, token);
    public Task StartGuiAsync(CancellationToken token) => _service.StartGuiForUpdateAsync(token);

    private IEnumerable<Process> InstalledGuiProcesses()
    {
        var session = Session;
        foreach (var process in Process.GetProcessesByName("HubShell"))
        {
            bool matches;
            try { matches = process.SessionId == session && string.Equals(process.MainModule?.FileName,
                Path.Combine(_directory, "HubShell.exe"), StringComparison.OrdinalIgnoreCase); }
            catch { process.Dispose(); continue; }
            if (matches) yield return process;
            else process.Dispose();
        }
    }

    public async Task WaitForExitAsync(CancellationToken token)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
        timeout.CancelAfter(TimeSpan.FromSeconds(15));
        foreach (var process in InstalledGuiProcesses())
            using (process) await process.WaitForExitAsync(timeout.Token);
    }

    public async Task StopFailedGuiAsync(CancellationToken token)
    {
        var local = _state.Read();
        if (local is not { Blocked: true }) throw new InvalidOperationException("Recovery requires a durable update block");
        try
        {
            var status = await QueryAsync(new("status", local.DeploymentId, local.RoundId), token);
            if (status.ActiveSession || status.PendingFacts != 0)
                throw new InvalidOperationException("An active ledger prevents forced recovery");
        }
        catch (Exception error) when (error is IOException or TimeoutException or System.ComponentModel.Win32Exception
            || error is OperationCanceledException && !token.IsCancellationRequested) { }
        foreach (var process in InstalledGuiProcesses())
            using (process)
            {
                if (!process.HasExited) process.Kill();
                await process.WaitForExitAsync(token);
            }
    }
}
