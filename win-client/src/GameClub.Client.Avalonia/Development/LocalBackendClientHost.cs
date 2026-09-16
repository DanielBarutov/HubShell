using GameClub.Client.Application;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Infrastructure;
using GameClub.Client.Presentation;

namespace GameClub.Client.Avalonia.Development;

/// <summary>
/// Linux developer composition for the existing server-backed client flow.
/// It is intentionally loopback-only and does not provide a Linux substitute
/// for DPAPI, tray, restart, or kiosk policy.
/// </summary>
public sealed class LocalBackendClientHost : IClientHost
{
    private static readonly Uri LocalAuthAddress = new("http://127.0.0.1:8100");
    private static readonly Uri LocalGrpcAddress = new("http://127.0.0.1:51051");
    private readonly DeviceEnrollmentTokenProvider _enrollment;
    private bool _started;

    public LocalBackendClientHost()
    {
        _enrollment = new DeviceEnrollmentTokenProvider(LocalAuthAddress, "dev");
        ViewModel = new MainViewModel(
            new ClientSessionCoordinator(new GrpcBackendClient(LocalGrpcAddress, _enrollment)),
            new EnvironmentAccessCredentialVerifier("dev"),
            clientVersion: "avalonia-linux-smoke",
            capabilities: ["commands.v1", "sessions.v1", "widget.v1"]);
    }

    public MainViewModel ViewModel { get; }

    public string WindowTitle => "HubShell client — Linux developer host";

    public string HostDisclaimer => "Linux developer host: backend доступен только через loopback.";

    public IClientWindowAdapter? WindowAdapter => null;

    public async Task StartAsync()
    {
        if (_started)
        {
            return;
        }

        _started = true;
        await ViewModel.RefreshConnectionAsync();
        ViewModel.TrackBackgroundTask(ViewModel.RunHeartbeatLoopAsync());
        ViewModel.TrackBackgroundTask(ViewModel.RunAccessLockLoopAsync());
        ViewModel.TrackBackgroundTask(ActivateEnrollmentAsync());
    }

    public async ValueTask DisposeAsync()
    {
        await ViewModel.DisposeAsync();
        _enrollment.Dispose();
    }

    private async Task ActivateEnrollmentAsync()
    {
        while (string.IsNullOrWhiteSpace(_enrollment.DeviceId)
            && !ViewModel.LifetimeToken.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromSeconds(5), ViewModel.LifetimeToken);
            await ViewModel.RefreshConnectionAsync(ViewModel.LifetimeToken);
        }

        if (string.IsNullOrWhiteSpace(_enrollment.DeviceId))
        {
            return;
        }

        ViewModel.SetDeviceIdentity(
            _enrollment.DeviceId,
            _enrollment.WorkstationId,
            _enrollment.WorkstationName);
        ViewModel.TrackBackgroundTask(
            ViewModel.RunWorkstationHeartbeatLoopAsync(
                ViewModel.ApplyTheme,
                ViewModel.ApplyWorkstationName,
                ViewModel.ApplyManagerPasswordVerifier,
                ViewModel.ApplyLockdownPolicy,
                ViewModel.ApplySessionSnapshotFromHeartbeat,
                ViewModel.ApplyHeartbeatConnectionState));
    }
}
