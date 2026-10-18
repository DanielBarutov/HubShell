using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using GameClub.Client.Presentation;
using System.Runtime.Versioning;

namespace GameClub.Client.Windows;

/// <summary>
/// Production-сборка общего окна Avalonia. Только здесь подключаются журнал DPAPI,
/// перезапуск Windows и цикл команд устройства. Linux developer-host их не имитирует.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class WindowsClientHost : IClientHost
{
    private readonly V2DeviceEnrollmentTokenProvider _enrollment;
    private readonly V2LocalLedgerRecoveryCoordinator _v2Recovery;
    private readonly HttpClient? _v2EventsHttpClient;
    private readonly V2ClientOutboxWorker? _v2OutboxWorker;
    private readonly V2ServerEventWorker? _v2ServerEventWorker;
    private readonly IWorkstationPowerController _powerController;
    private readonly WindowsClientWindowAdapter _windowAdapter;
    private bool _started;

    public WindowsClientHost()
    {
        var environment = DeploymentSettings.EnvironmentName;
        _enrollment = new V2DeviceEnrollmentTokenProvider(DeploymentSettings.GrpcAddress, environment);
        _powerController = new WindowsWorkstationPowerController();
        _windowAdapter = new WindowsClientWindowAdapter();
        var backend = new V2GrpcBackendClient(DeploymentSettings.GrpcAddress, _enrollment);
        var v2Ledger = new V2LocalLedgerCoordinator(new ProtectedV2LocalLedgerStore());
        _v2Recovery = new V2LocalLedgerRecoveryCoordinator(v2Ledger);
        Uri? v2ServerEventsEndpoint = null;
        if (DeploymentSettings.V2EventsHttpAddress is { } eventsAddress)
        {
            _v2EventsHttpClient = new HttpClient();
            _v2OutboxWorker = new V2ClientOutboxWorker(
                new V2ClientOutboxPublisher(
                    v2Ledger,
                    new V2HttpClientEventPublisher(
                        _v2EventsHttpClient,
                        eventsAddress,
                        _enrollment)));
            v2ServerEventsEndpoint = new Uri(eventsAddress, "/api/events/server");
        }
        var v2Login = new V2OfflineLoginCoordinator(backend, v2Ledger);
        var v2Verifier = new V2Ed25519OfflineSnapshotSignatureVerifier(
            DeploymentSettings.V2SnapshotPublicKeys);
        ViewModel = new MainViewModel(
            new ClientSessionCoordinator(
                backend,
                new JsonlOfflineJournal()),
            new EnvironmentAccessCredentialVerifier(environment),
            clientVersion: "avalonia-windows-v2",
            capabilities: ["display-lock.v2", "v2.local-ledger", "v2.device-commands", "widget.v2"],
            powerController: _powerController,
            timeNotificationPresenter: _windowAdapter,
            v2OfflineLogin: v2Login,
            v2Ledger: v2Ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(v2Ledger),
            v2SignatureVerifier: v2Verifier,
            v2GuestSession: backend);
        if (v2ServerEventsEndpoint is not null)
        {
            _v2ServerEventWorker = new V2ServerEventWorker(
                new V2HttpServerEventConsumer(
                    _v2EventsHttpClient!,
                    v2ServerEventsEndpoint,
                    _enrollment,
                    new V2ServerEventProcessor(v2Ledger)),
                onFailure: ViewModel.ApplyV2ServerEventTransportFailure,
                onPoll: result => ViewModel.ApplyV2ServerEventPollResult(result.RejectedCount));
        }
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
        _v2EventsHttpClient?.Dispose();
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
        await ViewModel.RecoverV2SessionAsync(_v2Recovery, ViewModel.LifetimeToken);
        if (_v2OutboxWorker is not null)
        {
            ViewModel.TrackBackgroundTask(_v2OutboxWorker.RunAsync(ViewModel.LifetimeToken));
        }
        if (_v2ServerEventWorker is not null)
        {
            ViewModel.TrackBackgroundTask(_v2ServerEventWorker.RunAsync(ViewModel.LifetimeToken));
        }
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
                ViewModel.ApplyHeartbeatConnectionState,
                () => ViewModel.LockClient("Место отключено администратором")));
        ViewModel.TrackBackgroundTask(
            ViewModel.RunCommandLoopAsync(
                new V2WindowsCommandExecutor(
                    _powerController,
                    reason => ViewModel.LockClient(reason))));
    }
}
