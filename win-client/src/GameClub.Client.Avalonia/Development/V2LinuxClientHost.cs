using GameClub.Client.Application;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using GameClub.Client.Presentation;

namespace GameClub.Client.Avalonia.Development;

/// <summary>
/// Linux-сборка V2 для ручной проверки. Она использует настоящие V2 gRPC/HTTP
/// контракты и открытый dev-ledger вместо доступного только в Windows DPAPI.
/// </summary>
public sealed class V2LinuxClientHost : IClientHost
{
    private const string DefaultGrpcAddress = "http://127.0.0.1:51051";
    private const string DefaultEventsAddress = "http://127.0.0.1:8100/api/events/client-facts";
    private const string DefaultDevPublicKeyRing =
        "test-contour=11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=";

    private readonly V2DeviceEnrollmentTokenProvider _enrollment;
    private readonly V2LocalLedgerRecoveryCoordinator _recovery;
    private readonly HttpClient _eventsHttpClient;
    private readonly V2ClientOutboxWorker _outboxWorker;
    private readonly V2ServerEventWorker _serverEventWorker;
    private bool _started;

    public V2LinuxClientHost()
    {
        var environment = Environment.GetEnvironmentVariable("GAMECLUB_ENVIRONMENT")?.Trim();
        environment = string.IsNullOrWhiteSpace(environment) ? "dev" : environment;
        var grpcAddress = ResolveAddress(
            "GAMECLUB_GRPC_ADDRESS",
            DefaultGrpcAddress,
            environment);
        var eventsAddress = ResolveAddress(
            "GAMECLUB_V2_EVENTS_HTTP_ADDRESS",
            DefaultEventsAddress,
            environment);
        ClientLog.Info(
            "startup",
            $"v2 linux host configured environment={environment} grpc={grpcAddress} events={eventsAddress}");
        _enrollment = new V2DeviceEnrollmentTokenProvider(grpcAddress, environment);
        var backend = new V2GrpcBackendClient(grpcAddress, _enrollment);
        var ledger = new V2LocalLedgerCoordinator(new JsonV2LocalLedgerStore());
        _recovery = new V2LocalLedgerRecoveryCoordinator(ledger);
        _eventsHttpClient = new HttpClient();
        _outboxWorker = new V2ClientOutboxWorker(
            new V2ClientOutboxPublisher(
                ledger,
                new V2HttpClientEventPublisher(_eventsHttpClient, eventsAddress, _enrollment)));
        var verifier = new V2Ed25519OfflineSnapshotSignatureVerifier(
            V2SnapshotPublicKeyRing.Parse(
                Environment.GetEnvironmentVariable("GAMECLUB_V2_SNAPSHOT_PUBLIC_KEYS")
                ?? (environment == "dev" ? DefaultDevPublicKeyRing : string.Empty)));
        ViewModel = new MainViewModel(
            new ClientSessionCoordinator(backend),
            new EnvironmentAccessCredentialVerifier(environment),
            clientVersion: "avalonia-linux-v2",
            capabilities: ["v2.local-ledger", "v2.device-commands", "widget.v2", "linux-developer"],
            v2OfflineLogin: new V2OfflineLoginCoordinator(backend, ledger),
            v2Ledger: ledger,
            v2MinuteRunner: new V2MinuteLedgerRunner(ledger),
            v2SignatureVerifier: verifier,
            v2GuestSession: backend);
        _serverEventWorker = new V2ServerEventWorker(
            new V2HttpServerEventConsumer(
                _eventsHttpClient,
                new Uri(eventsAddress, "/api/events/server"),
                _enrollment,
                new V2ServerEventProcessor(ledger)),
            onFailure: ViewModel.ApplyV2ServerEventTransportFailure,
            onPoll: result => ViewModel.ApplyV2ServerEventPollResult(result.RejectedCount));
    }

    public MainViewModel ViewModel { get; }

    public string WindowTitle => "HubShell, Linux developer host";

    public string HostDisclaimer =>
        "Linux V2 developer-host: тестовый ledger в открытом виде, без DPAPI и kiosk enforcement.";

    public IClientWindowAdapter? WindowAdapter => null;

    public async Task StartAsync()
    {
        if (_started)
        {
            return;
        }

        _started = true;
        try
        {
            await ViewModel.RefreshConnectionAsync();
            ClientLog.Info("startup", $"initial connection state={ViewModel.ConnectionMessage}");
            ViewModel.TrackBackgroundTask(ViewModel.RunHeartbeatLoopAsync());
            ViewModel.TrackBackgroundTask(ViewModel.RunAccessLockLoopAsync());
            ViewModel.TrackBackgroundTask(ViewModel.RunSessionCountdownLoopAsync());
            ViewModel.TrackBackgroundTask(ActivateEnrollmentAsync());
        }
        catch (Exception error)
        {
            ClientLog.Exception("startup", error, "v2 host start failed");
            throw;
        }
    }

    public async ValueTask DisposeAsync()
    {
        await ViewModel.DisposeAsync();
        _eventsHttpClient.Dispose();
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
            ClientLog.Warning("enrollment", "device is still waiting for assignment");
            return;
        }

        ViewModel.SetDeviceIdentity(
            _enrollment.DeviceId,
            _enrollment.WorkstationId,
            _enrollment.WorkstationName);
        ClientLog.Info("enrollment", "device enrollment activated");
        await ViewModel.RecoverV2SessionAsync(_recovery, ViewModel.LifetimeToken);
        ViewModel.TrackBackgroundTask(_outboxWorker.RunAsync(ViewModel.LifetimeToken));
        ViewModel.TrackBackgroundTask(_serverEventWorker.RunAsync(ViewModel.LifetimeToken));
        ViewModel.TrackBackgroundTask(
            ViewModel.RunWorkstationHeartbeatLoopAsync(
                ViewModel.ApplyTheme,
                ViewModel.ApplyWorkstationName,
                ViewModel.ApplyManagerPasswordVerifier,
                ViewModel.ApplyLockdownPolicy,
                onConnectionStateChanged: ViewModel.ApplyHeartbeatConnectionState));
    }

    private static Uri ResolveAddress(string variable, string fallback, string environment)
    {
        var value = Environment.GetEnvironmentVariable(variable)?.Trim();
        value = string.IsNullOrWhiteSpace(value) ? fallback : value;
        if (!Uri.TryCreate(value, UriKind.Absolute, out var endpoint))
        {
            throw new InvalidOperationException($"{variable} must be an absolute URI");
        }
        return EndpointPolicy.Validate(endpoint, variable, environment);
    }
}
