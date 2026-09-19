using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using GameClub.Client.Presentation;
using System.Runtime.Versioning;

namespace GameClub.Client.Windows;

/// <summary>
/// Production-only composition for the shared Avalonia window. This is the
/// only place where DPAPI journal, Windows restart and the device command loop
/// are wired; the Linux developer host deliberately does not emulate them.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class WindowsClientHost : IClientHost
{
    private readonly DeviceEnrollmentTokenProvider _enrollment;
    private readonly IWorkstationPowerController _powerController;
    private readonly WindowsClientWindowAdapter _windowAdapter;
    private bool _started;

    public WindowsClientHost()
    {
        var environment = DeploymentSettings.EnvironmentName;
        _enrollment = new DeviceEnrollmentTokenProvider(DeploymentSettings.AuthAddress, environment);
        _powerController = new WindowsWorkstationPowerController();
        _windowAdapter = new WindowsClientWindowAdapter();
        ViewModel = new MainViewModel(
            new ClientSessionCoordinator(
                new GrpcBackendClient(DeploymentSettings.GrpcAddress, _enrollment),
                new JsonlOfflineJournal()),
            new EnvironmentAccessCredentialVerifier(environment),
            clientVersion: "avalonia-windows",
            capabilities: ["commands.v1", "display-lock.v1", "theme.v1", "sessions.v1", "widget.v1"],
            powerController: _powerController,
            timeNotificationPresenter: _windowAdapter);
    }

    public MainViewModel ViewModel { get; }

    public string WindowTitle => "HubShell";

    public string HostDisclaimer => "Клиент подключается к назначенному серверу клуба.";

    public IClientWindowAdapter? WindowAdapter => _windowAdapter;

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
        ViewModel.TrackBackgroundTask(ViewModel.RunSessionCountdownLoopAsync());
        ViewModel.TrackBackgroundTask(ActivateEnrollmentAsync());
    }

    public async ValueTask DisposeAsync()
    {
        WindowAdapter?.Dispose();
        await ViewModel.DisposeAsync();
        _enrollment.Dispose();
    }

    private async Task ActivateEnrollmentAsync()
    {
        while (string.IsNullOrWhiteSpace(_enrollment.DeviceId)
            && !ViewModel.LifetimeToken.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromSeconds(10), ViewModel.LifetimeToken);
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
        var deviceId = ViewModel.DeviceId;
        if (string.IsNullOrWhiteSpace(deviceId))
        {
            return;
        }

        ViewModel.TrackBackgroundTask(
            ViewModel.RunWorkstationHeartbeatLoopAsync(
                ViewModel.ApplyTheme,
                ViewModel.ApplyWorkstationName,
                ViewModel.ApplyManagerPasswordVerifier,
                ViewModel.ApplyLockdownPolicy,
                ViewModel.ApplySessionSnapshotFromHeartbeat,
                ViewModel.ApplyHeartbeatConnectionState));
        ViewModel.TrackBackgroundTask(
            ViewModel.RunCommandLoopAsync(
                new WindowsCommandExecutor(
                    deviceId,
                    ViewModel.BackendClient,
                    ViewModel.ApplyTheme,
                    _powerController,
                    ViewModel.RegisterSessionStarted,
                    session =>
                    {
                        ViewModel.RegisterSessionStopped(session);
                        _ = SteamGuestSessionStopSignalPublisher.PublishAsync();
                    },
                    () => ViewModel.LockClient())));
    }
}
