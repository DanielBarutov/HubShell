using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using GameClub.Client.Infrastructure.Updates;

var settings = JsonSerializer.Deserialize<HostSettings>(File.ReadAllBytes(args.Single()), UpdateIpcProtocol.Json)!;
using var http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false });
var gui = new DeveloperGui(settings);
var agent = new ClientUpdateAgent(http, new Uri(settings.Backend), settings.DeviceId,
    settings.InstallationId, settings.CredentialSecret, File.ReadAllText(settings.PublicKeyPath),
    settings.Directory, gui) { HealthTimeout = TimeSpan.FromMilliseconds(500) };
while (await Console.In.ReadLineAsync() is { } command && command != "exit")
{
    using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
    try
    {
        switch (command)
        {
            case "tick": await agent.TickAsync(deadline.Token); break;
            case "active": gui.Active = true; break;
            case "idle": gui.Active = false; break;
            case "unhealthy": gui.Healthy = false; break;
            case "healthy": gui.Healthy = true; break;
            default: throw new InvalidDataException("Unknown developer command");
        }
        var journal = new ClientUpdateStateStore(settings.Directory).Read();
        Console.WriteLine(JsonSerializer.Serialize(new {
            ok = true, hash = ClientExecutableInstaller.Hash(Path.Combine(settings.Directory, "HubShell.exe")),
            stage = journal?.Stage, blocked = journal?.Blocked ?? false, closes = gui.Closes,
        }));
    }
    catch (Exception error)
    {
        Console.WriteLine(JsonSerializer.Serialize(new { ok = false, error = error.GetType().Name,
            status = (error as HttpRequestException)?.StatusCode }));
    }
}

internal sealed record HostSettings(string Backend, string DeviceId, string InstallationId,
    string CredentialSecret, string GuiToken, string PublicKeyPath, string Directory,
    string TargetReleaseId, string TargetSha256);

// Linux protocol host: process/IPC are simulated; HTTP, signatures and file replacement are real.
internal sealed class DeveloperGui(HostSettings settings) : IUpdateGuiPlatform
{
    public bool Active { get; set; }
    public bool Healthy { get; set; } = true;
    public int Closes { get; private set; }
    private bool _paused;
    private bool _running = true;
    private readonly ClientUpdateStateStore _state = new(settings.Directory);
    private string Release => ClientExecutableInstaller.Hash(Path.Combine(settings.Directory, "HubShell.exe"))
        == settings.TargetSha256 ? (Healthy ? settings.TargetReleaseId : "unhealthy") : "v-old";

    public Task PauseRecoveryAsync(CancellationToken token) { _paused = true; return Task.CompletedTask; }
    public Task ResumeRecoveryAsync(CancellationToken token) { _paused = false; return Task.CompletedTask; }
    public Task WaitForExitAsync(CancellationToken token)
    {
        if (_running) throw new InvalidOperationException("GUI has not exited");
        return Task.CompletedTask;
    }
    public async Task StartGuiAsync(CancellationToken token) { _running = true; await ConfirmAsync(token); }
    public Task StopFailedGuiAsync(CancellationToken token)
    {
        if (Active) throw new InvalidOperationException("Cannot stop active session");
        _running = false;
        return Task.CompletedTask;
    }
    public async Task<UpdateIpcStatus> QueryAsync(UpdateIpcRequest request, CancellationToken token)
    {
        var local = _state.Read();
        var blocked = local?.Blocked == true;
        var ready = !Active && _running && (Release != "unhealthy");
        var closing = false;
        if (request.Command == "close")
        {
            if (!_paused || !blocked || !ready || local!.DeploymentId != request.DeploymentId
                || local.RoundId != request.RoundId) throw new InvalidOperationException("Unsafe GUI close");
            _running = false;
            closing = true;
            Closes++;
        }
        else if (_running) await ConfirmAsync(token);
        return new(settings.DeviceId, settings.InstallationId, Release, Active, 0, ready, blocked, closing);
    }
    private async Task ConfirmAsync(CancellationToken token)
    {
        if (Active || !_running || Release != settings.TargetReleaseId || _state.Read()?.Blocked != true) return;
        using var gui = new HttpClient { BaseAddress = new Uri(settings.Backend) };
        gui.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", settings.GuiToken);
        var current = await gui.GetFromJsonAsync<JsonElement>("/api/v1/client-updates/gui/current", token);
        var item = current.GetProperty("deployment");
        if (item.ValueKind == JsonValueKind.Null || item.GetProperty("phase").GetString() != "authorized") return;
        using var response = await gui.PostAsJsonAsync($"/api/v1/client-updates/{item.GetProperty("id").GetString()}/gui-confirm",
            new { release_id = Release }, token);
        response.EnsureSuccessStatusCode();
    }
}
