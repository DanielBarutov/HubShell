using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using GameClub.Client.Presentation;
using System.Runtime.Versioning;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using GameClub.Client.Infrastructure.Updates;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Threading;

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
    private bool _updateRecoveryCompleted;
    private bool _updateStateFault;
    private readonly V2LocalLedgerCoordinator _v2Ledger;
    private readonly ClientUpdateStateStore _updateState = new(AppContext.BaseDirectory);

    public WindowsClientHost()
    {
        var environment = DeploymentSettings.EnvironmentName;
        _enrollment = new V2DeviceEnrollmentTokenProvider(DeploymentSettings.GrpcAddress, environment);
        _powerController = new WindowsWorkstationPowerController();
        _windowAdapter = new WindowsClientWindowAdapter();
        var backend = new V2GrpcBackendClient(DeploymentSettings.GrpcAddress, _enrollment);
        var v2Ledger = _v2Ledger = new V2LocalLedgerCoordinator(new ProtectedV2LocalLedgerStore());
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
            clientVersion: UpdateIpcProtocol.ReleaseId(typeof(Program).Assembly),
            capabilities: ["display-lock.v2", "v2.local-ledger", "v2.device-commands", "widget.v2", "client-updates.v1"],
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
        try { ViewModel.ApplyDeploymentBlock(_updateState.Read()?.Blocked == true); }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException)
        {
            _updateStateFault = true;
            ViewModel.ApplyDeploymentBlock(true);
        }
        var updatePipe = new WindowsGuiUpdatePipe(HandleUpdateRequestAsync, () =>
            Dispatcher.UIThread.Post(() =>
            {
                if (global::Avalonia.Application.Current?.ApplicationLifetime is IClassicDesktopStyleApplicationLifetime lifetime)
                    lifetime.Shutdown();
            }));
        ViewModel.TrackBackgroundTask(updatePipe.RunAsync(ViewModel.LifetimeToken));
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
        _updateRecoveryCompleted = true;
        if (_v2EventsHttpClient is not null && DeploymentSettings.V2EventsHttpAddress is not null)
            ViewModel.TrackBackgroundTask(RunGuiUpdateLoopAsync(ViewModel.LifetimeToken));
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

    private async Task<UpdateIpcStatus> HandleUpdateRequestAsync(UpdateIpcRequest request, CancellationToken token)
    {
        ClientUpdateJournal? journal;
        try { journal = _updateState.Read(); }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException)
        {
            _updateStateFault = true;
            journal = null;
            ViewModel.ApplyDeploymentBlock(true);
        }
        var matches = journal is not null && journal.DeploymentId == request.DeploymentId
            && journal.RoundId == request.RoundId;
        if (request.Command == "prepare" && matches && journal!.Blocked)
            ViewModel.ApplyDeploymentBlock(true);
        if (request.Command == "release" && matches && !journal!.Blocked && !_updateStateFault)
            ViewModel.ApplyDeploymentBlock(false);
        bool active;
        int pending;
        V2LocalLedgerStorageSnapshot? snapshot = null;
        try
        {
            snapshot = await _v2Ledger.ReadSnapshotAsync(token);
            active = ViewModel.HasActiveGameSession || snapshot?.Ledger.Status is
                V2LocalSessionStatus.Active or V2LocalSessionStatus.NeedsReview;
            pending = snapshot?.PendingOutbox.Count ?? 0;
            if (snapshot?.PendingPortalPackagePurchase is not null) pending++;
            if (snapshot?.PendingMinuteBonusRequest is not null || snapshot?.MinuteBonusCancellationPending == true) pending++;
            pending += snapshot?.ServerEventIssues?.Count ?? 0;
        }
        catch (Exception error) when (error is not OperationCanceledException)
        {
            active = true;
            pending = 1;
        }
        var ready = _updateRecoveryCompleted && !_updateStateFault && !active && pending == 0
            && !string.IsNullOrWhiteSpace(_enrollment.DeviceId) && _v2EventsHttpClient is not null;
        var closing = request.Command == "close" && ready && matches && journal!.Blocked
            && ViewModel.IsDeploymentBlocked;
        if (closing) ViewModel.AuthorizeUpdateShutdown();
        return new UpdateIpcStatus(_enrollment.DeviceId, _enrollment.InstallationId,
            UpdateIpcProtocol.ReleaseId(typeof(Program).Assembly), active, pending, ready,
            ViewModel.IsDeploymentBlocked, closing, ready ? null : "gui_not_ready",
            snapshot?.Ledger.SessionId, snapshot?.Ledger.NextSequence - 1 ?? 0,
            snapshot?.Ledger.PreviousPayloadHash);
    }

    private async Task RunGuiUpdateLoopAsync(CancellationToken token)
    {
        var endpoint = new Uri(DeploymentSettings.V2EventsHttpAddress!, "/api/v1/client-updates/gui/current");
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(5));
        do
        {
            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, endpoint);
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", await _enrollment.GetAccessTokenAsync(token));
                using var response = await _v2EventsHttpClient!.SendAsync(request, token);
                response.EnsureSuccessStatusCode();
                using var document = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(token), cancellationToken: token);
                var deployment = document.RootElement.GetProperty("deployment");
                if (deployment.ValueKind != JsonValueKind.Null)
                {
                    var journalBlocked = true;
                    try { journalBlocked = _updateState.Read()?.Blocked == true; }
                    catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException)
                    { _updateStateFault = true; }
                    ViewModel.ApplyDeploymentBlock(_updateStateFault || journalBlocked || deployment.GetProperty("block_gui").GetBoolean());
                    if (deployment.GetProperty("phase").GetString() == "authorized"
                        && deployment.GetProperty("release_id").GetString() == UpdateIpcProtocol.ReleaseId(typeof(Program).Assembly))
                    {
                        var local = await HandleUpdateRequestAsync(new UpdateIpcRequest("status",
                            deployment.GetProperty("id").GetGuid(), deployment.GetProperty("round_id").GetGuid()), token);
                        if (!local.Ready || !local.Blocked) continue;
                        using var confirm = new HttpRequestMessage(HttpMethod.Post, new Uri(endpoint,
                            $"/api/v1/client-updates/{deployment.GetProperty("id").GetString()}/gui-confirm"));
                        confirm.Headers.Authorization = request.Headers.Authorization;
                        confirm.Content = JsonContent.Create(new { release_id = UpdateIpcProtocol.ReleaseId(typeof(Program).Assembly) });
                        using var confirmed = await _v2EventsHttpClient.SendAsync(confirm, token);
                        confirmed.EnsureSuccessStatusCode();
                    }
                }
            }
            catch (Exception error) when (error is not OperationCanceledException)
            {
                // A disconnected poll never clears a durable deployment block.
            }
        } while (await timer.WaitForNextTickAsync(token));
    }

}
